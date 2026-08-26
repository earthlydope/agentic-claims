"""Persona-scoped workspace: who is looking, what they see, and their coworker."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.coworker import ask
from app.agents.graph import graph_shape
from app.claimants import CUSTOMERS, REPAIRERS, SCENARIOS
from app.config import AUTHORITY_LIMITS_EUR
from app.db import get_db
from app.lifecycle import STATUSES, stage_dicts, stages_for, status_meta
from app.models import Claim, CoworkerTurn, Estimate, ReviewTask
from app.personas import (
    DEFAULT_PERSONA,
    FEATURES,
    PERSONAS,
    normalise_queue,
    persona as get_persona,
)
from app.services import llm_usage, tracing

router = APIRouter(prefix="/api", tags=["workspace"])


@router.get("/personas")
def personas() -> dict[str, Any]:
    """The people who use this platform, and what each of them sees."""
    return {
        "personas": [p.as_dict() for p in PERSONAS],
        "default": DEFAULT_PERSONA,
        "features": {k: {**v.__dict__, "stages": list(v.stages)} for k, v in FEATURES.items()},
        "authority_limits_eur": AUTHORITY_LIMITS_EUR,
        # The claimants are the people who *have* claims, as distinct from the people who
        # work them.
        "claimants": [
            {
                "party_id": c["party_id"],
                "name": f"{c['first_name']} {c['last_name']}",
                "city": c["city"], "language": c["language"],
                "product": c["policy"]["product"],
                "vehicle": f"{c['vehicle']['make']} {c['vehicle']['model']}",
                "note": c["persona_note"],
            }
            for c in CUSTOMERS
        ],
        "repairers": REPAIRERS,
        "scenarios": SCENARIOS,
    }


@router.get("/personas/{key}")
def persona_detail(key: str) -> dict[str, Any]:
    p = get_persona(key)
    if p.key != key:
        raise HTTPException(404, f"No persona '{key}'.")
    return {
        **p.as_dict(),
        "stages_owned": [s.as_dict() for s in stages_for(p.key)],
    }


@router.get("/lifecycle")
def lifecycle() -> dict[str, Any]:
    """Every stage of the claim, and who owns it."""
    return {
        "stages": stage_dicts(),
        "statuses": [
            {"key": s.key, "label": s.label, "stage": s.stage, "tone": s.tone,
             "terminal": s.terminal, "description": s.description}
            for s in STATUSES
        ],
        "graph": graph_shape(),
        "tracing": tracing.status(),
    }


# --------------------------------------------------------------------------
# The persona's own work
# --------------------------------------------------------------------------
@router.get("/work")
def work(persona: str = DEFAULT_PERSONA, db: Session = Depends(get_db)) -> dict[str, Any]:
    """What this persona has to do, and nothing that belongs to anybody else."""
    p = get_persona(persona)
    now = dt.datetime.now(dt.timezone.utc)

    if p.kind == "customer":
        claims = db.scalars(
            select(Claim).where(Claim.party_id == p.party_id)
            .order_by(Claim.reported_at.desc())
        ).all()
        return {
            "persona": p.key,
            "kind": "customer",
            "claims": [_customer_card(c, db) for c in claims],
            "open": sum(1 for c in claims if not status_meta(c.status)["terminal"]),
        }

    queues = set(p.queues)
    tasks = db.scalars(select(ReviewTask).where(ReviewTask.status != "resolved")).all()
    mine = [t for t in tasks if (normalise_queue(t.queue) or t.queue) in queues]
    mine.sort(key=lambda t: (t.priority or 3, -(t.proposed_amount_eur or 0.0)))

    claim_map = {
        c.reference: c
        for c in db.scalars(
            select(Claim).where(Claim.reference.in_([t.claim_reference for t in mine]))
        ).all()
    } if mine else {}

    rows = []
    for t in mine:
        claim = claim_map.get(t.claim_reference)
        due = t.sla_due_at
        if due is not None and due.tzinfo is None:
            due = due.replace(tzinfo=dt.timezone.utc)
        rows.append({
            "task_id": t.task_id,
            "claim_reference": t.claim_reference,
            "queue": t.queue,
            "reason": t.reason,
            "reason_detail": t.reason_detail,
            "proposed_decision": t.proposed_decision,
            "proposed_amount_eur": t.proposed_amount_eur or 0.0,
            "authority_required": t.authority_required,
            "within_my_authority": (t.proposed_amount_eur or 0.0) <= p.authority_limit_eur
            and p.authority_limit_eur > 0,
            "priority": t.priority,
            "sla_due_at": due.isoformat() if due else None,
            "sla_breached": bool(due and due < now),
            "age_minutes": round(
                (now - (t.created_at.replace(tzinfo=dt.timezone.utc)
                        if t.created_at and t.created_at.tzinfo is None
                        else t.created_at or now)).total_seconds() / 60.0, 1),
            "policyholder": (
                f"{claim.party_id}" if claim is None else _holder_name(claim, db)),
            "severity": claim.severity if claim else None,
            "structural": bool(claim.structural_damage) if claim else False,
            "injury": bool(claim.injury_reported) if claim else False,
            "status": status_meta(claim.status if claim else None),
        })

    return {
        "persona": p.key,
        "kind": "staff",
        "queues": sorted(queues),
        "authority_limit_eur": p.authority_limit_eur,
        "open": len(rows),
        "sla_breached": sum(1 for r in rows if r["sla_breached"]),
        "value_at_stake_eur": round(sum(r["proposed_amount_eur"] for r in rows), 2),
        "tasks": rows,
        "stages_owned": [s.as_dict() for s in stages_for(p.key)],
    }


def _holder_name(claim: Claim, db: Session) -> str:
    from app.models import Party

    party = db.get(Party, claim.party_id) if claim.party_id else None
    return f"{party.first_name} {party.last_name}" if party else (claim.party_id or "—")


def _customer_card(claim: Claim, db: Session) -> dict[str, Any]:
    from app.models import Message

    messages = db.scalars(
        select(Message).where(Message.claim_reference == claim.reference)
        .order_by(Message.created_at.desc()).limit(1)
    ).all()
    estimate = db.scalars(
        select(Estimate).where(Estimate.claim_reference == claim.reference)
        .order_by(Estimate.id.desc()).limit(1)
    ).first()
    return {
        "reference": claim.reference,
        "status": status_meta(claim.status),
        "incident_type": claim.incident_type,
        "incident_date": claim.incident_date,
        "reported_at": claim.reported_at.isoformat() if claim.reported_at else None,
        "decision": claim.decision,
        "settlement_amount_eur": claim.settlement_amount_eur or 0.0,
        "estimate_eur": estimate.total_cost if estimate else None,
        "with_a_person": claim.status in ("in_review", "under_investigation",
                                          "total_loss_review"),
        "latest_message": (
            {"subject": messages[0].subject, "body": messages[0].body}
            if messages and messages[0].status != "blocked" else None
        ),
        "scenario_key": claim.scenario_key,
    }


# --------------------------------------------------------------------------
# The coworker
# --------------------------------------------------------------------------
class AskRequest(BaseModel):
    persona: str = DEFAULT_PERSONA
    question: str
    conversation_id: str | None = None


@router.post("/coworker/ask")
async def coworker_ask(body: AskRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Put a question to a persona's AI coworker.

    The question is screened like any other input, the coworker can only reach the tools its
    persona is allowed to reach, and anything it says to a customer goes through the
    outbound guard.
    """
    if not body.question.strip():
        raise HTTPException(400, "A question is required.")
    return await ask(db, persona_key=body.persona, question=body.question,
                     conversation_id=body.conversation_id)


@router.get("/coworker/{persona}")
def coworker_profile(persona: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_persona(persona)
    turns = db.scalars(
        select(CoworkerTurn).where(CoworkerTurn.persona == p.key)
        .order_by(CoworkerTurn.created_at.desc()).limit(30)
    ).all()
    return {
        "persona": p.key,
        "coworker": p.coworker.as_dict(),
        "history": [
            {
                "turn_id": t.turn_id, "conversation_id": t.conversation_id,
                "question": t.question, "answer": t.answer,
                "tools_used": t.tools_used or [], "citations": t.citations or [],
                "blocked": bool(t.blocked), "block_reason": t.block_reason,
                "model": t.model, "latency_ms": t.latency_ms,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in reversed(turns)
        ],
    }


# --------------------------------------------------------------------------
# Model usage
# --------------------------------------------------------------------------
@router.get("/llm-usage")
def usage(days: int = 28, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Peak usage per model against its limit, plus what it is costing per claim."""
    return {
        **llm_usage.usage_report(db, days),
        "recent": llm_usage.recent_calls(db, 40),
        "daily": llm_usage.daily_series(db, days),
        "tracing": tracing.status(),
    }
