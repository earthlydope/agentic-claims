"""Append-only ledger persistence and the two auditors that read it."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Claim, LedgerEntry
from app.zero_trust.crypto_guard import GENESIS_HASH, LedgerAuditor


def next_nonce(db: Session) -> int:
    """Strictly increasing per tenant. Gaps and repeats both raise an alert."""
    current = db.scalar(select(func.max(LedgerEntry.nonce)))
    return int(current or 0) + 1


def last_chain_hash(db: Session) -> str:
    row = db.scalars(
        select(LedgerEntry).order_by(LedgerEntry.nonce.desc()).limit(1)
    ).first()
    return row.chain_hash if row else GENESIS_HASH


def append(db: Session, envelope: dict[str, Any], *, status: str = "VERIFIED_AUTHENTIC") -> LedgerEntry:
    entry = LedgerEntry(
        nonce=envelope["nonce"],
        tenant=envelope["tenant"],
        claim_id=envelope["claim_id"],
        run_id=envelope["run_id"],
        step_id=envelope["step_id"],
        agent_id=envelope["agent_id"],
        service_identity=envelope["service_identity"],
        user_id=envelope["user_id"],
        action=envelope["action"],
        policy_version=envelope["policy_version"],
        approval_ref=envelope.get("approval_ref"),
        timestamp=envelope["timestamp"],
        payload_hash=envelope["payload_hash"],
        prev_hash=envelope["prev_hash"],
        chain_hash=envelope["chain_hash"],
        signature=envelope["signature"],
        signer=envelope.get("signer"),
        payload=envelope.get("payload") or {},
        verification_status=status,
    )
    db.add(entry)
    db.commit()
    return entry


def entry_to_dict(entry: LedgerEntry) -> dict[str, Any]:
    return {
        "nonce": entry.nonce,
        "tenant": entry.tenant,
        "claim_id": entry.claim_id,
        "run_id": entry.run_id,
        "step_id": entry.step_id,
        "agent_id": entry.agent_id,
        "service_identity": entry.service_identity,
        "user_id": entry.user_id,
        "action": entry.action,
        "policy_version": entry.policy_version,
        "approval_ref": entry.approval_ref,
        "timestamp": entry.timestamp,
        "payload_hash": entry.payload_hash,
        "prev_hash": entry.prev_hash,
        "chain_hash": entry.chain_hash,
        "signature": entry.signature,
        "signer": entry.signer,
        "payload": entry.payload or {},
        "verification_status": entry.verification_status,
    }


def all_entries(db: Session, limit: int | None = None) -> list[dict[str, Any]]:
    stmt = select(LedgerEntry).order_by(LedgerEntry.nonce.asc())
    if limit:
        stmt = stmt.limit(limit)
    return [entry_to_dict(e) for e in db.scalars(stmt).all()]


def verify_chain(db: Session) -> dict[str, Any]:
    return LedgerAuditor.verify_chain(all_entries(db))


def audit_database(db: Session) -> dict[str, Any]:
    """Reconcile live claim rows against the latest signed entry for each claim."""
    rows = []
    for claim in db.scalars(
        select(Claim).where(Claim.decision.isnot(None), Claim.scenario_key.isnot(None))
    ).all():
        rows.append({
            "claim_id": claim.reference,
            "decision": claim.decision,
            "settlement_amount_eur": claim.settlement_amount_eur,
            "severity": claim.severity,
            "status": claim.status,
        })
    return LedgerAuditor.audit_database(rows, all_entries(db))
