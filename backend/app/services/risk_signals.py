"""Risk signals derived from what a claim itself knows.

These used to exist only in the seeder, so no claim filed through the platform could ever
carry one: every real notification scored 0.00 and the fraud function was reachable on
three hard-coded claims and nothing else.

The derivation lives here rather than inside `get_risk_signals` because that tool is
classified read-high and documented read-only, and a read tool that writes is exactly the
kind of quiet scope violation the platform's whole tool discipline exists to prevent. The
graph calls `refresh` on the risk stage, where a write is a declared side effect.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, Document, ExtractedField, RiskSignal
from app.semantic.definitions import COLLISION_PERILS


def _derive(db: Session, reference: str) -> list[dict[str, Any]]:
    """Signals a claim carries on its own facts, computed at run time.

    RiskSignal rows were written only by the seeder, so no claim filed through the platform
    could ever carry one: every real notification scored 0.00 with no signals, PG-08 always
    passed, and the fraud function was reachable on three hard-coded claims and nothing
    else. These are the indicators derivable from what the claim itself knows — reporting
    delay, claim velocity on the same party, repeat use of the same repairer, a prior claim
    on the same vehicle, and a missing police report where the conditions require one.

    They are signals, not findings. The weights are stated here rather than learned, which
    is honest for a demonstration and is also how a governed indicator set starts.
    """
    import datetime as _dt


    claim = db.get(Claim, reference)
    if claim is None:
        return []

    signals: list[dict[str, Any]] = []

    # Late notification — AKHB Art 9 requires notification "unverzüglich".
    if claim.incident_date and claim.reported_at:
        try:
            incident = claim.incident_date
            if isinstance(incident, str):
                incident = _dt.date.fromisoformat(incident[:10])
            if isinstance(incident, _dt.datetime):
                incident = incident.date()
            reported = claim.reported_at
            reported = reported.date() if isinstance(reported, _dt.datetime) else reported
            days = (reported - incident).days
            if days >= 60:
                signals.append({
                    "signal_type": "late_notification",
                    "detail": f"Reported {days} days after the incident date.",
                    "weight": 0.20 if days < 120 else 0.30,
                })
        except (ValueError, TypeError):
            pass

    # Claim velocity, measured against the book rather than against zero.
    #
    # An absolute count is not a signal: in any real portfolio most customers have some
    # history, and a threshold picked without reference to the book fires on everybody.
    # What is actually indicative is being well outside the normal distribution — so this
    # compares the party against the median claimant and only speaks when they are clearly
    # above it. Calibrating to the portfolio is also what stops a denser book quietly
    # turning every claim into a referral.
    siblings = db.scalars(
        select(Claim).where(
            Claim.party_id == claim.party_id, Claim.reference != claim.reference
        )
    ).all()
    recent = [c for c in siblings if c.reported_at and claim.reported_at
              and abs((claim.reported_at - c.reported_at).days) <= 240]
    mine_count = len(recent) + 1

    per_party: dict[str, int] = {}
    for row in db.scalars(select(Claim.party_id)).all():
        if row:
            per_party[row] = per_party.get(row, 0) + 1
    counts = sorted(per_party.values()) or [1]
    median = counts[len(counts) // 2]

    # median + 2 rather than median x 2: on a book with a median of five claims per party
    # a doubling puts the bar at ten and switches the indicator off entirely, which is the
    # opposite failure from firing on everybody.
    if mine_count >= max(3, median + 2):
        signals.append({
            "signal_type": "claim_velocity",
            "detail": (
                f"{mine_count} claims from this party in eight months, against a book "
                f"median of {median}."
            ),
            "weight": 0.30,
        })

    # A prior claim on the same vehicle is ordinary; several in a short window is not.
    same_vehicle = [c for c in recent if c.vin and c.vin == claim.vin]
    if len(same_vehicle) >= 3:
        signals.append({
            "signal_type": "repeat_vehicle",
            "detail": f"{len(same_vehicle)} claims on the same vehicle within eight months.",
            "weight": 0.15,
        })

    # The same repairer across the party's claims, read off the documents.
    # Deliberately scoped to the party's *other* claims. Querying every extraction row
    # matched the claim's own repairer against itself, so the signal fired on any claim
    # with a quote attached — an artefact, not an indicator.
    sibling_docs = {
        d.doc_id
        for d in db.scalars(
            select(Document).where(
                Document.claim_reference.in_([c.reference for c in siblings])
            )
        ).all()
    } if siblings else set()
    repairers = {
        f.extracted_value
        for f in db.scalars(
            select(ExtractedField).where(
                ExtractedField.field_name == "repairer_name",
                ExtractedField.doc_id.in_(sibling_docs),
            )
        ).all()
        if f.extracted_value
    } if sibling_docs else set()
    mine = {
        f.extracted_value
        for d in db.scalars(
            select(Document).where(Document.claim_reference == reference)
        ).all()
        for f in db.scalars(
            select(ExtractedField).where(
                ExtractedField.doc_id == d.doc_id,
                ExtractedField.field_name == "repairer_name",
            )
        ).all()
        if f.extracted_value
    }
    if mine and repairers and (mine & repairers) and len(recent) >= 1:
        signals.append({
            "signal_type": "repeat_repairer",
            "detail": f"Same repairer as an earlier claim from this party: {sorted(mine & repairers)[0]}.",
            "weight": 0.20,
        })

    # Parking damage with no police reference, which AKKB (VAV) Art 1 lit j requires.
    if claim.incident_type == "parking_collision" and not claim.police_report_ref:
        signals.append({
            "signal_type": "missing_police_report",
            "detail": "Parking damage reported without the police confirmation the "
                      "conditions require.",
            "weight": 0.05,
        })

    return signals


def refresh(db: Session, reference: str) -> int:
    """Store any derived signal this claim does not already carry. Returns how many."""
    existing = {
        r.signal_type
        for r in db.scalars(
            select(RiskSignal).where(RiskSignal.claim_reference == reference)
        ).all()
    }
    added = 0
    for sig in _derive(db, reference):
        if sig["signal_type"] in existing:
            continue
        db.add(RiskSignal(
            claim_reference=reference,
            signal_type=sig["signal_type"],
            detail=sig["detail"],
            weight=sig["weight"],
            evidence_ref="derived-at-run-time",
        ))
        added += 1
    if added:
        db.commit()
    return added
