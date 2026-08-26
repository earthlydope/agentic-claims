"""The typed tool catalog.

Typed business tools come first, everywhere. No agent is ever handed generic SQL, a
shell, or unrestricted HTTP. Every tool below is a narrow, named capability with a risk
class, and each one reads through the Semantic Query API rather than touching a table.

The claim under work is taken from the run context, not from the model's arguments, so an
agent cannot reach a different claim by asking nicely.
"""

from __future__ import annotations

from typing import Any

from app.agents.harness import run_context
from app.semantic import knowledge, query_api
from app.semantic.definitions import PANEL_CATALOGUE, STRUCTURAL_PANELS
from app.zero_trust.sandbox import sandboxed_estimate_calculation

# risk class per tool, carried on every call alongside claim_id, run_id, agent_id
TOOL_RISK_CLASS: dict[str, str] = {
    "get_claim_360": "read-low",
    "get_claim_timeline": "read-low",
    "get_outstanding_evidence": "read-low",
    "get_extractions": "read-medium",
    "get_policy_coverage": "read-medium",
    "get_endorsements": "read-medium",
    "search_policy_wording": "read-medium",
    "get_photo_findings": "read-medium",
    "lookup_part_price": "read-low",
    "get_labour_rate": "read-low",
    "calculate_repair_estimate": "compute-sandboxed",
    "get_reasonableness_band": "read-low",
    "get_risk_signals": "read-high",
    "graph_neighbours": "read-high",
    "assemble_decision_inputs": "read-high",
    "create_review_task": "write-hitl",
    "get_queue_state": "read-low",
    "get_template": "read-low",
    "get_vehicle_valuation": "read-medium",
    "check_total_loss_threshold": "read-medium",
    "get_liability_position": "read-medium",
    "assess_recovery": "read-medium",
}


# --------------------------------------------------------------------------
# Intake Orchestrator
# --------------------------------------------------------------------------
def get_claim_360() -> dict[str, Any]:
    """Read the agreed claim record: status, stage, incident, policyholder, vehicle,
    policy summary and the evidence received so far.

    Returns the sm_claim_360 semantic model view of the claim currently under work.
    """
    ctx = run_context()
    return query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)


def get_claim_timeline() -> dict[str, Any]:
    """Read the ordered history of the claim: notification, evidence, review tasks and
    human decisions."""
    ctx = run_context()
    return query_api.execute("get_claim_timeline", db=ctx.db, reference=ctx.claim_reference)


def get_outstanding_evidence() -> dict[str, Any]:
    """List the evidence still required for this claim, and the specific question to ask
    the customer for each item. Never re-asks a fact that has already been validated."""
    ctx = raw = run_context()
    ext = query_api.execute("get_extractions", db=raw.db, reference=raw.claim_reference)
    claim = query_api.execute("get_claim_360", db=raw.db, reference=raw.claim_reference)
    data = claim.get("data") or {}

    validated: set[str] = set()
    needs_confirmation: list[dict[str, Any]] = []
    unreadable: list[dict[str, Any]] = []

    for doc in ext.get("data") or []:
        if (doc.get("quality_score") or 1.0) < 0.55:
            unreadable.append({
                "doc_id": doc["doc_id"],
                "filename": doc.get("filename"),
                "quality_score": doc.get("quality_score"),
                "ask": (
                    "The photo of the tailgate is too blurred to measure the panel edges. "
                    "Please send one more photo of the same panel from about two metres "
                    "back, in daylight."
                ),
            })
        for f in doc.get("fields") or []:
            if f.get("validated_value"):
                validated.add(f["field_name"])
            elif (f.get("confidence") or 0.0) < 0.85:
                needs_confirmation.append({
                    "field_name": f["field_name"],
                    "read_as": f.get("extracted_value"),
                    "confidence": f.get("confidence"),
                    "ask": (
                        f"We read the {f['field_name'].replace('_', ' ')} as "
                        f"\"{f.get('extracted_value')}\" — is that right?"
                    ),
                })

    missing: list[str] = []
    have_photo = any(d.get("kind") == "photo" for d in (ext.get("data") or []))
    if not have_photo:
        missing.append("at least one photo of the damage")
    if data.get("injury_reported") and not data.get("police_report_ref"):
        missing.append("police report reference (required where injury is reported)")

    completeness = round(
        max(
            0.0,
            1.0
            - 0.25 * len(missing)
            - 0.10 * len(needs_confirmation)
            - 0.15 * len(unreadable),
        ),
        2,
    )

    return {
        "data": {
            "validated_fields": sorted(validated),
            "needs_confirmation": needs_confirmation,
            "unreadable_evidence": unreadable,
            "missing": missing,
            "evidence_completeness": completeness,
        },
        "provenance": {
            "semantic_model": "sm_claim_360",
            "derivation": "recovery rules — accept / confirm / re-ask / escalate",
        },
    }


