"""GenAI evaluation — golden cases, trajectory and groundedness.

Continuous proof that quality has not drifted. Each golden case asserts four things: the
outcome, the routing, the exact set of policy checks that should have failed, and whether
a material coverage answer carried a citation. A trajectory check confirms the agents
actually called the tools they are supposed to call.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.graph import run_claim
from app.models import Claim

GOLDEN_CASES: list[dict[str, Any]] = [
    {
        "reference": "AT-2026-004417",
        "name": "Straight-through approval inside the ceiling",
        "expect_decision": "Approved",
        "expect_queue": None,
        "expect_failed_checks": [],
        "expect_grounded": True,
        "expect_straight_through": True,
        "expect_claim_settled_eur": 1_142.30,
        "expect_tools": ["get_claim_360", "get_extractions", "get_policy_coverage",
                         "search_policy_wording", "get_damage_findings",
                         "calculate_repair_estimate", "get_risk_signals",
                         "assemble_decision_inputs", "get_template",
                         "check_total_loss_threshold", "assess_recovery"],
        "expect_settlement_eur": 1_142.30,
    },
    {
        "reference": "AT-2026-004422",
        "name": "Total loss settles on the vehicle, not the repair bill",
        "expect_decision": "Review Required",
        "expect_queue": "assessment",
        "expect_grounded": True,
        "expect_straight_through": False,
        "expect_tools": ["get_damage_findings", "calculate_repair_estimate",
                         "check_total_loss_threshold"],
        # The path that had no scenario and no assertion, which is why the indemnity
        # basis could be wrong for as long as it was. These assertions pin the three
        # things that were broken: panels must come off the repair quote, the verdict
        # must be a total loss, and the indemnity must be measured on the vehicle.
        "expect_total_loss": True,
        "expect_panels_at_least": 5,
        "expect_indemnity_basis": "total_loss",
    },
    {
        "reference": "AT-2026-004418",
        "name": "Ceiling and severity both block autonomy",
        "expect_decision": "Review Required",
        "expect_queue": "operations",
        "expect_failed_checks": ["PG-01", "PG-02"],
        "expect_grounded": True,
        "expect_straight_through": False,
        "expect_tools": ["calculate_repair_estimate", "create_review_task"],
        # The guard downgrades the decision but preserves the recommendation, so the
        # package still carries the figure the agent proposed…
        "expect_settlement_eur": 9_006.64,
        # …while nothing is written to the claim until a supervisor approves it.
        "expect_claim_settled_eur": 0.0,
    },
    {
        "reference": "AT-2026-004419",
        "name": "Liability-only cover excludes own-vehicle damage",
        "expect_decision": "Review Required",
        "expect_queue": "coverage",
        "expect_failed_checks": ["PG-09"],
        "expect_grounded": True,
        "expect_straight_through": False,
        "expect_tools": ["search_policy_wording", "create_review_task"],
        "expect_clause": "AKHB Art 8.2",
    },
    {
        "reference": "AT-2026-004420",
        "name": "Elevated fraud signal freezes autonomy",
        "expect_decision": "Review Required",
        "expect_queue": "siu",
        "expect_failed_checks": ["PG-01", "PG-08"],
        "expect_grounded": True,
        "expect_straight_through": False,
        "expect_tools": ["get_risk_signals", "graph_neighbours", "create_review_task"],
    },
    {
        "reference": "AT-2026-004421",
        "name": "Injury stop, and a poisoned document stripped",
        "expect_decision": "Review Required",
        "expect_queue": "injury",
        "expect_failed_checks": ["PG-07"],
        "expect_grounded": True,
        "expect_straight_through": False,
        "expect_security_events": 1,
        "expect_tools": ["get_extractions", "create_review_task"],
    },
]


async def run_evaluations(db: Session, mode: str | None = None) -> dict[str, Any]:
    """Replay every golden case and score it. Nothing here is mocked."""
    results: list[dict[str, Any]] = []

    for case in GOLDEN_CASES:
        final_event: dict[str, Any] | None = None
        tools_called: list[str] = []
        security_events = 0

        async for ev in run_claim(db, case["reference"], trigger="evaluation", mode=mode,
                                  runtime=("deterministic" if mode == "deterministic"
                                           else None)):
            if ev.get("kind") == "tool_call":
                tools_called.append((ev.get("data") or {}).get("tool") or "")
            if ev.get("kind") == "security":
                security_events += 1
            if ev.get("kind") == "run_end":
                final_event = ev

        data = (final_event or {}).get("data") or {}
        final = data.get("final") or {}
        guard = data.get("guard") or {}
        routing = data.get("routing") or {}
        outputs = data.get("agent_outputs") or {}
        coverage = outputs.get("coverage") or {}

        failed = sorted(
            c["check_id"] for c in (guard.get("checks") or []) if not c.get("passed")
        )
        citations = coverage.get("citations") or []

        assertions: list[dict[str, Any]] = []

        def assert_that(name: str, passed: bool, expected: Any, actual: Any) -> None:
            assertions.append({
                "assertion": name, "passed": bool(passed),
                "expected": expected, "actual": actual,
            })

        assert_that("outcome", final.get("decision") == case["expect_decision"],
                    case["expect_decision"], final.get("decision"))
        assert_that("routing", routing.get("queue") == case["expect_queue"],
                    case["expect_queue"], routing.get("queue"))
        if "expect_failed_checks" in case:
            assert_that("policy_checks_failed",
                        failed == sorted(case["expect_failed_checks"]),
                        sorted(case["expect_failed_checks"]), failed)
        assert_that("groundedness", bool(citations) == case["expect_grounded"],
                    case["expect_grounded"], bool(citations))

        if "expect_settlement_eur" in case:
            actual_amount = round(float(final.get("settlement_amount_eur") or 0.0), 2)
            assert_that("settlement_amount",
                        abs(actual_amount - case["expect_settlement_eur"]) < 0.01,
                        case["expect_settlement_eur"], actual_amount)

        # The total-loss dimensions. These exist because the path had no scenario and no
        # assertion, so an indemnity measured on the wrong quantity went unnoticed.
        if "expect_total_loss" in case:
            tl = outputs.get("total_loss") or {}
            assert_that("total_loss_verdict",
                        (tl.get("verdict") == "total_loss") == case["expect_total_loss"],
                        case["expect_total_loss"], tl.get("verdict"))

        if "expect_panels_at_least" in case:
            damage = outputs.get("damage_assessment") or {}
            count = int(damage.get("panel_count") or 0)
            assert_that("panels_read_from_evidence",
                        count >= case["expect_panels_at_least"],
                        f">= {case['expect_panels_at_least']}", count)

        if "expect_indemnity_basis" in case:
            basis = (final.get("indemnity") or {}).get("basis")
            assert_that("indemnity_basis", basis == case["expect_indemnity_basis"],
                        case["expect_indemnity_basis"], basis)

        if "expect_clause" in case:
            clauses = [c.get("clause_id") for c in citations]
            assert_that("clause_cited", case["expect_clause"] in clauses,
                        case["expect_clause"], clauses)

        if "expect_security_events" in case:
            assert_that("security_events",
                        security_events >= case["expect_security_events"],
                        f">= {case['expect_security_events']}", security_events)

        if "expect_claim_settled_eur" in case:
            db.expire_all()
            claim_row = db.get(Claim, case["reference"])
            settled = round(float((claim_row.settlement_amount_eur if claim_row else 0.0) or 0.0), 2)
            assert_that(
                "claim_settled_amount",
                abs(settled - case["expect_claim_settled_eur"]) < 0.01,
                case["expect_claim_settled_eur"], settled,
            )

        if "expect_straight_through" in case:
            db.expire_all()
            claim_row = db.get(Claim, case["reference"])
            actual_stp = bool(claim_row.straight_through) if claim_row else False
            assert_that("straight_through", actual_stp == case["expect_straight_through"],
                        case["expect_straight_through"], actual_stp)

        missing_tools = [t for t in case["expect_tools"] if t not in tools_called]
        assert_that("trajectory", not missing_tools, case["expect_tools"],
                    {"called": sorted(set(tools_called)), "missing": missing_tools})

        passed = all(a["passed"] for a in assertions)
        results.append({
            "reference": case["reference"],
            "name": case["name"],
            "passed": passed,
            "assertions": assertions,
            "observed": {
                "decision": final.get("decision"),
                "proposed_decision": final.get("original_decision") or final.get("decision"),
                "settlement_amount_eur": final.get("settlement_amount_eur"),
                "queue": routing.get("queue"),
                "failed_checks": failed,
                "citations": [c.get("clause_id") for c in citations],
                "tools_called": sorted(set(t for t in tools_called if t)),
                "security_events": security_events,
                "summary": (data.get("summary") or {}),
            },
        })

    passed_count = sum(1 for r in results if r["passed"])
    total_assertions = sum(len(r["assertions"]) for r in results)
    passed_assertions = sum(
        1 for r in results for a in r["assertions"] if a["passed"]
    )

    return {
        "suite": "allianz-at-motor-golden-cases-1.0",
        "mode": mode or "auto",
        "cases": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "pass_rate": round(passed_count / max(len(results), 1), 4),
        "assertions": {
            "total": total_assertions,
            "passed": passed_assertions,
            "pass_rate": round(passed_assertions / max(total_assertions, 1), 4),
        },
        "dimensions": ["outcome", "routing", "policy_checks_failed", "groundedness",
                       "total_loss_verdict", "panels_read_from_evidence", "indemnity_basis",
                       "settlement_amount", "clause_cited", "security_events", "trajectory"],
        "results": results,
    }
