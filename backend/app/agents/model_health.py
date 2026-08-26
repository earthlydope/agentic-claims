"""Which providers are actually reachable, as opposed to merely configured.

A key in the environment is not the same as a provider you can call. A team without
credits, a model closed to new projects and an expired key all look identical from the
config and completely different from the API. Putting a dead leg at the front of a fallback
chain costs a failed round trip on every single turn, so the chain is composed from
providers that answered a probe rather than from providers that have a key.

The probe is cheap, cached, and never fatal: a provider whose health is unknown is treated
as usable, because refusing to try is worse than trying and falling through.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import (
    GOOGLE_API_KEY,
    OPENROUTER_API_KEY,
    XAI_API_KEY,
    configured_providers,
    model_for,
)

# How long a probe result is trusted. Long enough that it is not run per turn, short
# enough that adding credits to an account is noticed without a restart.
TTL_SECONDS = 600.0

PROVIDER_LABEL = {
    "google": "Google Gemini",
    "openrouter": "OpenRouter",
    "xai": "xAI Grok",
}


@dataclass
class Health:
    provider: str
    reachable: bool
    checked_at: float
    detail: str = ""
    remedy: str = ""
    latency_ms: float = 0.0
    models_seen: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "label": PROVIDER_LABEL.get(self.provider, self.provider),
            "reachable": self.reachable,
            "detail": self.detail,
            "remedy": self.remedy,
            "latency_ms": round(self.latency_ms, 1),
            "models_seen": self.models_seen,
            "checked_at": dt.datetime.fromtimestamp(
                self.checked_at, dt.timezone.utc
            ).isoformat(),
            "age_seconds": round(time.time() - self.checked_at, 1),
        }


_CACHE: dict[str, Health] = {}
_LOCK = asyncio.Lock()


async def _probe(provider: str) -> Health:
    """Ask the provider whether we can use it, as cheaply as it allows."""
    import httpx

    started = time.perf_counter()

    def done(reachable: bool, detail: str, remedy: str = "", models: int = 0) -> Health:
        return Health(
            provider=provider, reachable=reachable, checked_at=time.time(),
            detail=detail, remedy=remedy, models_seen=models,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    endpoints = {
        "google": (
            "https://generativelanguage.googleapis.com/v1beta/models",
            {"x-goog-api-key": GOOGLE_API_KEY},
        ),
        "openrouter": (
            "https://openrouter.ai/api/v1/key",
            {"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        ),
        "xai": (
            "https://api.x.ai/v1/models",
            {"Authorization": f"Bearer {XAI_API_KEY}"},
        ),
    }
    target = endpoints.get(provider)
    if target is None:
        return done(True, "No probe defined; assumed usable.")

    url, headers = target
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001 — an unreachable probe is a real answer
        return done(
            False, f"{type(exc).__name__}: {exc}"[:180],
            "Check network access to the provider.",
        )

    if response.status_code == 200:
        try:
            body = response.json()
        except ValueError:
            body = {}
        rows = body.get("data") if isinstance(body, dict) else None
        count = len(rows) if isinstance(rows, list) else 0
        return done(True, "Answered.", models=count)

    detail = ""
    try:
        payload = response.json()
        detail = str(
            payload.get("error")
            or (payload.get("error") or {}).get("message")
            or payload
        )[:220]
    except ValueError:
        detail = response.text[:220]

    remedy = "Check the key."
    lowered = detail.lower()
    if "credit" in lowered or "licen" in lowered or "billing" in lowered:
        remedy = (
            "The account has no credits. Add them, and the leg joins the chain on its own "
            "at the next probe."
        )
    elif response.status_code in (401, 403):
        remedy = "The key was rejected. Check it is current and has model access."
    elif response.status_code == 429:
        remedy = "Rate-limited at the moment; the leg is kept in the chain."

    # A rate limit is not a dead provider — it is a busy one.
    reachable = response.status_code == 429
    return done(reachable, f"HTTP {response.status_code}: {detail}", remedy)


async def health(*, refresh: bool = False) -> dict[str, Health]:
    """Health for every configured provider, probed at most once per TTL."""
    async with _LOCK:
        now = time.time()
        stale = [
            p for p in configured_providers()
            if refresh
            or p not in _CACHE
            or now - _CACHE[p].checked_at > TTL_SECONDS
        ]
        if stale:
            results = await asyncio.gather(
                *(_probe(p) for p in stale), return_exceptions=True
            )
            for provider, result in zip(stale, results):
                if isinstance(result, Health):
                    _CACHE[provider] = result
                else:
                    # A probe that itself failed must not remove a provider from the chain.
                    _CACHE[provider] = Health(
                        provider=provider, reachable=True, checked_at=now,
                        detail="Probe failed; assumed usable.",
                    )
        return {p: _CACHE[p] for p in configured_providers() if p in _CACHE}


def known_health() -> dict[str, Health]:
    """Whatever has already been probed, without probing."""
    return {p: _CACHE[p] for p in configured_providers() if p in _CACHE}


def usable_providers() -> tuple[str, ...]:
    """The chain: configured providers that have not been shown to be unusable.

    Unprobed providers are included. Being optimistic and falling through costs one round
    trip; being pessimistic could leave the platform with no provider at all.
    """
    cache = known_health()
    return tuple(
        p for p in configured_providers()
        if p not in cache or cache[p].reachable
    )


def chain_report(tier: str = "fast") -> dict[str, Any]:
    """What the chain looks like, and why anything is missing from it."""
    cache = known_health()
    legs = []
    for provider in configured_providers():
        entry = cache.get(provider)
        legs.append({
            "provider": provider,
            "label": PROVIDER_LABEL.get(provider, provider),
            "model": model_for(provider, tier),
            "in_chain": entry is None or entry.reachable,
            "health": entry.as_dict() if entry else None,
        })
    return {"tier": tier, "legs": legs, "usable": list(usable_providers())}


async def prime() -> dict[str, Any]:
    """Probe once at startup so the first claim does not pay for it."""
    probed = await health(refresh=True)
    return {p: h.as_dict() for p, h in probed.items()}