# --------------------------------------------------------------------------
# Document Understanding
# --------------------------------------------------------------------------
def get_extractions() -> dict[str, Any]:
    """Read the document-processing output for this claim: every document with its type,
    quality score, and each extracted field with its own confidence.

    This tool is read-only. It cannot change the claim.
    """
    ctx = run_context()
    return query_api.execute("get_extractions", db=ctx.db, reference=ctx.claim_reference)


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------
def get_policy_coverage() -> dict[str, Any]:
    """Read the policy position on the date of loss: product, in-force status, excess,
    active covers, exclusions and sum insured."""
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    data = claim.get("data") or {}
    policy_number = (data.get("policy") or {}).get("policy_number")
    if not policy_number:
        return {"data": None, "provenance": {"error": "no policy attached to this claim"}}

    result = query_api.execute(
        "get_policy_coverage",
        db=ctx.db,
        policy_number=policy_number,
        as_of=(data.get("incident") or {}).get("date"),
    )

    # A coverage view is the policy position *against a specific loss*, so the incident
    # facts the position is being tested against travel with it.
    incident = data.get("incident") or {}
    result["data"] = {
        **(result.get("data") or {}),
        "incident": incident,
        "own_damage_claimed": not data.get("third_party_involved")
        or incident.get("type") in ("parking_collision", "single_vehicle", "hail", "glass_breakage"),
        "injury_reported": bool(data.get("injury_reported")),
        "at_fault": incident.get("type") in ("parking_collision", "single_vehicle"),
    }
    return result


def get_endorsements() -> dict[str, Any]:
    """Read the endorsements attached to the policy on this claim."""
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    policy_number = ((claim.get("data") or {}).get("policy") or {}).get("policy_number")
    if not policy_number:
        return {"data": [], "provenance": {"error": "no policy attached"}}
    return query_api.execute("get_endorsements", db=ctx.db, policy_number=policy_number)


def search_policy_wording(question: str) -> dict[str, Any]:
    """Search the approved policy wording, endorsements and claims procedures for the
    clauses that answer a question, filtered to this policy's product.

    Returns whole clauses with a clause reference, section and page. An empty result is a
    real answer: it means no authoritative clause was found and the agent must abstain
    rather than fill the gap.

    Args:
        question: The coverage question to ground, in German or English.
    """
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    data = claim.get("data") or {}
    product = (data.get("policy") or {}).get("product")
    language = data.get("language") or "en"

    results = knowledge.retrieve(question, product=product, language=language, top_k=3)
    citations = knowledge.citations_for(results, language=language)

    return {
        "data": {
            "question": question,
            "product_filter": product,
            "found": len(citations),
            "citations": citations,
            "abstain": len(citations) == 0,
            "abstain_reason": (
                "No authoritative clause matched. Rewrite the query or escalate — do not "
                "answer from general knowledge."
                if not citations
                else None
            ),
        },
        "provenance": {**knowledge.corpus_summary(), "filter_applied_during_retrieval": True},
    }


