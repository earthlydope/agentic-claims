"""Model usage, and how close we are to the limits.

Every call to a model provider is recorded, so three questions have answers rather than
estimates: what did we consume, what is it costing per claim, and how much headroom is
left before the provider starts refusing us.

The limits below are the Gemini free-tier defaults. Set `MODEL_RATE_LIMITS` to the quota
the project actually holds — a limit the platform believes but does not have is worse than
no limit at all.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MODEL_PRICING_EUR_PER_MTOK, MODEL_MAX_RPM
from app.models import ModelCall


@dataclass(frozen=True)
class RateLimit:
    rpm: int          # requests per minute
    tpm: int          # tokens per minute
    rpd: int          # requests per day
    tier: str = "free"


# Gemini free tier, as the provider publishes it.
DEFAULT_LIMITS: dict[str, RateLimit] = {
    "gemini-3.1-flash-lite": RateLimit(15, 250_000, 500),
    "gemini-3.7-flash": RateLimit(5, 250_000, 20),
    "gemini-3.6-flash": RateLimit(5, 250_000, 20),
    "gemini-3.5-flash": RateLimit(5, 250_000, 20),
    "gemini-3-flash-preview": RateLimit(5, 250_000, 20),
    "gemini-3.1-pro-preview": RateLimit(0, 0, 0),
    "gemini-2.5-flash": RateLimit(0, 0, 0),
    "gemini-2.5-pro": RateLimit(0, 0, 0),
    "scripted-deterministic": RateLimit(0, 0, 0, tier="local"),
}

CATEGORY: dict[str, str] = {
    "scripted-deterministic": "Deterministic provider",
}


def _configured_limits() -> dict[str, RateLimit]:
    """Allow the real quota to be supplied, rather than assumed."""
    raw = os.environ.get("MODEL_RATE_LIMITS", "").strip()
    limits = dict(DEFAULT_LIMITS)
    if not raw:
        return limits
    try:
        for name, spec in json.loads(raw).items():
            limits[name] = RateLimit(
                int(spec.get("rpm", 0)), int(spec.get("tpm", 0)),
                int(spec.get("rpd", 0)), str(spec.get("tier", "configured")),
            )
    except (ValueError, TypeError, AttributeError):
        pass
    return limits


def limit_for(model: str) -> RateLimit:
    return _configured_limits().get(model, RateLimit(MODEL_MAX_RPM, 250_000, 500, "assumed"))


def cost_of(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = MODEL_PRICING_EUR_PER_MTOK.get(model)
    if price is None:
        return 0.0
    return round(
        (prompt_tokens / 1_000_000.0) * price["in"]
        + (completion_tokens / 1_000_000.0) * price["out"],
        8,
    )


def record(
    db: Session,
    *,
    model: str,
    runtime: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    agent: str | None = None,
    persona: str | None = None,
    purpose: str = "claim_run",
    claim_reference: str | None = None,
    run_id: str | None = None,
    latency_ms: float = 0.0,
    throttle_wait_ms: float = 0.0,
    outcome: str = "ok",
    error: str | None = None,
    cost_eur: float | None = None,
) -> None:
    """Record one call. Never allowed to break the caller."""
    try:
        total = int(prompt_tokens or 0) + int(completion_tokens or 0)
        db.add(ModelCall(
            model=model, runtime=runtime, agent=agent, persona=persona, purpose=purpose,
            claim_reference=claim_reference, run_id=run_id,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            total_tokens=total,
            cost_eur=(cost_of(model, prompt_tokens, completion_tokens)
                      if cost_eur is None else round(float(cost_eur), 8)),
            latency_ms=round(float(latency_ms or 0.0), 2),
            throttle_wait_ms=round(float(throttle_wait_ms or 0.0), 2),
            outcome=outcome, error=(error or "")[:500] or None,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 — metering must never take a run down
        db.rollback()


# --------------------------------------------------------------------------
def _peak_windows(calls: list[ModelCall]) -> tuple[int, int, int]:
    """Peak requests/minute, tokens/minute and requests/day actually observed.

    A ceiling is only meaningful against the peak, not the average — an average that looks
    comfortable hides the minute in which the provider started refusing.
    """
    if not calls:
        return 0, 0, 0

    stamped = sorted(
        ((c.at.replace(tzinfo=dt.timezone.utc) if c.at.tzinfo is None else c.at), c)
        for c in calls if c.at is not None
    )
    if not stamped:
        return 0, 0, 0

    peak_rpm = peak_tpm = 0
    start = 0
    running_tokens = 0
    for end in range(len(stamped)):
        running_tokens += stamped[end][1].total_tokens or 0
        while (stamped[end][0] - stamped[start][0]).total_seconds() > 60.0:
            running_tokens -= stamped[start][1].total_tokens or 0
            start += 1
        peak_rpm = max(peak_rpm, end - start + 1)
        peak_tpm = max(peak_tpm, running_tokens)

    by_day: dict[str, int] = {}
    for at, _ in stamped:
        key = at.date().isoformat()
        by_day[key] = by_day.get(key, 0) + 1
    peak_rpd = max(by_day.values()) if by_day else 0

    return peak_rpm, peak_tpm, peak_rpd


def usage_report(db: Session, days: int = 28) -> dict[str, Any]:
    """Peak usage per model against its limit — the shape the console renders."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    calls = db.scalars(select(ModelCall).where(ModelCall.at >= since)).all()

    by_model: dict[str, list[ModelCall]] = {}
    for call in calls:
        by_model.setdefault(call.model or "unknown", []).append(call)

    # Every model the platform knows about appears, used or not — a page that only lists
    # what was used cannot tell you what headroom you have elsewhere.
    known = set(_configured_limits()) | set(by_model)

    rows: list[dict[str, Any]] = []
    for model in sorted(known):
        model_calls = by_model.get(model, [])
        limit = limit_for(model)
        rpm, tpm, rpd = _peak_windows(model_calls)
        tokens = sum(c.total_tokens or 0 for c in model_calls)
        cost = round(sum(c.cost_eur or 0.0 for c in model_calls), 6)
        quota_refusals = sum(1 for c in model_calls if c.outcome == "quota")
        latencies = [c.latency_ms or 0.0 for c in model_calls if c.latency_ms]

        rows.append({
            "model": model,
            "category": CATEGORY.get(model, "Text-out models"),
            "tier": limit.tier,
            "available": limit.rpm > 0 or model == "scripted-deterministic",
            "calls": len(model_calls),
            "tokens": tokens,
            "cost_eur": cost,
            "quota_refusals": quota_refusals,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
            "rpm": {"peak": rpm, "limit": limit.rpm,
                    "ratio": round(rpm / limit.rpm, 4) if limit.rpm else 0.0},
            "tpm": {"peak": tpm, "limit": limit.tpm,
                    "ratio": round(tpm / limit.tpm, 4) if limit.tpm else 0.0},
            "rpd": {"peak": rpd, "limit": limit.rpd,
                    "ratio": round(rpd / limit.rpd, 4) if limit.rpd else 0.0},
        })

    rows.sort(key=lambda r: (-r["rpm"]["ratio"], -r["calls"], r["model"]))

    total_tokens = sum(r["tokens"] for r in rows)
    total_cost = round(sum(r["cost_eur"] for r in rows), 6)
    total_calls = sum(r["calls"] for r in rows)
    claims = {c.claim_reference for c in calls if c.claim_reference}

    by_purpose: dict[str, dict[str, Any]] = {}
    for call in calls:
        entry = by_purpose.setdefault(
            call.purpose or "unknown",
            {"purpose": call.purpose or "unknown", "calls": 0, "tokens": 0, "cost_eur": 0.0},
        )
        entry["calls"] += 1
        entry["tokens"] += call.total_tokens or 0
        entry["cost_eur"] = round(entry["cost_eur"] + (call.cost_eur or 0.0), 6)

    by_runtime: dict[str, int] = {}
    for call in calls:
        by_runtime[call.runtime or "unknown"] = by_runtime.get(call.runtime or "unknown", 0) + 1

    at_limit = [r for r in rows if r["rpm"]["ratio"] >= 1.0 or r["rpd"]["ratio"] >= 1.0]

    return {
        "window_days": days,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "models": rows,
        "totals": {
            "calls": total_calls,
            "tokens": total_tokens,
            "cost_eur": total_cost,
            "claims_touched": len(claims),
            "cost_per_claim_eur": round(total_cost / len(claims), 6) if claims else 0.0,
            "tokens_per_claim": round(total_tokens / len(claims)) if claims else 0,
            "quota_refusals": sum(r["quota_refusals"] for r in rows),
        },
        "by_purpose": sorted(by_purpose.values(), key=lambda p: -p["tokens"]),
        "by_runtime": by_runtime,
        "at_limit": [r["model"] for r in at_limit],
        "warning": (
            f"{', '.join(r['model'] for r in at_limit)} reached a limit in this window."
            if at_limit else None
        ),
        "note": (
            "Limits are the Gemini free-tier defaults. Set MODEL_RATE_LIMITS to the quota "
            "the project actually holds."
        ),
    }


