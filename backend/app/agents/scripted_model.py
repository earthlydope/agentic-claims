"""Deterministic model provider.

`google-adk` runs the whole way through in both modes. Tools execute for real, plugins
fire for real, sessions and the event stream are the real ADK ones. The only thing that
changes without Google credentials is where the reasoning turn comes from.

In scripted mode each agent follows a fixed tool trajectory and then synthesises its
answer *from the actual tool results* — it is data-driven, not a canned string. That
keeps every downstream control genuinely exercised: the policy guard evaluates real
numbers, the signer signs a real payload, and the ledger chains real entries.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from app.agents.harness import maybe_run_context
from app.config import THRESHOLDS

# --------------------------------------------------------------------------
# Synthesisers — one per agent, each reading only what its own tools returned
# --------------------------------------------------------------------------
def _d(results: dict[str, Any], tool: str) -> dict[str, Any]:
    return (results.get(tool) or {}).get("data") or {}


def _synth_intake(results: dict[str, Any]) -> dict[str, Any]:
    claim = _d(results, "get_claim_360")
    ev = _d(results, "get_outstanding_evidence")
    missing = ev.get("missing") or []
    confirm = ev.get("needs_confirmation") or []
    unreadable = ev.get("unreadable_evidence") or []

    if missing:
        next_step = "request_information"
    elif unreadable:
        next_step = "re_ask_specific_view"
    elif confirm:
        next_step = "confirm_low_confidence_reads"
    else:
        next_step = "proceed_to_assessment"

    questions = (
        [c["ask"] for c in confirm]
        + [u["ask"] for u in unreadable]
        + [f"Please provide {m}." for m in missing]
    )

    return {
        "next_step": next_step,
        "summary": (
            f"Claim {claim.get('reference')} reported via {claim.get('channel')} "
            f"{claim.get('age_hours')}h ago. "
            f"{len(claim.get('evidence') or [])} item(s) of evidence received."
        ),
        "evidence": {
            "completeness": ev.get("evidence_completeness"),
            "validated_fields": ev.get("validated_fields"),
            "missing": missing,
            "needs_confirmation": confirm,
            "unreadable": unreadable,
        },
        "customer_questions": questions,
        "routing_hint": (
            "specialist" if claim.get("injury_reported") else "automated_assessment"
        ),
        "injury_reported": bool(claim.get("injury_reported")),
    }


def _synth_document_understanding(results: dict[str, Any]) -> dict[str, Any]:
    docs = (results.get("get_extractions") or {}).get("data") or []
    classified, conflicts, low_conf = [], [], []

    quote_totals: list[tuple[str, float]] = []
    for doc in docs:
        fields = doc.get("fields") or []
        classified.append({
            "doc_id": doc.get("doc_id"),
            "filename": doc.get("filename"),
            "doc_type": doc.get("doc_type"),
            "kind": doc.get("kind"),
            "page_count": doc.get("page_count"),
            "quality_score": doc.get("quality_score"),
            "quarantined": bool(doc.get("quarantined")),
            "sanitised": bool(doc.get("sanitised")),
            "field_count": len(fields),
        })
        for f in fields:
            if (f.get("confidence") or 1.0) < 0.85:
                low_conf.append({
                    "doc_id": doc.get("doc_id"),
                    "field_name": f.get("field_name"),
                    "read_as": f.get("extracted_value"),
                    "confidence": f.get("confidence"),
                    "recovery_action": f.get("recovery_action"),
                })
            if f.get("field_name") in ("quote_total_eur", "invoice_total_eur"):
                try:
                    quote_totals.append((doc.get("doc_id"), float(f.get("extracted_value"))))
                except (TypeError, ValueError):
                    pass

    if len({round(v, 2) for _, v in quote_totals}) > 1:
        conflicts.append({
            "kind": "conflicting_totals",
            "detail": "Two documents state different repair totals.",
            "values": [{"doc_id": d, "total_eur": v} for d, v in quote_totals],
        })

    return {
        "documents": classified,
        "document_count": len(classified),
        "low_confidence_fields": low_conf,
        "conflicts": conflicts,
        "quote_total_eur": quote_totals[0][1] if quote_totals else None,
        "summary": (
            f"{len(classified)} document(s) classified; "
            f"{len(low_conf)} field(s) below the 0.85 confidence threshold."
        ),
    }


def _synth_coverage(results: dict[str, Any]) -> dict[str, Any]:
    cov = _d(results, "get_policy_coverage")
    wording = _d(results, "search_policy_wording")
    citations = wording.get("citations") or []
    endorsements = (results.get("get_endorsements") or {}).get("data") or []

    product = cov.get("product")
    in_force = bool(cov.get("in_force_on_date_of_loss"))
    incident_type = (cov.get("incident") or {}).get("type")
    own_damage = bool(cov.get("own_damage_claimed"))
    exclusions = set(cov.get("exclusions") or [])
    covers = set(cov.get("covers") or [])

    named_perils = {
        "hail": "hail", "glass_breakage": "glass", "theft_attempt": "theft",
        "fire": "fire", "storm": "storm", "wild_game": "wild_game",
    }

    if not in_force:
        status = "lapsed"
        reasoning = "The policy was not in force on the date of loss."
    elif product == "Haftpflicht" and own_damage:
        status = "excluded"
        reasoning = (
            "The policy provides third-party liability cover only. Damage to the "
            "policyholder's own vehicle falls outside that cover."
        )
    elif product == "Teilkasko":
        peril = named_perils.get(incident_type or "")
        if peril and peril in covers:
            status = "covered_with_excess"
            reasoning = (
                f"Partial cover includes {peril.replace('_', ' ')}, which is the peril "
                "claimed here."
            )
        elif "at_fault_collision" in exclusions:
            status = "excluded"
            reasoning = (
                "Partial cover responds to named perils only, and an at-fault collision "
                "is not among them."
            )
        else:
            status = "unknown"
            reasoning = "The peril claimed does not map cleanly to a named partial-cover peril."
    elif product == "Vollkasko":
        status = "covered_with_excess"
        reasoning = (
            "Comprehensive cover responds to accidental damage to the insured vehicle "
            "irrespective of fault."
        )
    else:
        status = "unknown"
        reasoning = "The product on this policy could not be mapped to a coverage position."

    # The citation rule is not optional: without an authoritative clause there is no
    # material coverage answer, only an escalation.
    if not citations:
        status = "unknown"
        reasoning = (
            "No authoritative clause was retrieved for this question. Abstaining and "
            "referring to a coverage adjuster rather than answering from general knowledge."
        )

    return {
        "status": status,
        "product": product,
        "in_force_on_date_of_loss": in_force,
        "excess_eur": cov.get("excess_eur") if status.startswith("covered") else 0.0,
        "sum_insured_eur": cov.get("sum_insured_eur"),
        "reasoning": reasoning,
        "citations": citations,
        "clauses_applied": [c.get("clause_id") for c in citations],
        "endorsements": endorsements,
        "confidence": 0.94 if citations else 0.0,
        "abstained": not citations,
        "summary": (
            f"Coverage assessed as '{status}' on {product or 'the policy'}, grounded on "
            + (", ".join(c.get("clause_id") for c in citations) if citations
               else "no authoritative clause — abstained")
            + "."
        ),
    }


def _synth_damage(results: dict[str, Any]) -> dict[str, Any]:
    f = _d(results, "get_photo_findings")
    return {
        "severity": f.get("severity"),
        "severity_basis": f.get("severity_basis"),
        "structural_damage": bool(f.get("structural_damage")),
        "panels": f.get("panels") or [],
        "panel_count": f.get("panel_count"),
        "low_quality_photos": f.get("low_quality_photos") or [],
        "missing_views": f.get("missing_views") or [],
        "confidence": round(
            min([p.get("confidence", 0.0) for p in (f.get("panels") or [{}])] or [0.0]), 2
        ),
        "summary": (
            f"{f.get('panel_count')} panel(s) affected; severity assessed as "
            f"{f.get('severity')} because {f.get('severity_basis')}."
        ),
    }


def _synth_estimate(results: dict[str, Any]) -> dict[str, Any]:
    e = _d(results, "calculate_repair_estimate")
    rate = _d(results, "get_labour_rate")
    return {
        "items": e.get("items") or [],
        "labour_hours": e.get("labour_hours"),
        "labour_rate_eur": e.get("labour_rate_eur") or rate.get("labour_rate_eur"),
        "total_parts": e.get("total_parts"),
        "total_labour": e.get("total_labour"),
        "total_tax": e.get("total_tax"),
        "total_cost": e.get("total_cost"),
        "vat_rate": e.get("vat_rate"),
        "region": e.get("region") or rate.get("region"),
        "severity": e.get("severity"),
        "structural_damage": e.get("structural_damage"),
        "reasonableness": e.get("reasonableness"),
        "sandbox": e.get("_sandbox"),
        "summary": (
            f"EUR {e.get('total_parts', 0):,.2f} parts + "
            f"EUR {e.get('total_labour', 0):,.2f} labour "
            f"({e.get('labour_hours')}h at EUR {e.get('labour_rate_eur')}/h) + "
            f"EUR {e.get('total_tax', 0):,.2f} VAT = EUR {e.get('total_cost', 0):,.2f}."
        ),
    }


def _synth_fraud(results: dict[str, Any]) -> dict[str, Any]:
    rs = _d(results, "get_risk_signals")
    gn = _d(results, "graph_neighbours")
    neighbours = gn.get("neighbours") or []
    flagged = [n for n in neighbours if n.get("flagged")]

    score = float(rs.get("score") or 0.0)
    threshold = THRESHOLDS.max_fraud_score_for_autonomy

    return {
        "score": round(score, 3),
        "threshold": threshold,
        "above_threshold": score > threshold,
        "signals": rs.get("signals") or [],
        "signal_count": len(rs.get("signals") or []),
        "graph": {
            "neighbour_count": len(neighbours),
            "flagged_count": len(flagged),
            "flagged": flagged,
        },
        "recommendation": (
            "freeze_and_refer_siu" if score > threshold else "no_investigation_required"
        ),
        "summary": (
            f"Composite risk score {score:.2f} against a threshold of {threshold:.2f}, "
            f"from {len(rs.get('signals') or [])} signal(s) and "
            f"{len(flagged)} flagged relationship(s)."
        ),
        "note": (
            "These are signals, not findings. The claim is frozen and referred, never "
            "declined on a signal alone."
        ),
    }


def _synth_decision(results: dict[str, Any]) -> dict[str, Any]:
    inp = _d(results, "assemble_decision_inputs")
    claim = inp.get("claim") or {}
    coverage = inp.get("coverage") or {}
    estimate = inp.get("estimate") or {}
    risk = inp.get("risk") or {}
    damage = inp.get("damage") or {}
    evidence = inp.get("evidence") or {}

    total = float(estimate.get("total_cost") or 0.0)
    excess = float(coverage.get("excess_eur") or 0.0)
    cov_status = coverage.get("status") or "unknown"
    missing = list(evidence.get("missing") or [])
    unreadable = list(evidence.get("unreadable") or [])

    # The Decision agent proposes on coverage and evidence alone. It deliberately does
    # not apply the ceiling, the severity rule, the injury stop or the fraud threshold —
    # those are the deterministic guard's job, and the demonstration depends on the guard
    # being the thing that catches them.
    if cov_status in ("excluded", "lapsed"):
        decision = "Declined"
        settlement = 0.0
        reasoning = f"Coverage position is '{cov_status}'. {coverage.get('reasoning', '')}".strip()
    elif cov_status == "unknown":
        decision = "Review Required"
        settlement = 0.0
        reasoning = (
            "The coverage position could not be established from an authoritative clause."
        )
    elif missing or unreadable:
        decision = "Request Information"
        settlement = 0.0
        reasoning = "Required evidence is still outstanding, so no decision is proposed yet."
    else:
        decision = "Approved"
        settlement = round(max(total - excess, 0.0), 2)
        reasoning = (
            f"Cover confirmed as '{cov_status}' on "
            f"{', '.join(coverage.get('clauses_applied') or []) or 'the policy schedule'}. "
            f"Estimate of EUR {total:,.2f} less an excess of EUR {excess:,.2f} gives a "
            f"settlement of EUR {settlement:,.2f}."
        )

    return {
        "decision": decision,
        "settlement_amount_eur": settlement,
        "reasoning": reasoning,
        "severity": damage.get("severity") or claim.get("severity"),
        "structural_damage": bool(damage.get("structural_damage")),
        "injury_reported": bool(claim.get("injury_reported")),
        "coverage": {
            "status": cov_status,
            "excess_eur": excess,
            "citations": coverage.get("citations") or [],
            "clauses_applied": coverage.get("clauses_applied") or [],
            "reasoning": coverage.get("reasoning"),
        },
        "estimate": {
            "total_cost": total,
            "total_parts": estimate.get("total_parts"),
            "total_labour": estimate.get("total_labour"),
            "total_tax": estimate.get("total_tax"),
            "items": estimate.get("items") or [],
        },
        "risk": {
            "score": risk.get("score"),
            "signals": risk.get("signals") or [],
            "recommendation": risk.get("recommendation"),
        },
        "evidence": {
            "missing": missing,
            "completeness": evidence.get("completeness"),
        },
        "claim_reference": claim.get("reference"),
        "summary": (
            f"Proposing '{decision}'"
            + (f" at EUR {settlement:,.2f}" if settlement else "")
            + f" on coverage status '{cov_status}'."
        ),
    }


def _synth_hitl(results: dict[str, Any]) -> dict[str, Any]:
    task = _d(results, "create_review_task")
    queue = _d(results, "get_queue_state")
    return {
        "task": task,
        "queue_depth": len(queue) if isinstance(queue, list) else None,
        "summary": (
            f"Review task {task.get('task_id')} created on the {task.get('queue')} queue, "
            f"requiring {task.get('authority_required')} authority."
        ),
    }


# What a customer may be told about why their claim is with a person. Internal rule
# identifiers, guard reasoning, queue names and investigation status never appear here.
CUSTOMER_SAFE_REASON: dict[str, dict[str, str]] = {
    "ceiling_or_severity": {
        "de": "Die Reparatursumme liegt über dem Betrag, den wir automatisch freigeben, "
              "daher gibt eine Kollegin sie frei.",
        "en": "The repair figure is above the amount we settle automatically, so a "
              "colleague signs it off.",
    },
    "evidence_incomplete": {
        "de": "Uns fehlt noch eine Angabe zu Ihrem Schaden.",
        "en": "We are still missing one detail about your claim.",
    },
    "coverage_uncertain_or_excluded": {
        "de": "Eine Kollegin prüft die Deckung nach Ihrer Polizze.",
        "en": "A colleague is confirming the position under your policy.",
    },
    "adverse_decision_review": {
        "de": "Eine Kollegin prüft die Deckung nach Ihrer Polizze.",
        "en": "A colleague is confirming the position under your policy.",
    },
    "injury_reported": {
        "de": "Weil Sie eine Verletzung angegeben haben, betreut ein Fachteam Ihren "
              "Schaden persönlich.",
        "en": "Because you mentioned an injury, a specialist team is handling your claim "
              "personally.",
    },
    # Deliberately absent: fraud_signal_elevated. A customer is never told that a claim
    # is under investigation.
}


def _synth_comms(results: dict[str, Any]) -> dict[str, Any]:
    tpl = _d(results, "get_template")
    ctx = maybe_run_context()
    outputs = ctx.agent_outputs if ctx else {}
    final = outputs.get("_final") or {}
    routing = outputs.get("_routing") or {}
    coverage = (outputs.get("decision") or {}).get("coverage") or {}
    language = tpl.get("language") or "de"
    reference = ctx.claim_reference if ctx else ""
    template_id = tpl.get("template_id") or "claim_in_review"

    de = language == "de"
    lines = [(tpl.get("text") or "").replace("{reference}", reference)]

    # The body is driven by the approved template, not by the internal decision string,
    # so the two can never disagree.
    if template_id == "claim_approved":
        amount = float(final.get("settlement_amount_eur") or 0.0)
        excess = float(coverage.get("excess_eur") or 0.0)
        lines.append(
            f"Wir überweisen EUR {amount:,.2f} nach Abzug des Selbstbehalts von "
            f"EUR {excess:,.2f}."
            if de
            else f"We will settle EUR {amount:,.2f} after deducting your excess of "
                 f"EUR {excess:,.2f}."
        )
    elif template_id == "coverage_declined":
        clauses = ", ".join(coverage.get("clauses_applied") or []) or "—"
        lines.append(
            f"Maßgeblich ist {clauses} Ihrer Versicherungsbedingungen. Eine Kollegin "
            "bestätigt das noch persönlich, bevor wir abschließen."
            if de
            else f"This follows {clauses} of your policy conditions. A colleague will "
                 "confirm it with you before we close the claim."
        )
    elif template_id == "investigation_opened":
        # No reason given, by design.
        lines.append(
            "Wir melden uns, sobald die Prüfung abgeschlossen ist."
            if de
            else "We will come back to you as soon as that review is complete."
        )
    elif template_id == "more_info_needed":
        pass  # the specific question is appended below
    else:
        reason = CUSTOMER_SAFE_REASON.get(routing.get("reason") or "")
        if reason:
            lines.append(reason["de" if de else "en"])
        else:
            lines.append(
                "Eine Kollegin sieht sich Ihren Fall persönlich an."
                if de
                else "A colleague is looking at your case personally."
            )

    # Where the intake agent raised specific questions, they travel with the message —
    # a claim that needs one more photo should say so, whatever else is happening.
    questions = (outputs.get("intake_orchestrator") or {}).get("customer_questions") or []
    if questions:
        lines.append(
            "Dazu brauchen wir noch: " + questions[0]
            if de
            else "One thing we still need: " + questions[0]
        )

    lines.append(
        "Sie erreichen jederzeit eine Person über den Kontaktlink in Ihrem Schadenkonto."
        if de
        else "You can reach a person at any time using the contact link in your claim."
    )

    return {
        "template_id": template_id,
        "language": language,
        "subject": f"Ihr Schaden {reference}" if de else f"Your claim {reference}",
        "body": "\n\n".join(x for x in lines if x),
        "tone": "plain",
        "route_to_human_offered": True,
    }


# --------------------------------------------------------------------------
# Tool trajectories
# --------------------------------------------------------------------------
def _coverage_question(results: dict[str, Any]) -> dict[str, Any]:
    """Build the grounding question from the claim, the way a real agent would."""
    cov = _d(results, "get_policy_coverage")
    incident = (cov.get("incident") or {}).get("type") or "collision"
    product = cov.get("product") or ""
    own = cov.get("own_damage_claimed")

    if product == "Haftpflicht" and own:
        q = "Is damage to my own vehicle covered under third-party liability cover?"
    elif incident == "hail":
        q = "Is hail damage covered and does an excess apply?"
    elif incident == "glass_breakage":
        q = "Is glass breakage covered and is the excess waived on repair?"
    elif incident in ("parking_collision", "single_vehicle"):
        q = (
            "Is an at-fault collision causing damage to my own vehicle covered, and is "
            "an excess deducted?"
        )
    else:
        q = (
            "Is accidental collision damage to the insured vehicle covered, and is an "
            "excess deducted?"
        )
    return {"question": q}


def _hitl_args(results: dict[str, Any]) -> dict[str, Any]:
    ctx = maybe_run_context()
    outputs = ctx.agent_outputs if ctx else {}
    guard = outputs.get("_guard") or {}
    decision_pkg = outputs.get("decision") or {}
    routing = outputs.get("_routing") or {}
    return {
        "queue": routing.get("queue", "adjuster"),
        "reason": routing.get("reason", "policy_guard_violation"),
        "reason_detail": routing.get("reason_detail")
        or (guard.get("violations") or ["Routed for human review."])[0],
        "proposed_decision": decision_pkg.get("decision") or "Review Required",
        "proposed_amount_eur": float(decision_pkg.get("settlement_amount_eur") or 0.0),
    }


def _comms_args(results: dict[str, Any]) -> dict[str, Any]:
    ctx = maybe_run_context()
    outputs = ctx.agent_outputs if ctx else {}
    final = outputs.get("_final") or {}
    decision = final.get("decision") or "Review Required"
    coverage_status = ((outputs.get("coverage") or {}).get("status")) or ""
    claim_injury = (outputs.get("intake_orchestrator") or {}).get("injury_reported")
    fraud = (outputs.get("fraud_risk") or {}).get("above_threshold")

    if decision == "Approved":
        tpl = "claim_approved"
    elif decision == "Declined" or coverage_status in ("excluded", "lapsed"):
        tpl = "coverage_declined"
    elif claim_injury:
        tpl = "injury_safety_first"
    elif fraud:
        tpl = "investigation_opened"
    elif decision == "Request Information":
        tpl = "more_info_needed"
    else:
        tpl = "claim_in_review"
    return {"template_id": tpl}


ToolStep = tuple[str, Callable[[dict[str, Any]], dict[str, Any]] | None]

PLANS: dict[str, list[ToolStep]] = {
    "intake_orchestrator": [("get_claim_360", None), ("get_outstanding_evidence", None)],
    "document_understanding": [("get_extractions", None)],
    "coverage": [
        ("get_policy_coverage", None),
        ("get_endorsements", None),
        ("search_policy_wording", _coverage_question),
    ],
    "damage_assessment": [("get_photo_findings", None)],
    "repair_estimate": [("get_labour_rate", None), ("calculate_repair_estimate", None)],
    "fraud_risk": [("get_risk_signals", None), ("graph_neighbours", None)],
    "decision": [("assemble_decision_inputs", None)],
    "hitl_coordinator": [("create_review_task", _hitl_args), ("get_queue_state", None)],
    "customer_communication": [("get_template", _comms_args)],
}

SYNTHESISERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "intake_orchestrator": _synth_intake,
    "document_understanding": _synth_document_understanding,
    "coverage": _synth_coverage,
    "damage_assessment": _synth_damage,
    "repair_estimate": _synth_estimate,
    "fraud_risk": _synth_fraud,
    "decision": _synth_decision,
    "hitl_coordinator": _synth_hitl,
    "customer_communication": _synth_comms,
}


# --------------------------------------------------------------------------
class ScriptedLlm(BaseLlm):
    """A BaseLlm that walks a fixed tool trajectory, then answers from the results."""

    agent_key: str = ""

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        results: dict[str, Any] = {}
        called: list[str] = []
        for content in llm_request.contents or []:
            for part in content.parts or []:
                if part.function_response is not None:
                    name = part.function_response.name
                    results[name] = part.function_response.response
                    called.append(name)

        plan = PLANS.get(self.agent_key, [])
        prompt_tokens = _estimate_prompt_tokens(llm_request)

        if len(called) < len(plan):
            tool_name, arg_builder = plan[len(called)]
            args = arg_builder(results) if arg_builder else {}
            payload = types.Part(
                function_call=types.FunctionCall(name=tool_name, args=args)
            )
            yield LlmResponse(
                content=types.Content(role="model", parts=[payload]),
                usage_metadata=_usage(prompt_tokens, 40),
            )
            return

        synth = SYNTHESISERS.get(self.agent_key)
        answer = synth(results) if synth else {"note": "no synthesiser registered"}
        text = json.dumps(answer, ensure_ascii=False, default=str)
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            usage_metadata=_usage(prompt_tokens, max(1, len(text) // 4)),
        )


def _estimate_prompt_tokens(llm_request: LlmRequest) -> int:
    chars = 0
    for content in llm_request.contents or []:
        for part in content.parts or []:
            if part.text:
                chars += len(part.text)
            if part.function_response is not None:
                chars += len(json.dumps(part.function_response.response, default=str))
            if part.function_call is not None:
                chars += len(json.dumps(dict(part.function_call.args or {}), default=str))
    instruction = getattr(getattr(llm_request, "config", None), "system_instruction", None)
    if isinstance(instruction, str):
        chars += len(instruction)
    return max(1, chars // 4)


def _usage(prompt_tokens: int, completion_tokens: int):
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt_tokens,
        candidates_token_count=completion_tokens,
        total_token_count=prompt_tokens + completion_tokens,
    )