# --------------------------------------------------------------------------
# Damage Assessment
# --------------------------------------------------------------------------
def get_photo_findings() -> dict[str, Any]:
    """Read the approved photo findings for this claim: which panels were detected, the
    action each needs, the detection confidence, and the photo quality it came from.

    Read-only. There are no settlement tools in this scope.
    """
    ctx = run_context()
    ext = query_api.execute("get_extractions", db=ctx.db, reference=ctx.claim_reference)

    panels: list[dict[str, Any]] = []
    low_quality: list[dict[str, Any]] = []
    seen: set[str] = set()

    for doc in ext.get("data") or []:
        if doc.get("kind") != "photo":
            continue
        quality = doc.get("quality_score") or 0.0
        if quality < 0.55:
            low_quality.append({
                "doc_id": doc["doc_id"],
                "filename": doc.get("filename"),
                "quality_score": quality,
            })
        for det in doc.get("detections") or []:
            key = det.get("panel")
            if not key or key in seen:
                continue
            seen.add(key)
            panels.append({
                **det,
                "structural": key in STRUCTURAL_PANELS,
                "from_doc": doc["doc_id"],
                "photo_quality": quality,
                "in_catalogue": key in PANEL_CATALOGUE,
            })

    structural = any(p["structural"] for p in panels)
    severity = "complex" if structural or len(panels) >= 4 else "simple"
    missing_views = [
        "a straight-on view of the damaged panel from about two metres"
        for _ in low_quality
    ]

    return {
        "data": {
            "panels": panels,
            "panel_count": len(panels),
            "structural_damage": structural,
            "severity": severity,
            "low_quality_photos": low_quality,
            "missing_views": missing_views,
            "severity_basis": (
                "structural panel detected" if structural
                else f"{len(panels)} panel(s) affected"
            ),
        },
        "provenance": {"semantic_model": "sm_damage_estimate", "source": "approved photo findings"},
    }


def lookup_part_price(panel: str) -> dict[str, Any]:
    """Look up the approved part price and standard hours for one panel.

    Args:
        panel: Panel code, for example bumper_front or door_front_left.
    """
    return query_api.execute("lookup_part_price", panel=panel)


# --------------------------------------------------------------------------
# Repair Estimate
# --------------------------------------------------------------------------
def get_labour_rate() -> dict[str, Any]:
    """Read the approved labour rate for the region this incident occurred in."""
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    region = ((claim.get("data") or {}).get("incident") or {}).get("region") or ""
    return query_api.execute("get_labour_rate", region=region, repairer_tier="tier-1")


def calculate_repair_estimate() -> dict[str, Any]:
    """Build the itemised repair estimate from the approved panel findings, the approved
    parts catalogue and the approved regional labour rate.

    The arithmetic runs inside the managed sandbox: no secrets, no network egress, no
    filesystem. The returned isolation telemetry is proof of that, not an assertion.
    """
    ctx = run_context()
    findings = get_photo_findings()["data"]
    rate_row = get_labour_rate()["data"] or {}
    labour_rate = float(rate_row.get("labour_rate_eur") or 125.0)

    panels = [
        {"part": p["panel"], "action": p.get("action", "repair"), "paint": bool(p.get("paint"))}
        for p in findings["panels"]
        if p.get("in_catalogue")
    ]

    estimate = sandboxed_estimate_calculation(
        panels=panels,
        panel_catalogue=query_api.get_panel_catalogue(),
        labour_rate_eur=labour_rate,
    )

    band = query_api.execute(
        "get_reasonableness_band",
        severity=findings["severity"],
        total_cost=float(estimate.get("total_cost") or 0.0),
    )["data"]

    return {
        "data": {
            **estimate,
            "region": rate_row.get("region"),
            "severity": findings["severity"],
            "structural_damage": findings["structural_damage"],
            "reasonableness": band,
        },
        "provenance": {
            "semantic_model": "sm_damage_estimate",
            "catalogue": "approved-parts-2026.08",
            "rate_card": rate_row.get("rate_card"),
            "computed_in": "managed sandbox",
        },
    }


def get_reasonableness_band(severity: str, total_cost: float) -> dict[str, Any]:
    """Check an estimate total against the expected band for its severity.

    Args:
        severity: simple or complex.
        total_cost: The estimate total in EUR.
    """
    return query_api.execute(
        "get_reasonableness_band", severity=severity, total_cost=total_cost
    )


