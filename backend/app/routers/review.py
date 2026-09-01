"""Human review: the queues, the evidence workspace and the decision controls."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.personas import STAFF
from app.services import review as review_service

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/queue")
def queue(queue: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return review_service.queue_state(db, queue)


@router.get("/staff")
def staff() -> dict[str, Any]:
    return {"staff": STAFF}


@router.get("/tasks/{task_id}")
def task(task_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    detail = review_service.task_detail(db, task_id)
    if detail is None:
        raise HTTPException(404, f"Task {task_id} not found.")
    return detail


class AssignRequest(BaseModel):
    user_id: str


@router.post("/tasks/{task_id}/assign")
def assign(task_id: str, body: AssignRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return review_service.assign(db, task_id, body.user_id)
    except review_service.ReviewError as exc:
        raise HTTPException(400, str(exc)) from exc


class DecideRequest(BaseModel):
    # approve | amend | reject move money or close a claim and need authority.
    # confirm | release | refer | request_more record a professional finding
    # and do not — an assessor confirming a total loss moves no money.
    decision: str
    user_id: str
    amount_eur: float | None = None
    note: str = ""


@router.post("/tasks/{task_id}/decide")
def decide(task_id: str, body: DecideRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Approve, amend, reject or ask for more — through the same signed write path."""
    try:
        return review_service.decide(
            db, task_id, decision=body.decision, user_id=body.user_id,
            amount_eur=body.amount_eur, note=body.note,
        )
    except review_service.ReviewError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