def recent_calls(db: Session, limit: int = 60) -> list[dict[str, Any]]:
    rows = db.scalars(select(ModelCall).order_by(ModelCall.at.desc()).limit(limit)).all()
    return [
        {
            "at": r.at.isoformat() if r.at else None,
            "model": r.model, "runtime": r.runtime, "agent": r.agent,
            "persona": r.persona, "purpose": r.purpose,
            "claim_reference": r.claim_reference,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens, "cost_eur": r.cost_eur,
            "latency_ms": r.latency_ms, "throttle_wait_ms": r.throttle_wait_ms,
            "outcome": r.outcome, "error": r.error,
        }
        for r in rows
    ]


def daily_series(db: Session, days: int = 28) -> list[dict[str, Any]]:
    """Calls, tokens and cost per day, for the trend the console draws."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    rows = db.execute(
        select(
            func.date(ModelCall.at).label("day"),
            func.count(ModelCall.id),
            func.sum(ModelCall.total_tokens),
            func.sum(ModelCall.cost_eur),
        )
        .where(ModelCall.at >= since)
        .group_by(func.date(ModelCall.at))
        .order_by(func.date(ModelCall.at))
    ).all()
    return [
        {"day": str(day), "calls": int(calls or 0), "tokens": int(tokens or 0),
         "cost_eur": round(float(cost or 0.0), 6)}
        for day, calls, tokens, cost in rows
    ]