# --------------------------------------------------------------------------
# Fraud & Risk
# --------------------------------------------------------------------------
def get_risk_signals() -> dict[str, Any]:
    """Read the duplicate, pattern, velocity and relationship signals recorded against
    this claim. Read-only fraud features."""
    ctx = run_context()
    return query_api.execute("get_risk_signals", db=ctx.db, reference=ctx.claim_reference)


def graph_neighbours() -> dict[str, Any]:
    """Walk the party, vehicle, device, address and repairer graph around this claim and
    report the neighbourhood, including any node already flagged."""
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    party = ((claim.get("data") or {}).get("policyholder") or {}).get("party_id")
    if not party:
        return {"data": {"neighbours": []}, "provenance": {"error": "no party on claim"}}
    return query_api.execute(
        "graph_neighbours", db=ctx.db, node_type="party", node_id=party, max_depth=2
    )


# --------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------
def assemble_decision_inputs() -> dict[str, Any]:
    """Read the approved evidence and context needed to propose one decision: the claim
    record, the coverage position, the estimate and the risk picture.

    This tool cannot write to the claims core.
    """
    ctx = run_context()
    outputs = ctx.agent_outputs
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    return {
        "data": {
            "claim": claim.get("data"),
            "coverage": outputs.get("coverage"),
            "damage": outputs.get("damage_assessment"),
            "estimate": outputs.get("repair_estimate"),
            "risk": outputs.get("fraud_risk"),
            "evidence": outputs.get("intake_orchestrator", {}).get("evidence"),
            "document_understanding": outputs.get("document_understanding"),
        },
        "provenance": {
            "assembled_from": sorted(outputs),
            "note": "Read-only. The Decision agent proposes; it never writes.",
        },
    }


# --------------------------------------------------------------------------
# HITL Coordinator
# --------------------------------------------------------------------------
def create_review_task(
    queue: str, reason: str, reason_detail: str, proposed_decision: str,
    proposed_amount_eur: float,
) -> dict[str, Any]:
    """Create a human review task and place it on a queue.

    Args:
        queue: handler, coverage, assessment, supervisor, injury, siu or security.
        reason: A short reason code, for example ceiling_exceeded or injury_reported.
        reason_detail: One sentence an adjuster can read to understand why it arrived.
        proposed_decision: The decision the agent recommended before the guard ran.
        proposed_amount_eur: The amount recommended, in EUR.
    """
    import datetime as dt
    import secrets

    from app.config import AUTHORITY_LIMITS_EUR
    from app.models import ReviewTask

    ctx = run_context()
    authority = (
        "team_leader"
        if proposed_amount_eur > AUTHORITY_LIMITS_EUR["claims_handler"]
        else "claims_handler"
    )
    if queue == "siu":
        authority = "siu_investigator"
    elif queue == "assessment":
        authority = "motor_assessor"

    task = ReviewTask(
        task_id=f"TSK-{secrets.token_hex(4).upper()}",
        claim_reference=ctx.claim_reference,
        reason=reason,
        reason_detail=reason_detail,
        queue=queue,
        authority_required=authority,
        authority_limit_eur=AUTHORITY_LIMITS_EUR.get(authority, 0.0),
        priority=1 if queue in ("siu", "injury") else 2,
        status="open",
        proposed_decision=proposed_decision,
        proposed_amount_eur=round(float(proposed_amount_eur or 0.0), 2),
        sla_due_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24),
    )
    ctx.db.add(task)
    ctx.db.commit()

    return {
        "data": {
            "task_id": task.task_id,
            "queue": task.queue,
            "authority_required": task.authority_required,
            "authority_limit_eur": task.authority_limit_eur,
            "sla_due_at": task.sla_due_at.isoformat(),
        },
        "provenance": {"semantic_model": "sm_review_queue"},
    }


def get_queue_state(queue: str = "") -> dict[str, Any]:
    """Read the current state of the human review queues.

    Args:
        queue: Optional queue name to filter to.
    """
    ctx = run_context()
    return query_api.execute("get_queue_state", db=ctx.db, queue=queue or None)


