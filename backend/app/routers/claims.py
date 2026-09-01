"""Claims: the customer journey in, the console view out, and the run stream."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import secrets
from typing import Any

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import run_claim
from app.db import SessionLocal, get_db
from app.models import (
    Claim,
    CoverageAssessment,
    Document,
    Estimate,
    ExtractedField,
    Party,
    Policy,
    ReviewTask,
    RiskSignal,
    Vehicle,
)
from app.claimants import scenario_by_key
from app.lifecycle import status_meta
from app.semantic import query_api
from app.services.metrics import messages_for
from app.services.ingest import ingest
from app.services.preflight import preflight_upload, recovery_action, safe_link_check
from app.zero_trust.semantic_gateway import PolicyAction, PromptFirewall, Surface

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.get("")
def list_claims(
    live_only: bool = False,
    status: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Claim).order_by(Claim.reported_at.desc())
    if live_only:
        stmt = stmt.where(Claim.scenario_key.isnot(None))
    if status:
        stmt = stmt.where(Claim.status == status)
    claims = db.scalars(stmt.limit(limit)).all()

    parties = {p.party_id: p for p in db.scalars(select(Party)).all()}
    vehicles = {v.vin: v for v in db.scalars(select(Vehicle)).all()}
    policies = {p.policy_number: p for p in db.scalars(select(Policy)).all()}
    open_tasks: dict[str, ReviewTask] = {}
    for t in db.scalars(select(ReviewTask).where(ReviewTask.status != "resolved")).all():
        open_tasks.setdefault(t.claim_reference, t)

    return {
        "claims": [_claim_summary(c, parties, vehicles, policies, open_tasks) for c in claims],
        "count": len(claims),
    }


def _claim_summary(c, parties, vehicles, policies, open_tasks) -> dict[str, Any]:
    party = parties.get(c.party_id)
    vehicle = vehicles.get(c.vin)
    policy = policies.get(c.policy_number)
    task = open_tasks.get(c.reference)
    scenario = scenario_by_key(c.scenario_key) if c.scenario_key else None
    meta = status_meta(c.status)
    return {
        "reference": c.reference,
        "status": c.status,
        # The status in both languages, so a view can label it without a second lookup.
        "status_meta": meta,
        "status_tone": meta.get("tone"),
        "stage": c.stage,
        "decision": c.decision,
        "settlement_amount_eur": c.settlement_amount_eur,
        "severity": c.severity,
        "structural_damage": bool(c.structural_damage),
        "injury_reported": bool(c.injury_reported),
        "fraud_score": c.fraud_score,
        "evidence_completeness": c.evidence_completeness,
        "straight_through": bool(c.straight_through),
        "human_touches": c.human_touches,
        "channel": c.channel,
        "language": c.language,
        "incident_type": c.incident_type,
        "incident_region": c.incident_region,
        "incident_city": c.incident_city,
        "incident_date": c.incident_date,
        "reported_at": c.reported_at.isoformat() if c.reported_at else None,
        "sla_due_at": c.sla_due_at.isoformat() if c.sla_due_at else None,
        "assigned_queue": c.assigned_queue,
        "assigned_to": c.assigned_to,
        "scenario_key": c.scenario_key,
        "scenario": scenario,
        "is_live_demo": bool(c.scenario_key),
        "policyholder": (
            {"party_id": party.party_id, "name": f"{party.first_name} {party.last_name}",
             "city": party.city, "region": party.region, "language": party.language,
             "segment": party.segment, "customer_since": party.customer_since}
            if party else None
        ),
        "vehicle": (
            {"vin": vehicle.vin, "plate": vehicle.plate, "make": vehicle.make,
             "model": vehicle.model, "year": vehicle.year,
             "market_value_eur": vehicle.market_value_eur}
            if vehicle else None
        ),
        "policy": (
            {"policy_number": policy.policy_number, "product": policy.product,
             "product_label_en": policy.product_label_en, "status": policy.status,
             "excess_eur": policy.excess_eur, "annual_premium_eur": policy.annual_premium_eur}
            if policy else None
        ),
        "open_task": (
            {"task_id": task.task_id, "queue": task.queue, "reason": task.reason,
             "authority_required": task.authority_required,
             "proposed_amount_eur": task.proposed_amount_eur}
            if task else None
        ),
    }


@router.get("/{reference}")
def get_claim(reference: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    claim = db.get(Claim, reference)
    if claim is None:
        raise HTTPException(404, f"Claim {reference} not found.")

    parties = {p.party_id: p for p in db.scalars(select(Party)).all()}
    vehicles = {v.vin: v for v in db.scalars(select(Vehicle)).all()}
    policies = {p.policy_number: p for p in db.scalars(select(Policy)).all()}
    open_tasks = {
        t.claim_reference: t
        for t in db.scalars(select(ReviewTask).where(ReviewTask.status != "resolved")).all()
    }

    docs = db.scalars(select(Document).where(Document.claim_reference == reference)).all()
    documents = []
    for d in docs:
        fields = db.scalars(
            select(ExtractedField).where(ExtractedField.doc_id == d.doc_id)
        ).all()
        documents.append({
            "doc_id": d.doc_id, "kind": d.kind, "filename": d.filename,
            "mime_type": d.mime_type, "size_bytes": d.size_bytes,
            "page_count": d.page_count, "sha256": d.sha256, "doc_type": d.doc_type,
            "quality_score": d.quality_score,
            "quality_action": recovery_action(d.quality_score or 0.0),
            "scan_verdict": d.scan_verdict, "quarantined": bool(d.quarantined),
            "sanitised": bool(d.sanitised), "duplicate_of": d.duplicate_of,
            "preflight_notes": d.preflight_notes or [],
            "detections": d.detections or [],
            "ocr_text": d.ocr_text,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "fields": [
                {"field_name": f.field_name, "extracted_value": f.extracted_value,
                 "validated_value": f.validated_value, "confidence": f.confidence,
                 "recovery_action": f.recovery_action, "page": f.page}
                for f in fields
            ],
        })

    coverage = db.scalars(
        select(CoverageAssessment).where(CoverageAssessment.claim_reference == reference)
        .order_by(CoverageAssessment.id.desc())
    ).first()
    estimate = db.scalars(
        select(Estimate).where(Estimate.claim_reference == reference)
        .order_by(Estimate.id.desc())
    ).first()
    signals = db.scalars(
        select(RiskSignal).where(RiskSignal.claim_reference == reference)
    ).all()
    tasks = db.scalars(
        select(ReviewTask).where(ReviewTask.claim_reference == reference)
    ).all()

    return {
        "claim": {
            **_claim_summary(claim, parties, vehicles, policies, open_tasks),
            "fnol_text": claim.fnol_text,
            "incident_location": claim.incident_location,
            "collision_type": claim.collision_type,
            "third_party_involved": bool(claim.third_party_involved),
            "police_report_ref": claim.police_report_ref,
        },
        "documents": documents,
        "coverage": (
            {"status": coverage.status, "excess_eur": coverage.excess_eur,
             "reasoning": coverage.reasoning, "citations": coverage.citations or [],
             "clauses_applied": coverage.clauses_applied or [],
             "confidence": coverage.confidence}
            if coverage else None
        ),
        "estimate": (
            {"items": estimate.items or [], "labour_hours": estimate.labour_hours,
             "labour_rate_eur": estimate.labour_rate_eur,
             "total_parts": estimate.total_parts, "total_labour": estimate.total_labour,
             "total_tax": estimate.total_tax, "total_cost": estimate.total_cost,
             "reasonableness_band": estimate.reasonableness_band,
             "sandbox_telemetry": estimate.sandbox_telemetry or {}}
            if estimate else None
        ),
        "risk": {
            "score": round(min(1.0, sum(s.weight or 0.0 for s in signals)), 3),
            "signals": [
                {"signal_type": s.signal_type, "detail": s.detail, "weight": s.weight,
                 "evidence_ref": s.evidence_ref}
                for s in signals
            ],
        },
        "tasks": [
            {"task_id": t.task_id, "queue": t.queue, "reason": t.reason,
             "reason_detail": t.reason_detail, "status": t.status,
             "authority_required": t.authority_required,
             "proposed_decision": t.proposed_decision,
             "proposed_amount_eur": t.proposed_amount_eur, "decision": t.decision,
             "decision_note": t.decision_note, "resolved_by": t.resolved_by,
             "approval_ref": t.approval_ref,
             "created_at": t.created_at.isoformat() if t.created_at else None,
             "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None}
            for t in tasks
        ],
        "messages": messages_for(db, reference),
        "timeline": query_api.execute("get_claim_timeline", db=db, reference=reference)["data"],
        # The trace of the last analysis, so opening a claim that was already worked shows
        # what each stage found rather than an empty panel. The live stream replaces this
        # while a run is in flight.
        "trace": _last_trace(db, reference),
    }


def _last_trace(db: Session, reference: str) -> list[dict[str, Any]]:
    """The most recent recorded run on a claim, as trace events."""
    from app.models import AgentRun

    run = db.scalars(
        select(AgentRun).where(AgentRun.claim_reference == reference)
        .order_by(AgentRun.started_at.desc()).limit(1)
    ).first()
    if run is None:
        return []
    trace = run.trace
    return trace if isinstance(trace, list) else []


# --------------------------------------------------------------------------
# Customer intake
# --------------------------------------------------------------------------
class EvidenceItem(BaseModel):
    kind: str = Field(description="photo, pdf or link")
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int = 1_200_000
    page_count: int = 1
    quality_score: float = 0.9
    doc_type: str = "photo"
    ocr_text: str | None = None
    source_url: str | None = None
    detections: list[dict[str, Any]] = []


class IntakeRequest(BaseModel):
    policy_number: str
    fnol_text: str
    incident_date: str
    incident_city: str = ""
    incident_region: str = "Wien"
    incident_location: str = ""
    incident_type: str = "parking_collision"
    collision_type: str = ""
    language: str = "de"
    channel: str = "web"
    injury_reported: bool = False
    third_party_involved: bool = False
    police_report_ref: str | None = None
    evidence: list[EvidenceItem] = []


@router.post("/intake")
def intake(
    body: IntakeRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """File a claim. Everything is screened before a model ever sees it."""
    policy = db.get(Policy, body.policy_number)
    if policy is None:
        raise HTTPException(404, f"Policy {body.policy_number} not found.")

    # Step 1 — the inbound firewall, before anything is written.
    fw = PromptFirewall.inspect(body.fnol_text, Surface.USER_MESSAGE)
    if fw.action is PolicyAction.BLOCK:
        return {
            "accepted": False,
            "blocked_by": "semantic_gateway.prompt_firewall",
            "firewall": fw.as_dict(),
            "message": (
                "This notification was stopped at the gateway before a model saw it and "
                "before a claim record was created."
            ),
        }

    # Step 2 — preflight every item of evidence.
    seen: dict[str, str] = {}
    accepted: list[EvidenceItem] = []
    evidence_report: list[dict[str, Any]] = []

    for item in body.evidence:
        if item.kind == "link":
            link = safe_link_check(item.source_url or "")
            evidence_report.append({
                "kind": "link", "source_url": item.source_url,
                "verdict": link.verdict, "accepted": link.accepted,
                "checks": link.checks, "notes": link.notes,
            })
            if link.accepted:
                accepted.append(item)
            continue

        payload = (item.ocr_text or item.filename or "evidence").encode("utf-8")
        pre = preflight_upload(
            filename=item.filename or "upload",
            mime_type=item.mime_type or "image/jpeg",
            payload=payload,
            page_count=item.page_count,
            known_hashes=seen,
        )
        seen[pre.sha256] = item.filename or "upload"
        evidence_report.append({
            "kind": item.kind, "filename": item.filename, "verdict": pre.verdict,
            "accepted": pre.accepted, "checks": pre.checks, "notes": pre.notes,
            "sha256": pre.sha256, "duplicate_of": pre.duplicate_of,
            "quality_score": item.quality_score,
            "quality_action": recovery_action(item.quality_score),
        })
        if pre.accepted:
            accepted.append(item)

    reference = f"AT-2026-{secrets.randbelow(899999) + 100000:06d}" if hasattr(secrets, "randbelow") else f"AT-2026-{secrets.token_hex(3).upper()}"
    now = dt.datetime.now(dt.timezone.utc)

    claim = Claim(
        reference=reference,
        policy_number=policy.policy_number,
        party_id=policy.party_id,
        vin=policy.vin,
        status="fnol_received",
        stage="intake",
        channel=body.channel,
        language=body.language,
        fnol_text=body.fnol_text,
        incident_date=body.incident_date,
        reported_at=now,
        incident_city=body.incident_city,
        incident_region=body.incident_region,
        incident_location=body.incident_location,
        incident_type=body.incident_type,
        collision_type=body.collision_type,
        injury_reported=body.injury_reported,
        third_party_involved=body.third_party_involved,
        police_report_ref=body.police_report_ref,
        sla_due_at=now + dt.timedelta(hours=48),
    )
    db.add(claim)

    for i, item in enumerate(accepted, start=1):
        doc_id = f"{reference}-DOC{i:02d}"
        db.add(Document(
            doc_id=doc_id,
            claim_reference=reference,
            kind=item.kind,
            filename=item.filename,
            mime_type=item.mime_type,
            size_bytes=item.size_bytes,
            page_count=item.page_count,
            sha256=hashlib.sha256((item.filename or doc_id).encode()).hexdigest(),
            source_url=item.source_url,
            doc_type=item.doc_type,
            quality_score=item.quality_score,
            ocr_text=item.ocr_text,
            detections=item.detections,
            uploaded_at=now,
        ))
        for det in item.detections:
            pass  # detections travel on the document, not as extracted fields
    db.commit()

    # The customer has finished; the work starts now rather than when somebody asks.
    if background is not None:
        background.add_task(_auto_analyse, reference, user_id="policy.holder")

    return {
        "accepted": True,
        "reference": reference,
        "firewall": fw.as_dict(),
        "evidence": evidence_report,
        "evidence_accepted": len(accepted),
        "evidence_submitted": len(body.evidence),
        "analysis": "started",
        "next": f"/api/claims/{reference}/analysis-state",
    }


# --------------------------------------------------------------------------
# The guided notification
# --------------------------------------------------------------------------
class Turn(BaseModel):
    question: str = ""
    answer: str


class GuidedRequest(BaseModel):
    policy_number: str | None = None
    answers: list[Turn] = []
    language: str = "de"


@router.post("/intake/question")
async def intake_question(
    body: GuidedRequest, db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The next question to put to the customer, or the signal that enough is known.

    The alternative to the form, not a wrapper around it: both routes end at the same
    intake, and a customer can move between them without losing what they have said.
    """
    from app.services import questionnaire

    product = ""
    if body.policy_number:
        policy = db.get(Policy, body.policy_number)
        if policy is not None:
            product = policy.product_label_en or policy.product

    return await questionnaire.next_question(
        answers=[t.model_dump() for t in body.answers],
        language=body.language,
        policy_product=product,
    )


