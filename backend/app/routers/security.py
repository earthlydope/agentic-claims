"""The zero-trust governance console: posture, ledger, drills and the regression suite."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SecurityEvent
from app.services import ledger, security_ops
from app.zero_trust.sandbox import execute_sandboxed, run_sandbox_attack_corpus
from app.zero_trust.semantic_gateway import (
    DecisionPolicyGuard,
    PromptFirewall,
    Surface,
    screen_customer_message,
)

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/posture")
def posture(db: Session = Depends(get_db)) -> dict[str, Any]:
    return security_ops.security_posture(db)


@router.get("/ledger")
def get_ledger(limit: int = 200, db: Session = Depends(get_db)) -> dict[str, Any]:
    entries = ledger.all_entries(db)
    chain = ledger.verify_chain(db)
    return {
        "entries": entries[-limit:],
        "total": len(entries),
        "chain": chain,
        "database_audit": ledger.audit_database(db),
    }


@router.post("/verify")
def verify(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Walk the whole chain and reconcile it against the live rows, on demand."""
    return {
        "chain": ledger.verify_chain(db),
        "database_audit": ledger.audit_database(db),
    }


@router.get("/events")
def events(limit: int = 100, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(
        select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(limit)
    ).all()
    return {
        "events": [
            {"event_id": e.event_id, "claim_reference": e.claim_reference,
             "run_id": e.run_id, "kind": e.kind, "severity": e.severity,
             "surface": e.surface, "rule_ids": e.rule_ids or [], "detail": e.detail,
             "payload": e.payload or {},
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in rows
        ],
        "count": len(rows),
    }


@router.post("/regression")
def regression(db: Session = Depends(get_db)) -> dict[str, Any]:
    """The security regression suite. Must pass at 100% before any release."""
    return security_ops.run_regression_suite(db)


@router.post("/attack-replay")
def attack_replay() -> dict[str, Any]:
    """Replay the attack prompt library against the gateway."""
    return security_ops.run_attack_replay()


@router.get("/attack-library")
def attack_library() -> dict[str, Any]:
    return {"library": security_ops.ATTACK_LIBRARY}


class ScreenRequest(BaseModel):
    text: str
    surface: str = "user_message"


@router.post("/screen")
def screen(body: ScreenRequest) -> dict[str, Any]:
    """Screen arbitrary text through the firewall, so anything can be tried live."""
    try:
        surface = Surface(body.surface)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown surface '{body.surface}'.") from exc
    result = PromptFirewall.inspect(body.text, surface)
    return {"input": body.text, **result.as_dict(),
            "sanitised_text": result.sanitised_text}


class GuardRequest(BaseModel):
    package: dict[str, Any]


@router.post("/guard")
def guard(body: GuardRequest) -> dict[str, Any]:
    """Run a decision package through the deterministic policy guard directly."""
    return DecisionPolicyGuard.evaluate(body.package).as_dict()


class SandboxRequest(BaseModel):
    code: str


@router.post("/sandbox")
def sandbox(body: SandboxRequest) -> dict[str, Any]:
    """Try arbitrary code against the sandbox. Escapes are refused, not executed."""
    return execute_sandboxed(body.code).as_dict()


@router.get("/sandbox-corpus")
def sandbox_corpus() -> dict[str, Any]:
    results = run_sandbox_attack_corpus()
    return {
        "results": results,
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
    }


class CommsRequest(BaseModel):
    body: str
    approved_amount_eur: float | None = None


@router.post("/outbound-guard")
def outbound_guard(body: CommsRequest) -> dict[str, Any]:
    return screen_customer_message(
        body.body, approved_amount_eur=body.approved_amount_eur
    ).as_dict()


class TamperRequest(BaseModel):
    reference: str
    new_amount_eur: float = 14_850.00


@router.post("/drills/tamper")
def tamper_drill(body: TamperRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Deliberately destructive: edit an approved claim out of band, then detect it."""
    result = security_ops.run_tamper_drill(db, body.reference, body.new_amount_eur)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


class RestoreRequest(BaseModel):
    reference: str


@router.post("/drills/restore")
def restore(body: RestoreRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = security_ops.restore_from_ledger(db, body.reference)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