# --------------------------------------------------------------------------
# Customer Communication
# --------------------------------------------------------------------------
def get_template(template_id: str) -> dict[str, Any]:
    """Read an approved customer communication template in the customer's language.

    Args:
        template_id: One of claim_approved, claim_in_review, more_info_needed,
            coverage_declined, injury_safety_first, investigation_opened.
    """
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    language = (claim.get("data") or {}).get("language") or "de"
    return query_api.execute("get_template", template_id=template_id, language=language)




# --------------------------------------------------------------------------
# Repairability (total loss)
# --------------------------------------------------------------------------
def get_vehicle_valuation() -> dict[str, Any]:
    """Read the vehicle's replacement value on the date of loss, with age and mileage.

    This is the figure the total-loss test runs against — what it would cost to put the
    policyholder back in an equivalent vehicle, not what they paid for it.
    """
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    data = claim.get("data") or {}
    vehicle = data.get("vehicle") or {}
    policy = data.get("policy") or {}

    incident_year = int(str((data.get("incident") or {}).get("date") or "2026")[:4])
    year = int(vehicle.get("year") or incident_year)
    age_years = max(0, incident_year - year)

    return {
        "data": {
            "vin": vehicle.get("vin"),
            "make": vehicle.get("make"),
            "model": vehicle.get("model"),
            "year": year,
            "age_years": age_years,
            "replacement_value_eur": float(vehicle.get("market_value_eur") or 0.0),
            "sum_insured_eur": float(policy.get("sum_insured_eur") or 0.0),
            "new_for_old_available": age_years <= 2,
            "valuation_basis": "Wiederbeschaffungswert — trade replacement value",
        },
        "provenance": {
            "semantic_model": "sm_claim_360",
            "valuation_source": "vehicle-valuation-2026.08",
        },
    }


def check_total_loss_threshold() -> dict[str, Any]:
    """Run the total-loss test: repair cost against replacement value.

    Where repair cost exceeds the policy threshold the loss is treated as a total loss and
    the indemnity is the replacement value less the salvage, rather than the repair bill.
    The threshold is policy wording, not a setting — it comes from the clause.
    """
    ctx = run_context()
    valuation = get_vehicle_valuation()["data"]
    estimate = (ctx.agent_outputs.get("repair_estimate") or {})
    repair_cost = float(estimate.get("total_cost") or 0.0)
    replacement = float(valuation.get("replacement_value_eur") or 0.0)

    threshold = 0.70          # AKB-§11.2
    ratio = round(repair_cost / replacement, 4) if replacement else 0.0

    if not replacement or not repair_cost:
        verdict = "borderline"
    elif ratio > threshold:
        verdict = "total_loss"
    elif ratio > threshold - 0.10:
        verdict = "borderline"
    else:
        verdict = "economically_repairable"

    # Salvage retains value even on a total loss, and the indemnity is net of it.
    residual = round(replacement * 0.14, 2) if verdict == "total_loss" else 0.0
    payable = round(max(replacement - residual, 0.0), 2) if verdict == "total_loss" else 0.0

    return {
        "data": {
            "verdict": verdict,
            "repair_cost_eur": round(repair_cost, 2),
            "replacement_value_eur": round(replacement, 2),
            "ratio": ratio,
            "threshold": threshold,
            "residual_value_eur": residual,
            "payable_on_total_loss_eur": payable,
            "basis": (
                f"Repair cost is {ratio * 100:.1f}% of replacement value against a "
                f"{threshold * 100:.0f}% threshold."
            ),
        },
        "provenance": {
            "semantic_model": "sm_damage_estimate",
            "clause": "AKB-§11.2",
            "note": "The threshold is policy wording, not a configurable setting.",
        },
    }