@router.post("/intake/assemble")
async def intake_assemble(body: GuidedRequest) -> dict[str, Any]:
    """The structured notification the conversation produced.

    Returned to the customer to confirm before it is filed, because a claim assembled from
    a conversation should be shown back to the person whose conversation it was.
    """
    from app.services import questionnaire

    return await questionnaire.assemble(
        answers=[t.model_dump() for t in body.answers],
        language=body.language,
    )


MAX_FILES = 12
MAX_TOTAL_BYTES = 40 * 1024 * 1024


@router.post("/intake/upload")
async def intake_upload(
    policy_number: str = Form(...),
    fnol_text: str = Form(...),
    incident_date: str = Form(...),
    incident_type: str = Form("parking_collision"),
    incident_region: str = Form("Wien"),
    incident_city: str = Form(""),
    language: str = Form("de"),
    channel: str = Form("web"),
    injury_reported: bool = Form(False),
    third_party_involved: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
    background: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """File a claim with real documents attached.

    The order matters and is the point: the customer's words are screened before a model
    could ever see them and before a claim record exists; every file is preflighted before
    it is stored; and what is extracted carries its own confidence, so a value we are not
    sure of is confirmed with the customer rather than promoted quietly.
    """
    policy = db.get(Policy, policy_number)
    if policy is None:
        raise HTTPException(404, f"Policy {policy_number} not found.")
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} files per notification.")

    # Step 1 — the inbound firewall, before anything is written.
    fw = PromptFirewall.inspect(fnol_text, Surface.USER_MESSAGE)
    if fw.action is PolicyAction.BLOCK:
        return {
            "accepted": False,
            "blocked_by": "semantic_gateway.prompt_firewall",
            "firewall": fw.as_dict(),
            "message": (
                "This notification was stopped at the gateway before a model saw it and "
                "before a claim record was created. No file was stored."
            ),
        }

    # Step 2 — read and preflight each file.
    seen: dict[str, str] = {}
    total = 0
    ingested: list[Any] = []
    for upload_file in files:
        payload = await upload_file.read()
        total += len(payload)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, "Total upload size exceeds the limit.")
        result = ingest(
            upload_file.filename or "upload",
            upload_file.content_type or "application/octet-stream",
            payload,
            known_hashes=seen,
        )
        seen[result.sha256] = result.filename
        ingested.append(result)

    accepted = [f for f in ingested if f.accepted]

    # Anything the documents establish that the customer did not type.
    detected_injury = injury_reported or any(
        field["field_name"] == "injury_reported"
        and str(field["extracted_value"]).lower() == "true"
        for f in accepted for field in f.fields
    )
    police_ref = next(
        (field["extracted_value"] for f in accepted for field in f.fields
         if field["field_name"] == "police_report_ref"),
        None,
    )
    third_party = third_party_involved or any(
        field["field_name"] == "at_fault_party"
        and str(field["extracted_value"]) == "third_party"
        for f in accepted for field in f.fields
    )

    reference = f"AT-2026-{secrets.randbelow(899999) + 100000:06d}"
    now = dt.datetime.now(dt.timezone.utc)

    db.add(Claim(
        reference=reference,
        policy_number=policy.policy_number,
        party_id=policy.party_id,
        vin=policy.vin,
        status="fnol_received",
        stage="intake",
        channel=channel,
        language=language,
        fnol_text=fnol_text,
        incident_date=incident_date,
        reported_at=now,
        incident_city=incident_city or incident_region,
        incident_region=incident_region,
        incident_location=f"{incident_city or incident_region}, Austria",
        incident_type=incident_type,
        injury_reported=detected_injury,
        third_party_involved=third_party,
        police_report_ref=police_ref,
        sla_due_at=now + dt.timedelta(hours=48),
    ))

    for index, f in enumerate(accepted, start=1):
        doc_id = f"{reference}-DOC{index:02d}"
        db.add(Document(
            doc_id=doc_id,
            claim_reference=reference,
            kind=f.kind,
            filename=f.filename,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            page_count=f.page_count,
            sha256=f.sha256,
            doc_type=f.doc_type,
            quality_score=f.quality_score,
            # Stored verbatim. Whatever a file carries is preserved as evidence; it is
            # stripped in transit on every read, not sanitised on the way in.
            ocr_text=f.text or None,
            detections=f.detections,
            preflight_notes=f.notes,
            duplicate_of=(f.preflight or {}).get("duplicate_of"),
            uploaded_at=now + dt.timedelta(seconds=index),
        ))
        for field in f.fields:
            db.add(ExtractedField(
                doc_id=doc_id,
                field_name=field["field_name"],
                extracted_value=field["extracted_value"],
                validated_value=field["validated_value"],
                confidence=field["confidence"],
                recovery_action=field["recovery_action"],
                page=1,
            ))
    db.commit()

    # The customer has finished; the work starts now rather than when somebody asks.
    if background is not None:
        background.add_task(_auto_analyse, reference, user_id="policy.holder")

    return {
        "accepted": True,
        "reference": reference,
        "firewall": fw.as_dict(),
        "files": [f.as_dict() for f in ingested],
        "files_accepted": len(accepted),
        "files_submitted": len(ingested),
        "derived": {
            "injury_reported": detected_injury,
            "third_party_involved": third_party,
            "police_report_ref": police_ref,
            "panels": sorted({
                d["panel"] for f in accepted for d in f.detections
            }),
            "structural": any(
                d.get("structural") for f in accepted for d in f.detections
            ),
            "needs_confirming": [
                {"file": f.filename, "field": field["field_name"],
                 "read_as": field["extracted_value"], "confidence": field["confidence"]}
                for f in accepted for field in f.fields
                if field["recovery_action"] != "accept"
            ],
            "unreadable": [
                {"file": f.filename, "quality": f.quality_score, "why": f.notes[:1]}
                for f in accepted if f.quality_score < 0.55
            ],
        },
        "analysis": "started",
        "next": f"/api/claims/{reference}/analysis-state",
    }


