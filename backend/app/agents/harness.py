"""The agent harness — shared by every agent.

Runtime, state, budgets and circuit breakers, the agent registry and model routing all
live here, so an agent inherits them the day it is created rather than remembering to
implement them.
"""

from __future__ import annotations

import contextvars
import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import (
    BUDGETS,
    GOOGLE_API_KEY,
    MODEL_CAPABLE,
    MODEL_FAST,
    MODEL_PRICING_EUR_PER_MTOK,
    live_model_available,
    model_mode,
)

# --------------------------------------------------------------------------
# Run context
# --------------------------------------------------------------------------
@dataclass
class RunContext:
    """Everything a tool call needs that must never be supplied by the model.

    The claim reference, the tenant, the acting user and the database handle are carried
    out of band. A model cannot widen its own scope by asking for a different claim,
    because the scope is not something it is allowed to state.
    """

    run_id: str
    claim_reference: str
    tenant: str
    user_id: str
    db: Session
    language: str = "de"
    trigger: str = "customer"
    started_at: float = field(default_factory=time.perf_counter)

    # accumulated during the run
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    steps: int = 0
    budget_stops: list[str] = field(default_factory=list)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    security_events: list[dict[str, Any]] = field(default_factory=list)

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.started_at) * 1000.0, 2)


_ctx: contextvars.ContextVar[RunContext | None] = contextvars.ContextVar(
    "agentic_claims_run_context", default=None
)


def set_run_context(ctx: RunContext) -> contextvars.Token:
    return _ctx.set(ctx)


def reset_run_context(token: contextvars.Token) -> None:
    _ctx.reset(token)


def run_context() -> RunContext:
    ctx = _ctx.get()
    if ctx is None:
        raise RuntimeError(
            "No run context is active. Tools may only be called inside an agent run."
        )
    return ctx


def maybe_run_context() -> RunContext | None:
    return _ctx.get()


# --------------------------------------------------------------------------
# Budgets and circuit breakers
# --------------------------------------------------------------------------
class BudgetExceeded(RuntimeError):
    """Raised on a safe stop. The trace is preserved and no external action repeats."""


def check_budgets(ctx: RunContext) -> None:
    """A safe stop, not a crash: the run halts with its trace intact."""
    if len(ctx.tool_calls) > BUDGETS.max_tool_calls:
        ctx.budget_stops.append(f"tool_calls>{BUDGETS.max_tool_calls}")
        raise BudgetExceeded(f"Tool-call budget of {BUDGETS.max_tool_calls} exceeded — safe stop.")
    if ctx.steps > BUDGETS.max_steps:
        ctx.budget_stops.append(f"steps>{BUDGETS.max_steps}")
        raise BudgetExceeded(f"Step budget of {BUDGETS.max_steps} exceeded — safe stop.")
    total_tokens = ctx.prompt_tokens + ctx.completion_tokens
    if total_tokens > BUDGETS.max_tokens:
        ctx.budget_stops.append(f"tokens>{BUDGETS.max_tokens}")
        raise BudgetExceeded(f"Token budget of {BUDGETS.max_tokens} exceeded — safe stop.")
    if ctx.elapsed_ms() > BUDGETS.wall_clock_seconds * 1000.0:
        ctx.budget_stops.append(f"wall_clock>{BUDGETS.wall_clock_seconds}s")
        raise BudgetExceeded("Wall-clock budget exceeded — safe stop.")


# --------------------------------------------------------------------------
# FinOps
# --------------------------------------------------------------------------
def cost_eur(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = MODEL_PRICING_EUR_PER_MTOK.get(
        model_name, MODEL_PRICING_EUR_PER_MTOK["scripted-deterministic"]
    )
    return round(
        (prompt_tokens / 1_000_000.0) * price["in"]
        + (completion_tokens / 1_000_000.0) * price["out"],
        6,
    )


# --------------------------------------------------------------------------
# Agent registry — versioned agents, tools, prompts and schemas
# --------------------------------------------------------------------------
@dataclass
class AgentSpec:
    key: str
    name: str
    ordinal: int
    title: str
    description: str
    responsibility: str
    tool_scope: list[str]
    cannot: list[str]
    model_tier: str = "fast"
    version: str = "1.0.0"
    prompt_version: str = "1.0.0"
    service_identity: str = "claims-agent-runtime@allianz-at.iam"
    step_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["model"] = resolve_model_name(self.model_tier)
        return d


def resolve_model_name(tier: str) -> str:
    if not live_model_available():
        return "scripted-deterministic"
    return MODEL_CAPABLE if tier == "capable" else MODEL_FAST


def harness_status() -> dict[str, Any]:
    """What the observability page reads to describe the runtime it is watching."""
    return {
        "model_mode": model_mode(),
        "live_model_available": live_model_available(),
        "api_key_present": bool(GOOGLE_API_KEY),
        "model_fast": MODEL_FAST,
        "model_capable": MODEL_CAPABLE,
        "budgets": dataclasses.asdict(BUDGETS),
        "adk_runtime": "google-adk",
        "session_service": "InMemorySessionService (demo) / VertexAiSessionService (target)",
    }