# --------------------------------------------------------------------------
# Recovery (Regress)
# --------------------------------------------------------------------------
def get_liability_position() -> dict[str, Any]:
    """Read who was at fault and whether an identified third party was involved.

    This is what decides whether there is anyone to recover from at all.
    """
    ctx = run_context()
    claim = query_api.execute("get_claim_360", db=ctx.db, reference=ctx.claim_reference)
    data = claim.get("data") or {}
    incident = data.get("incident") or {}
    docs = query_api.execute("get_extractions", db=ctx.db, reference=ctx.claim_reference)

    at_fault_party = None
    for doc in docs.get("data") or []:
        for field in doc.get("fields") or []:
            if field.get("field_name") == "at_fault_party":
                at_fault_party = field.get("extracted_value")

    self_inflicted = incident.get("type") in (
        "parking_collision", "single_vehicle", "hail", "glass_breakage", "wild_game",
    )

    return {
        "data": {
            "incident_type": incident.get("type"),
            "third_party_involved": bool(data.get("third_party_involved")),
            "police_report_ref": data.get("police_report_ref"),
            "at_fault_party": at_fault_party,
            "self_inflicted": self_inflicted,
            "settlement_paid_eur": float(data.get("settlement_amount_eur") or 0.0),
            "excess_eur": float((data.get("policy") or {}).get("excess_eur") or 0.0),
        },
        "provenance": {"semantic_model": "sm_claim_360"},
    }


def assess_recovery() -> dict[str, Any]:
    """Work out whether a recovery is worth pursuing, and against whom.

    A recovery that costs more to pursue than it returns is not a recovery. The threshold
    below is the point at which the file is worth a handler's time.
    """
    position = get_liability_position()["data"]
    paid = float(position.get("settlement_paid_eur") or 0.0)
    excess = float(position.get("excess_eur") or 0.0)
    min_worth_pursuing = 350.0

    if position.get("self_inflicted") or not position.get("third_party_involved"):
        basis, prospects, recoverable = "no_recoverable_party", "none", 0.0
    elif position.get("at_fault_party") == "third_party" and position.get("police_report_ref"):
        basis, prospects = "third_party_at_fault", "strong"
        recoverable = round(paid + excess, 2)
    elif position.get("at_fault_party") == "third_party":
        basis, prospects = "third_party_at_fault", "moderate"
        recoverable = round((paid + excess) * 0.8, 2)
    elif position.get("third_party_involved"):
        basis, prospects = "shared_liability", "moderate"
        recoverable = round((paid + excess) * 0.5, 2)
    else:
        basis, prospects, recoverable = "unknown", "weak", 0.0

    worth_it = recoverable >= min_worth_pursuing
    if recoverable and not worth_it:
        prospects = "weak"

    return {
        "data": {
            "recoverable": bool(worth_it and basis != "no_recoverable_party"),
            "basis": basis,
            "recoverable_amount_eur": recoverable,
            "prospects": prospects,
            "worth_pursuing": worth_it,
            "minimum_worth_pursuing_eur": min_worth_pursuing,
            "next_action": (
                "Open a recovery file against the third-party insurer and reclaim the "
                "excess for the customer."
                if worth_it and basis == "third_party_at_fault"
                else "Approach the third-party insurer on a shared-liability basis."
                if worth_it and basis == "shared_liability"
                else "Record that there is no recoverable party and close the recovery."
            ),
            "position": position,
        },
        "provenance": {
            "semantic_model": "sm_claim_360",
            "note": "Recovery is assessed after settlement, on what was actually paid.",
        },
    }


# --------------------------------------------------------------------------
# Per-agent tool scope. An agent physically receives only these callables.
# --------------------------------------------------------------------------
TOOL_SCOPE: dict[str, list] = {
    "intake_orchestrator": [get_claim_360, get_claim_timeline, get_outstanding_evidence],
    "document_understanding": [get_extractions],
    "coverage": [get_policy_coverage, get_endorsements, search_policy_wording],
    "damage_assessment": [get_photo_findings, lookup_part_price],
    "repair_estimate": [get_labour_rate, calculate_repair_estimate, get_reasonableness_band],
    "fraud_risk": [get_risk_signals, graph_neighbours],
    "total_loss": [get_vehicle_valuation, check_total_loss_threshold, search_policy_wording],
    "decision": [assemble_decision_inputs],
    "recovery": [get_liability_position, assess_recovery],
    "hitl_coordinator": [create_review_task, get_queue_state],
    "customer_communication": [get_template],
}

TOOL_NAMES_BY_AGENT: dict[str, set[str]] = {
    key: {fn.__name__ for fn in fns} for key, fns in TOOL_SCOPE.items()
}
