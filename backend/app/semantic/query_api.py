"""The Semantic Query API — the only route to business data.

No agent receives a database handle, a connection string or a SQL string. Every read is
a named query against one of the governed semantic models, and every response carries
its own provenance: which model answered, which grain, which version, and how fresh it
is. Unknown query names are rejected rather than guessed at.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    CoverageAssessment,
    Document,
    Estimate,
    ExtractedField,
    GraphEdge,
    Party,
    Policy,
    ReviewTask,
    RiskSignal,
    Vehicle,
)
from app.semantic.definitions import (
    COMMS_TEMPLATES,
    DEFAULT_LABOUR_RATE_EUR,
    LABOUR_RATES_EUR,
    PANEL_CATALOGUE,
    REASONABLENESS_BANDS,
    SEMANTIC_MODELS,
    STRUCTURAL_PANELS,
)

API_VERSION = "semantic-query-api-1.2.0"


class SemanticQueryError(RuntimeError):
    """Raised when a query is not in the catalogue or its arguments are invalid."""


def _provenance(model: str, rows: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    sm = SEMANTIC_MODELS.get(model)
    return {
        "semantic_model": model,
        "entity": sm.entity if sm else None,
        "grain": sm.grain if sm else None,
        "source_layer": sm.source_layer if sm else None,
        "quality": sm.quality if sm else None,
        "api_version": API_VERSION,
        "row_count": rows,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        **(extra or {}),
    }


def _wrap(model: str, data: Any, rows: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "provenance": _provenance(model, rows, extra)}


# --------------------------------------------------------------------------
# sm_claim_360
# --------------------------------------------------------------------------
def get_claim_360(db: Session, reference: str) -> dict[str, Any]:
    claim = db.get(Claim, reference)
    if claim is None:
        return _wrap("sm_claim_360", None, 0, {"not_found": reference})

    party = db.get(Party, claim.party_id) if claim.party_id else None
    vehicle = db.get(Vehicle, claim.vin) if claim.vin else None
    policy = db.get(Policy, claim.policy_number) if claim.policy_number else None

    docs = db.scalars(
        select(Document).where(Document.claim_reference == reference)
    ).all()
    age_hours = 0.0
    if claim.reported_at:
        reported = claim.reported_at
        if reported.tzinfo is None:
            reported = reported.replace(tzinfo=dt.timezone.utc)
        age_hours = round(
            (dt.datetime.now(dt.timezone.utc) - reported).total_seconds() / 3600.0, 2
        )

    data = {
        "reference": claim.reference,
        "status": claim.status,
        "stage": claim.stage,
        "channel": claim.channel,
        "language": claim.language,
        "age_hours": age_hours,
        "incident": {
            "date": claim.incident_date,
            "city": claim.incident_city,
            "region": claim.incident_region,
            "location": claim.incident_location,
            "type": claim.incident_type,
            "collision_type": claim.collision_type,
        },
        "severity": claim.severity,
        "structural_damage": bool(claim.structural_damage),
        "injury_reported": bool(claim.injury_reported),
        "third_party_involved": bool(claim.third_party_involved),
        "police_report_ref": claim.police_report_ref,
        "evidence_completeness": claim.evidence_completeness,
        "fraud_score": claim.fraud_score,
        "decision": claim.decision,
        "settlement_amount_eur": claim.settlement_amount_eur,
        "assigned_queue": claim.assigned_queue,
        "human_touches": claim.human_touches,
        "policyholder": (
            {
                "party_id": party.party_id,
                "name": f"{party.first_name} {party.last_name}",
                "language": party.language,
                "city": party.city,
                "region": party.region,
                "customer_since": party.customer_since,
                "segment": party.segment,
            }
            if party
            else None
        ),
        "vehicle": (
            {
                "vin": vehicle.vin,
                "plate": vehicle.plate,
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "market_value_eur": vehicle.market_value_eur,
            }
            if vehicle
            else None
        ),
        "policy": (
            {
                "policy_number": policy.policy_number,
                "product": policy.product,
                "status": policy.status,
                "excess_eur": policy.excess_eur,
            }
            if policy
            else None
        ),
        "evidence": [
            {
                "doc_id": d.doc_id,
                "kind": d.kind,
                "doc_type": d.doc_type,
                "filename": d.filename,
                "quality_score": d.quality_score,
                "quarantined": bool(d.quarantined),
                "scan_verdict": d.scan_verdict,
            }
            for d in docs
        ],
    }
    return _wrap("sm_claim_360", data, 1)


def get_claim_timeline(db: Session, reference: str) -> dict[str, Any]:
    claim = db.get(Claim, reference)
    if claim is None:
        return _wrap("sm_claim_360", [], 0, {"not_found": reference})

    events: list[dict[str, Any]] = [
        {"at": claim.reported_at.isoformat() if claim.reported_at else None,
         "event": "fnol_received", "detail": f"Reported via {claim.channel}"}
    ]
    for d in db.scalars(select(Document).where(Document.claim_reference == reference)).all():
        events.append({
            "at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "event": "evidence_received",
            "detail": f"{d.kind} {d.filename or ''} — scan {d.scan_verdict}".strip(),
        })
    for t in db.scalars(select(ReviewTask).where(ReviewTask.claim_reference == reference)).all():
        events.append({
            "at": t.created_at.isoformat() if t.created_at else None,
            "event": "review_task_created",
            "detail": f"{t.queue}: {t.reason}",
        })
        if t.resolved_at:
            events.append({
                "at": t.resolved_at.isoformat(),
                "event": "human_decision",
                "detail": f"{t.decision} by {t.resolved_by}",
            })
    events.sort(key=lambda e: e["at"] or "")
    return _wrap("sm_claim_360", events, len(events))


# --------------------------------------------------------------------------
# sm_coverage
# --------------------------------------------------------------------------
def get_policy_coverage(db: Session, policy_number: str, as_of: str | None = None) -> dict[str, Any]:
    policy = db.get(Policy, policy_number)
    if policy is None:
        return _wrap("sm_coverage", None, 0, {"not_found": policy_number})

    in_force = policy.status == "active"
    if as_of and policy.inception_date and policy.renewal_date:
        in_force = in_force and policy.inception_date <= as_of <= policy.renewal_date

    data = {
        "policy_number": policy.policy_number,
        "product": policy.product,
        "product_label_en": policy.product_label_en,
        "status": policy.status,
        "in_force_on_date_of_loss": in_force,
        "inception_date": policy.inception_date,
        "renewal_date": policy.renewal_date,
        "excess_eur": policy.excess_eur,
        "sum_insured_eur": policy.sum_insured_eur,
        "annual_premium_eur": policy.annual_premium_eur,
        "covers": list(policy.covers or []),
        "exclusions": list(policy.exclusions or []),
        "no_claims_years": policy.no_claims_years,
        "protected_ncd": bool(policy.protected_ncd),
    }
    return _wrap("sm_coverage", data, 1, {"as_of_date_of_loss": as_of})


def get_endorsements(db: Session, policy_number: str) -> dict[str, Any]:
    policy = db.get(Policy, policy_number)
    rows = list(policy.endorsements or []) if policy else []
    return _wrap("sm_coverage", rows, len(rows))


# --------------------------------------------------------------------------
# sm_damage_estimate
# --------------------------------------------------------------------------
def lookup_part_price(panel: str) -> dict[str, Any]:
    spec = PANEL_CATALOGUE.get(panel)
    if spec is None:
        return _wrap("sm_damage_estimate", None, 0, {"unknown_panel": panel})
    data = {
        "panel": panel,
        **spec,
        "structural": panel in STRUCTURAL_PANELS,
        "catalogue": "approved-parts-2026.08",
    }
    return _wrap("sm_damage_estimate", data, 1)


def get_labour_rate(region: str, repairer_tier: str = "tier-1") -> dict[str, Any]:
    rate = LABOUR_RATES_EUR.get(region, DEFAULT_LABOUR_RATE_EUR)
    multiplier = {"tier-1": 1.0, "tier-2": 0.94, "independent": 0.88}.get(repairer_tier, 1.0)
    data = {
        "region": region,
        "repairer_tier": repairer_tier,
        "labour_rate_eur": round(rate * multiplier, 2),
        "base_rate_eur": rate,
        "rate_card": "approved-labour-2026.08",
        "fallback_used": region not in LABOUR_RATES_EUR,
    }
    return _wrap("sm_damage_estimate", data, 1)


def get_panel_catalogue() -> dict[str, dict[str, float]]:
    """Full approved catalogue, passed into the sandbox as inert reference data."""
    return {k: dict(v) for k, v in PANEL_CATALOGUE.items()}


def get_reasonableness_band(severity: str, total_cost: float) -> dict[str, Any]:
    band = REASONABLENESS_BANDS.get(
        "complex" if "complex" in (severity or "").lower() else "simple"
    )
    inside = band["low"] <= total_cost <= band["high"]
    data = {
        "severity": severity,
        "total_cost_eur": round(total_cost, 2),
        "band_low_eur": band["low"],
        "band_high_eur": band["high"],
        "within_band": inside,
        "verdict": "within expected band" if inside else "outlier — flag for review",
    }
    return _wrap("sm_damage_estimate", data, 1)


# --------------------------------------------------------------------------
# sm_risk_signals
# --------------------------------------------------------------------------
def get_risk_signals(db: Session, reference: str) -> dict[str, Any]:
    signals = db.scalars(
        select(RiskSignal).where(RiskSignal.claim_reference == reference)
    ).all()
    rows = [
        {
            "signal_type": s.signal_type,
            "detail": s.detail,
            "weight": s.weight,
            "evidence_ref": s.evidence_ref,
        }
        for s in signals
    ]
    score = min(1.0, round(sum(s.weight or 0.0 for s in signals), 3))
    return _wrap("sm_risk_signals", {"signals": rows, "score": score}, len(rows))


def graph_neighbours(db: Session, node_type: str, node_id: str, max_depth: int = 2) -> dict[str, Any]:
    """Breadth-first walk over the party / vehicle / device / address / repairer graph."""
    seen = {(node_type, node_id)}
    frontier = [(node_type, node_id, 0)]
    out: list[dict[str, Any]] = []

    while frontier:
        st, sid, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        edges = db.scalars(
            select(GraphEdge).where(GraphEdge.src_type == st, GraphEdge.src_id == sid)
        ).all()
        edges += db.scalars(
            select(GraphEdge).where(GraphEdge.dst_type == st, GraphEdge.dst_id == sid)
        ).all()
        for e in edges:
            if e.src_type == st and e.src_id == sid:
                nt, nid = e.dst_type, e.dst_id
            else:
                nt, nid = e.src_type, e.src_id
            if (nt, nid) in seen:
                continue
            seen.add((nt, nid))
            out.append({
                "node_type": nt,
                "node_id": nid,
                "edge": e.edge,
                "distance": depth + 1,
                "weight": e.weight,
                "flagged": bool(e.flagged),
                "note": e.note,
            })
            frontier.append((nt, nid, depth + 1))

    return _wrap(
        "sm_risk_signals",
        {"root": {"node_type": node_type, "node_id": node_id}, "neighbours": out},
        len(out),
        {"flagged_neighbours": sum(1 for n in out if n["flagged"])},
    )


# --------------------------------------------------------------------------
# sm_review_queue
# --------------------------------------------------------------------------
def get_queue_state(db: Session, queue: str | None = None) -> dict[str, Any]:
    stmt = select(ReviewTask).where(ReviewTask.status != "resolved")
    if queue:
        stmt = stmt.where(ReviewTask.queue == queue)
    tasks = db.scalars(stmt).all()
    now = dt.datetime.now(dt.timezone.utc)

    def age_minutes(t: ReviewTask) -> float:
        if not t.created_at:
            return 0.0
        created = t.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.timezone.utc)
        return round((now - created).total_seconds() / 60.0, 1)

    rows = [
        {
            "task_id": t.task_id,
            "claim_reference": t.claim_reference,
            "queue": t.queue,
            "reason": t.reason,
            "authority_required": t.authority_required,
            "authority_limit_eur": t.authority_limit_eur,
            "priority": t.priority,
            "status": t.status,
            "assigned_to": t.assigned_to,
            "proposed_decision": t.proposed_decision,
            "proposed_amount_eur": t.proposed_amount_eur,
            "age_minutes": age_minutes(t),
            "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
            "sla_breached": bool(
                t.sla_due_at
                and (t.sla_due_at.replace(tzinfo=dt.timezone.utc) if t.sla_due_at.tzinfo is None else t.sla_due_at) < now
            ),
        }
        for t in tasks
    ]
    rows.sort(key=lambda r: (r["priority"], -r["age_minutes"]))
    return _wrap("sm_review_queue", rows, len(rows))


# --------------------------------------------------------------------------
# sm_customer_comms
# --------------------------------------------------------------------------
def get_template(template_id: str, language: str = "de") -> dict[str, Any]:
    tpl = COMMS_TEMPLATES.get(template_id)
    if tpl is None:
        return _wrap("sm_customer_comms", None, 0, {"unknown_template": template_id})
    data = {
        "template_id": template_id,
        "language": language if language in tpl else "en",
        "text": tpl.get(language, tpl["en"]),
        "approved": True,
        "template_set": "at-motor-approved-2026.08",
    }
    return _wrap("sm_customer_comms", data, 1)


def list_templates() -> dict[str, Any]:
    rows = [
        {"template_id": k, "languages": sorted(v), "approved": True}
        for k, v in COMMS_TEMPLATES.items()
    ]
    return _wrap("sm_customer_comms", rows, len(rows))


# --------------------------------------------------------------------------
# Extraction reads (Silver layer — extracted vs validated)
# --------------------------------------------------------------------------
def get_extractions(db: Session, reference: str) -> dict[str, Any]:
    docs = db.scalars(select(Document).where(Document.claim_reference == reference)).all()
    rows: list[dict[str, Any]] = []
    for d in docs:
        fields = db.scalars(
            select(ExtractedField).where(ExtractedField.doc_id == d.doc_id)
        ).all()
        rows.append({
            "doc_id": d.doc_id,
            "filename": d.filename,
            "doc_type": d.doc_type,
            "kind": d.kind,
            "quality_score": d.quality_score,
            "quarantined": bool(d.quarantined),
            "sanitised": bool(d.sanitised),
            "scan_verdict": d.scan_verdict,
            "page_count": d.page_count,
            "ocr_text": d.ocr_text,
            "detections": list(d.detections or []),
            "fields": [
                {
                    "field_name": f.field_name,
                    "extracted_value": f.extracted_value,
                    "validated_value": f.validated_value,
                    "confidence": f.confidence,
                    "recovery_action": f.recovery_action,
                    "page": f.page,
                }
                for f in fields
            ],
        })
    return _wrap("sm_claim_360", rows, len(rows))


def get_estimates(db: Session, reference: str) -> dict[str, Any]:
    rows = db.scalars(select(Estimate).where(Estimate.claim_reference == reference)).all()
    return _wrap(
        "sm_damage_estimate",
        [
            {
                "id": e.id,
                "items": e.items,
                "labour_hours": e.labour_hours,
                "labour_rate_eur": e.labour_rate_eur,
                "total_parts": e.total_parts,
                "total_labour": e.total_labour,
                "total_tax": e.total_tax,
                "total_cost": e.total_cost,
                "reasonableness_band": e.reasonableness_band,
                "source": e.source,
                "sandbox_telemetry": e.sandbox_telemetry,
            }
            for e in rows
        ],
        len(rows),
    )


def get_coverage_assessment(db: Session, reference: str) -> dict[str, Any]:
    rows = db.scalars(
        select(CoverageAssessment).where(CoverageAssessment.claim_reference == reference)
    ).all()
    latest = rows[-1] if rows else None
    return _wrap(
        "sm_coverage",
        (
            {
                "status": latest.status,
                "excess_eur": latest.excess_eur,
                "reasoning": latest.reasoning,
                "citations": latest.citations,
                "clauses_applied": latest.clauses_applied,
                "confidence": latest.confidence,
            }
            if latest
            else None
        ),
        1 if latest else 0,
    )


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
QUERY_CATALOGUE: dict[str, dict[str, Any]] = {
    "get_claim_360": {"model": "sm_claim_360", "args": ["reference"], "risk_class": "read-low"},
    "get_claim_timeline": {"model": "sm_claim_360", "args": ["reference"], "risk_class": "read-low"},
    "get_policy_coverage": {"model": "sm_coverage", "args": ["policy_number", "as_of"], "risk_class": "read-medium"},
    "get_endorsements": {"model": "sm_coverage", "args": ["policy_number"], "risk_class": "read-medium"},
    "lookup_part_price": {"model": "sm_damage_estimate", "args": ["panel"], "risk_class": "read-low"},
    "get_labour_rate": {"model": "sm_damage_estimate", "args": ["region", "repairer_tier"], "risk_class": "read-low"},
    "get_reasonableness_band": {"model": "sm_damage_estimate", "args": ["severity", "total_cost"], "risk_class": "read-low"},
    "get_risk_signals": {"model": "sm_risk_signals", "args": ["reference"], "risk_class": "read-high"},
    "graph_neighbours": {"model": "sm_risk_signals", "args": ["node_type", "node_id", "max_depth"], "risk_class": "read-high"},
    "get_queue_state": {"model": "sm_review_queue", "args": ["queue"], "risk_class": "read-low"},
    "get_template": {"model": "sm_customer_comms", "args": ["template_id", "language"], "risk_class": "read-low"},
    "get_extractions": {"model": "sm_claim_360", "args": ["reference"], "risk_class": "read-medium"},
    "get_estimates": {"model": "sm_damage_estimate", "args": ["reference"], "risk_class": "read-low"},
    "get_coverage_assessment": {"model": "sm_coverage", "args": ["reference"], "risk_class": "read-medium"},
}

_DISPATCH = {
    "get_claim_360": get_claim_360,
    "get_claim_timeline": get_claim_timeline,
    "get_policy_coverage": get_policy_coverage,
    "get_endorsements": get_endorsements,
    "lookup_part_price": lookup_part_price,
    "get_labour_rate": get_labour_rate,
    "get_reasonableness_band": get_reasonableness_band,
    "get_risk_signals": get_risk_signals,
    "graph_neighbours": graph_neighbours,
    "get_queue_state": get_queue_state,
    "get_template": get_template,
    "get_extractions": get_extractions,
    "get_estimates": get_estimates,
    "get_coverage_assessment": get_coverage_assessment,
}

_NEEDS_DB = {
    "get_claim_360", "get_claim_timeline", "get_policy_coverage", "get_endorsements",
    "get_risk_signals", "graph_neighbours", "get_queue_state", "get_extractions",
    "get_estimates", "get_coverage_assessment",
}


def execute(query_name: str, db: Session | None = None, **kwargs: Any) -> dict[str, Any]:
    """Single entry point. An unknown query name is an error, never a guess."""
    fn = _DISPATCH.get(query_name)
    if fn is None:
        raise SemanticQueryError(
            f"'{query_name}' is not in the semantic query catalogue. "
            f"Available: {sorted(_DISPATCH)}"
        )
    if query_name in _NEEDS_DB:
        if db is None:
            raise SemanticQueryError(f"'{query_name}' requires a database session.")
        return fn(db, **kwargs)
    return fn(**kwargs)