# --------------------------------------------------------------------------
# Responding to a request for information
# --------------------------------------------------------------------------
@router.post("/{reference}/documents")
async def add_documents(
    reference: str,
    note: str = Form(""),
    police_report_ref: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    background: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add documents, or an answer, to a claim that is already open.

    Without this the platform could ask a customer for a police report and give them no
    way to send one: the only upload route created a *new* claim, so a customer answering
    a request for information would have opened a second claim instead of completing the
    first. "Waiting on the customer" was a state nobody could leave.

    Everything the intake route does applies here too — the note is screened before it is
    stored, every file is preflighted, and the analysis restarts on its own once the new
    evidence is in, because the reason the claim was waiting may now be gone.
    """
    claim = db.get(Claim, reference)
    if claim is None:
        raise HTTPException(404, f"Claim {reference} not found.")
    if claim.closed_at is not None:
        raise HTTPException(
            409,
            "This claim is closed. Reopening a settled claim is a separate decision.",
        )
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} files at a time.")

    # The customer's words are screened before anything is written, exactly as at intake.
    if note.strip():
        fw = PromptFirewall.inspect(note, Surface.USER_MESSAGE)
        if fw.action is PolicyAction.BLOCK:
            return {
                "accepted": False,
                "reason": "blocked_at_the_gateway",
                "firewall": fw.as_dict(),
            }

    existing = db.scalars(
        select(Document).where(Document.claim_reference == reference)
    ).all()
    known_hashes = {d.sha256 for d in existing if d.sha256}
    start_index = len(existing)

    payloads: list[tuple[str, bytes, str]] = []
    total = 0
    for upload in files:
        raw = await upload.read()
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, "The batch is larger than the per-claim limit.")
        payloads.append((upload.filename or "upload", raw, upload.content_type or ""))

    ingested = [
        ingest(filename=name, payload=raw, mime_type=mime, known_hashes=known_hashes)
        for name, raw, mime in payloads
    ]
    for item in ingested:
        if item.sha256:
            known_hashes.add(item.sha256)
    accepted = [f for f in ingested if not (f.preflight or {}).get("duplicate_of")]

    now = dt.datetime.now(dt.timezone.utc)
    for offset, f in enumerate(accepted, start=1):
        doc_id = f"{reference}-DOC{start_index + offset:02d}"
        db.add(Document(
            doc_id=doc_id,
            claim_reference=reference,
            kind=f.kind,
            filename=f.filename,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            page_count=f.page_count,
            sha256=f.sha256,
            doc_type=f.doc_type,
            quality_score=f.quality_score,
            ocr_text=f.text or None,
            detections=f.detections,
            preflight_notes=f.notes,
            duplicate_of=(f.preflight or {}).get("duplicate_of"),
            uploaded_at=now + dt.timedelta(seconds=offset),
        ))
        for field in f.fields:
            db.add(ExtractedField(
                doc_id=doc_id,
                field_name=field["field_name"],
                extracted_value=field["extracted_value"],
                validated_value=field["validated_value"],
                confidence=field["confidence"],
                recovery_action=field["recovery_action"],
                page=1,
            ))

    if police_report_ref.strip():
        claim.police_report_ref = police_report_ref.strip()
    if note.strip():
        claim.fnol_text = f"{claim.fnol_text}\n\n[Nachtrag] {note.strip()}"

    # The claim is no longer waiting on the customer, whatever it was waiting for.
    if claim.status == "awaiting_customer":
        claim.status = "assessing"
        claim.stage = "triage"
    db.commit()

    if background is not None:
        background.add_task(_auto_analyse, reference, user_id="policy.holder")

    return {
        "accepted": True,
        "reference": reference,
        "documents_added": len(accepted),
        "duplicates_ignored": len(ingested) - len(accepted),
        "files": [f.as_dict() for f in ingested],
        "police_report_ref": claim.police_report_ref,
        "analysis": "restarted",
        "next": f"/api/claims/{reference}/analysis-state",
    }


# --------------------------------------------------------------------------
# Autonomous start
# --------------------------------------------------------------------------
_AUTO_RUNS: dict[str, str] = {}


async def _auto_analyse(reference: str, *, user_id: str) -> None:
    """Work a freshly notified claim without waiting to be asked.

    A customer who has just described an accident and attached a quote has done their part;
    making them press something afterwards is an artefact of how claims software was built,
    not of how a claim works. So intake schedules this, it runs on its own session, and the
    customer's next visit shows a claim that has already moved.

    Failures are swallowed on purpose. The claim exists and is notified; if the analysis
    could not complete, the file is simply still waiting for a person, which is the correct
    resting state and exactly what the queues are for.
    """
    db = SessionLocal()
    try:
        _AUTO_RUNS[reference] = "running"
        async for _ in run_claim(db, reference, user_id=user_id, persona="policy_holder"):
            pass
        _AUTO_RUNS[reference] = "done"
    except Exception as exc:  # noqa: BLE001 — a failed analysis must not lose the claim
        _AUTO_RUNS[reference] = f"failed: {type(exc).__name__}"
        log.warning("autonomous analysis of %s did not complete: %s", reference, exc)
    finally:
        db.close()


@router.get("/{reference}/analysis-state")
def analysis_state(reference: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Whether the automatic analysis of this claim is still running.

    The customer's view polls this so it can say "we are reading your documents" and then
    stop saying it, without ever showing them a run, a stage list or an agent.
    """
    claim = db.get(Claim, reference)
    if claim is None:
        raise HTTPException(404, f"Claim {reference} not found.")
    state = _AUTO_RUNS.get(reference)
    # A claim that has left intake has been worked, whatever this process remembers —
    # the server may have restarted since.
    settled = claim.stage not in ("intake", "notify", "") and claim.stage is not None
    return {
        "reference": reference,
        "working": state == "running" and not settled,
        "state": state or ("done" if settled else "not_started"),
        "stage": claim.stage,
        "status": claim.status,
    }


# --------------------------------------------------------------------------
# Running a claim
# --------------------------------------------------------------------------
@router.post("/{reference}/run")
async def run_sync(
    reference: str,
    user_id: str = "system",
    mode: str | None = None,
    runtime: str | None = None,
    persona: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the pipeline and return the whole trace at once.

    `runtime` is "pydantic-ai", "google-adk" or "deterministic".
    """
    events: list[dict[str, Any]] = []
    async for ev in run_claim(db, reference, user_id=user_id, mode=mode,
                              runtime=runtime, persona=persona):
        events.append(ev)
    if not events:
        raise HTTPException(404, f"Claim {reference} not found.")
    return {"reference": reference, "events": events, "final": events[-1]}


@router.get("/{reference}/stream")
async def run_stream(
    reference: str, request: Request, user_id: str = "system", mode: str | None = None,
    runtime: str | None = None, persona: str | None = None,
):
    """Stream the run as server-sent events, one per trace step."""

    async def generator():
        db = SessionLocal()
        try:
            async for ev in run_claim(db, reference, user_id=user_id, mode=mode,
                                      runtime=runtime, persona=persona):
                if await request.is_disconnected():
                    break
                yield {"event": ev.get("kind", "message"), "data": json.dumps(ev, default=str)}
        except Exception as exc:  # noqa: BLE001 — surface the failure to the client
            yield {
                "event": "error",
                "data": json.dumps({"kind": "error", "detail": f"{type(exc).__name__}: {exc}"}),
            }
        finally:
            db.close()

    return EventSourceResponse(generator())
