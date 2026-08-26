"""Observability, evaluation and FinOps."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import metrics
from app.services.evals import GOLDEN_CASES, run_evaluations

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/metrics")
def portfolio(db: Session = Depends(get_db)) -> dict[str, Any]:
    return metrics.portfolio_metrics(db)


@router.get("/observability")
def observability(limit: int = 25, db: Session = Depends(get_db)) -> dict[str, Any]:
    return metrics.run_observability(db, limit)


@router.get("/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    detail = metrics.run_detail(db, run_id)
    if detail is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return detail


@router.get("/evals/cases")
def eval_cases() -> dict[str, Any]:
    return {"suite": "allianz-at-motor-golden-cases-1.0", "cases": GOLDEN_CASES}


@router.post("/evals/run")
async def evals(
    mode: str | None = None, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Replay every golden case against the live platform. Nothing is mocked.

    The golden cases assert deterministic outcomes, so they run in deterministic mode by
    default — an evaluation suite whose expected values move with model sampling is not
    an evaluation suite. Pass mode=live to check a real model against the same assertions.
    """
    return await run_evaluations(db, mode=mode or "deterministic")
