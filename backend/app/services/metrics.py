"""Observability, evaluation and FinOps reads.

The five figures a claims leader should be able to read on a Monday morning without
asking an engineer, plus the agent topology, the tool ledger and cost per claim.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.definitions import AGENT_SPECS
from app.agents.harness import harness_status
from app.config import COST_BASIS_NOTE, THRESHOLDS
from app.models import (
    AgentRun,
    Claim,
    CoverageAssessment,
    Document,
    ExtractedField,
    Message,
    ReviewTask,
)


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def portfolio_metrics(db: Session) -> dict[str, Any]:
    """The five headline measures, each computed from rows rather than asserted."""
    claims = db.scalars(select(Claim)).all()
    decided = [c for c in claims if c.decision]
    live = [c for c in claims if c.scenario_key]

    # 1. Straight-through processing
    eligible = [c for c in decided if not c.injury_reported and (c.fraud_score or 0) <= THRESHOLDS.max_fraud_score_for_autonomy]
    stp = [c for c in eligible if c.straight_through]

    # 2. First-time-right intake — no repeat document and no follow-up question needed
    docs = db.scalars(select(Document)).all()
    by_claim: dict[str, list[Document]] = {}
    for d in docs:
        by_claim.setdefault(d.claim_reference, []).append(d)
    fields = db.scalars(select(ExtractedField)).all()
    low_conf_docs = {f.doc_id for f in fields if (f.confidence or 1.0) < 0.85}
    ftr_total = len(by_claim)
    ftr_ok = sum(
        1 for ref, items in by_claim.items()
        if not any(i.duplicate_of for i in items)
        and not any((i.quality_score or 1.0) < 0.55 for i in items)
        and not any(i.doc_id in low_conf_docs for i in items)
    )

    # 3. Grounded answer rate — material coverage answers carrying a valid citation
    assessments = db.scalars(select(CoverageAssessment)).all()
    material = [a for a in assessments if a.status and a.status != "unknown"]
    grounded = [a for a in material if a.citations]

    # 4. Human override rate, by reason
    tasks = db.scalars(select(ReviewTask)).all()
    resolved = [t for t in tasks if t.status == "resolved"]
    overrides = [t for t in resolved if t.decision and t.decision != t.proposed_decision]
    by_reason: dict[str, int] = {}
    for t in overrides:
        by_reason[t.reason or "unknown"] = by_reason.get(t.reason or "unknown", 0) + 1

    # 5. Cycle time, FNOL to decision, by claim type
    cycle: dict[str, list[float]] = {}
    for c in decided:
        if not (c.reported_at and c.closed_at):
            continue
        start = c.reported_at if c.reported_at.tzinfo else c.reported_at.replace(tzinfo=dt.timezone.utc)
        end = c.closed_at if c.closed_at.tzinfo else c.closed_at.replace(tzinfo=dt.timezone.utc)
        hours = (end - start).total_seconds() / 3600.0
        cycle.setdefault(c.incident_type or "other", []).append(hours)

    return {
        "headline": [
            {
                "key": "straight_through_processing",
                "label": "Straight-through processing",
                "sublabel": "Eligible claims finished with no human change",
                "value": _pct(len(stp), len(eligible)),
                "format": "percent",
                "numerator": len(stp),
                "denominator": len(eligible),
            },
            {
                "key": "first_time_right_intake",
                "label": "First-time-right intake",
                "sublabel": "No repeat document or follow-up question needed",
                "value": _pct(ftr_ok, ftr_total),
                "format": "percent",
                "numerator": ftr_ok,
                "denominator": ftr_total,
            },
            {
                "key": "grounded_answer_rate",
                "label": "Grounded answer rate",
                "sublabel": "Material answers carrying a valid citation",
                "value": _pct(len(grounded), len(material)),
                "format": "percent",
                "numerator": len(grounded),
                "denominator": len(material),
            },
            {
                "key": "human_override_rate",
                "label": "Human override rate",
                "sublabel": "Tracked by reason, not as one number",
                "value": _pct(len(overrides), len(resolved)),
                "format": "percent",
                "numerator": len(overrides),
                "denominator": len(resolved),
                "breakdown": by_reason,
            },
            {
                "key": "claim_cycle_time",
                "label": "Claim cycle time",
                "sublabel": "FNOL to decision, by claim type",
                "value": round(
                    sum(sum(v) for v in cycle.values())
                    / max(sum(len(v) for v in cycle.values()), 1), 2
                ),
                "format": "hours",
                "breakdown": {
                    k: round(sum(v) / len(v), 2) for k, v in sorted(cycle.items())
                },
            },
        ],
        "portfolio": {
            "total_claims": len(claims),
            "live_demo_claims": len(live),
            "decided": len(decided),
            "in_review": sum(1 for c in claims if c.status == "in_review"),
            "awaiting_customer": sum(1 for c in claims if c.status == "awaiting_customer"),
            "approved": sum(1 for c in claims if c.decision == "Approved"),
            "total_settled_eur": round(sum(c.settlement_amount_eur or 0.0 for c in claims), 2),
            "by_region": _group(claims, "incident_region"),
            "by_incident_type": _group(claims, "incident_type"),
            "by_severity": _group(claims, "severity"),
            "by_status": _group(claims, "status"),
        },
    }


def _group(rows: list[Any], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = getattr(r, attr, None) or "unspecified"
        out[str(k)] = out.get(str(k), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def run_observability(db: Session, limit: int = 25) -> dict[str, Any]:
    """Trace, token and cost view over recent runs, plus the agent topology."""
    runs = db.scalars(
        select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    ).all()

    total_tokens = sum((r.prompt_tokens or 0) + (r.completion_tokens or 0) for r in runs)
    total_cost = round(sum(r.cost_eur or 0.0 for r in runs), 6)
    completed = [r for r in runs if r.status == "completed"]

    tool_counts: dict[str, int] = {}
    step_durations: dict[str, list[float]] = {}
    agent_calls: dict[str, int] = {}
    for r in runs:
        for ev in r.trace or []:
            if ev.get("kind") == "tool_call":
                name = (ev.get("data") or {}).get("tool") or "unknown"
                tool_counts[name] = tool_counts.get(name, 0) + 1
            if ev.get("kind") == "step_end" and ev.get("step_id"):
                step_durations.setdefault(ev["step_id"], []).append(ev.get("elapsed_ms") or 0.0)
            if ev.get("agent"):
                agent_calls[ev["agent"]] = agent_calls.get(ev["agent"], 0) + 1

    return {
        "harness": harness_status(),
        "cost_basis_note": COST_BASIS_NOTE,
        "runs": [
            {
                "run_id": r.run_id,
                "claim_reference": r.claim_reference,
                "status": r.status,
                "outcome": r.outcome,
                "model_mode": r.model_mode,
                "trigger": r.trigger,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "duration_ms": r.duration_ms,
                "steps_completed": r.steps_completed,
                "tool_calls": r.tool_calls,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": (r.prompt_tokens or 0) + (r.completion_tokens or 0),
                "cost_eur": r.cost_eur,
                "budget_stops": r.budget_stops or [],
            }
            for r in runs
        ],
        "totals": {
            "run_count": len(runs),
            "completed": len(completed),
            "failed": sum(1 for r in runs if r.status == "failed"),
            "stopped": sum(1 for r in runs if r.status == "stopped"),
            "total_tokens": total_tokens,
            "total_cost_eur": total_cost,
            "avg_tokens_per_run": round(total_tokens / max(len(runs), 1), 1),
            "cost_per_claim_eur": round(total_cost / max(len(runs), 1), 6),
            "avg_duration_ms": round(
                sum(r.duration_ms or 0.0 for r in runs) / max(len(runs), 1), 2
            ),
            "avg_tool_calls": round(
                sum(r.tool_calls or 0 for r in runs) / max(len(runs), 1), 2
            ),
        },
        "tool_ledger": dict(sorted(tool_counts.items(), key=lambda kv: -kv[1])),
        "agent_activity": dict(sorted(agent_calls.items(), key=lambda kv: -kv[1])),
        "step_latency_ms": {
            k: round(sum(v) / len(v), 2) for k, v in sorted(step_durations.items())
        },
        "topology": {
            "agents": [
                {
                    "key": s.key, "name": s.name, "ordinal": s.ordinal, "title": s.title,
                    "model_tier": s.model_tier, "tool_scope": s.tool_scope,
                    "calls": agent_calls.get(s.name, 0),
                }
                for s in AGENT_SPECS
            ],
            "composition": (
                "SequentialAgent[DocumentUnderstanding → IntakeOrchestrator → "
                "ParallelAgent[Coverage ∥ DamageAssessment ∥ RepairEstimate ∥ FraudRisk] "
                "→ Decision] then HitlCoordinator and CustomerCommunication"
            ),
        },
    }


def run_detail(db: Session, run_id: str) -> dict[str, Any] | None:
    run = db.get(AgentRun, run_id)
    if run is None:
        return None
    return {
        "run_id": run.run_id,
        "claim_reference": run.claim_reference,
        "status": run.status,
        "outcome": run.outcome,
        "model_mode": run.model_mode,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "duration_ms": run.duration_ms,
        "steps_completed": run.steps_completed,
        "tool_calls": run.tool_calls,
        "prompt_tokens": run.prompt_tokens,
        "completion_tokens": run.completion_tokens,
        "cost_eur": run.cost_eur,
        "budget_stops": run.budget_stops or [],
        "trace": run.trace or [],
    }


def messages_for(db: Session, reference: str) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Message).where(Message.claim_reference == reference)
        .order_by(Message.created_at.asc())
    ).all()
    return [
        {
            "message_id": m.message_id, "channel": m.channel, "language": m.language,
            "template_id": m.template_id, "subject": m.subject, "body": m.body,
            "status": m.status, "guard_findings": m.guard_findings or [],
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]
