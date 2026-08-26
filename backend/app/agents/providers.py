"""Pluggable agent runtimes.

One orchestrator, three ways to serve a reasoning turn:

  * **pydantic-ai** — the default. The agent's output type is a Pydantic model, so the
    result is validated before anything downstream sees it, and the model is re-asked when
    validation fails rather than a malformed answer being passed on.
  * **google-adk** — the runtime the target architecture names. Same agents, same tools.
  * **deterministic** — no model at all. Fixed tool trajectory, answer synthesised from
    the real tool results.

The zero-trust controls do not live in any of them. They live in the tool wrapper and in
the graph nodes, so they apply identically whichever runtime is serving — which is the
property worth demonstrating: swapping the model out does not swap the controls out.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.harness import maybe_run_context
from app.agents.throttle import limiter_for
from app.config import (
    MODEL_RETRY_ATTEMPTS,
    MODEL_THINKING_BUDGET,
    OPENROUTER_API_KEY,
    XAI_API_KEY,
    live_model_available,
    model_for,
    resolve_model_name_for,
    resolve_provider,
)
from app.schemas import schema_for
from app.services.tracing import Trace
from app.zero_trust.adk_plugin import _compact_for_model, _screen_tree

RUNTIMES = ("pydantic-ai", "google-adk", "deterministic")
DEFAULT_RUNTIME = "pydantic-ai"


@dataclass
class ReasonResult:
    output: BaseModel | None
    raw: dict[str, Any]
    runtime: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_eur: float = 0.0
    latency_ms: float = 0.0
    throttle_wait_ms: float = 0.0
    validation_retries: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    security_findings: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.output is not None and self.error is None


def coerce_to(schema: type[BaseModel], raw: dict[str, Any]) -> BaseModel:
    """Validate a dict against a strict contract, ignoring anything it does not name.

    Internal synthesisers legitimately carry more than the contract does — the extra is
    dropped here rather than the contract being loosened, so a model that invents a field
    is still rejected.
    """
    named = {k: v for k, v in (raw or {}).items() if k in schema.model_fields}
    return schema.model_validate(named)


# --------------------------------------------------------------------------
# Guarded tools — the controls, applied once, for every runtime
# --------------------------------------------------------------------------
def guarded_tool(
    fn: Callable[..., dict[str, Any]],
    *,
    agent_name: str,
    trace: Trace | None,
    sink: list[dict[str, Any]],
    findings_sink: list[dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    """Wrap a typed business tool in the zero-trust controls.

    Tool output is data, never instruction: anything a tool hands back that originated
    outside the platform is screened, smuggled instructions are stripped, and the result is
    trimmed to what a decision needs before it enters the model's context.
    """
    from app.agents.tools import TOOL_RISK_CLASS

    name = fn.__name__

    def _run(**kwargs: Any) -> dict[str, Any]:
        started = time.perf_counter()
        ctx = maybe_run_context()
        entry: dict[str, Any] = {
            "tool": name,
            "agent": agent_name,
            "risk_class": TOOL_RISK_CLASS.get(name, "unclassified"),
            "args": {k: (str(v)[:120] if isinstance(v, str) else v) for k, v in kwargs.items()},
            "claim_id": ctx.claim_reference if ctx else None,
            "run_id": ctx.run_id if ctx else None,
        }
        try:
            result = fn(**kwargs)
        except Exception as exc:  # noqa: BLE001 — a tool failure is data, not a crash
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            entry["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
            sink.append(entry)
            return {"error": entry["error"], "tool": name}

        if isinstance(result, dict):
            findings: list[dict[str, Any]] = []
            result = _screen_tree(result, findings)
            trimmed: list[str] = []
            result = _compact_for_model(result, trimmed)
            if findings:
                findings_sink.extend(findings)
                result["_zero_trust"] = {
                    "sanitised": True,
                    "findings": findings,
                    "note": (
                        "Retrieved content was treated as data. Instruction-shaped markup "
                        "was removed before this result entered the model context."
                    ),
                }
                entry["sanitised"] = True
            if trimmed:
                result["_context_budget"] = {"trimmed": sorted(set(trimmed))[:12]}

        entry["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        sink.append(entry)

        if trace is not None:
            with trace.span(f"tool.{name}", "tool", **entry["args"]) as span:
                span.outputs = {"provenance": (result or {}).get("provenance")
                                if isinstance(result, dict) else None}
                span.metadata = {"risk_class": entry["risk_class"],
                                 "sanitised": bool(entry.get("sanitised"))}
        return result

    _run.__name__ = name
    _run.__doc__ = fn.__doc__
    # pydantic-ai reads the signature to build the tool schema, so carry it across.
    _run.__signature__ = __import__("inspect").signature(fn)  # type: ignore[attr-defined]
    _run.__annotations__ = dict(getattr(fn, "__annotations__", {}))
    return _run


# --------------------------------------------------------------------------
# pydantic-ai
# --------------------------------------------------------------------------
_MODEL_CACHE: dict[str, Any] = {}

# The wait the last request spent queued, so a run can report time lost to quota rather
# than hiding it in the latency.
LAST_WAIT_MS: dict[str, float] = {"google": 0.0, "openrouter": 0.0, "xai": 0.0}


def _throttled_google_model(model_name: str):
    """A GoogleModel that stays inside the project's quota."""
    key = f"google:{model_name}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    import os

    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    class ThrottledGoogleModel(GoogleModel):
        async def request(self, messages, model_settings, model_request_parameters):
            LAST_WAIT_MS["google"] = round(
                await limiter_for("google").acquire() * 1000.0, 2
            )
            return await super().request(messages, model_settings, model_request_parameters)

    model = ThrottledGoogleModel(
        model_name, provider=GoogleProvider(api_key=os.environ.get("GOOGLE_API_KEY", ""))
    )
    _MODEL_CACHE[key] = model
    return model


def _throttled_openrouter_model(model_name: str):
    """An OpenRouter model, kept polite against a pool it shares with everybody else."""
    key = f"openrouter:{model_name}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    class ThrottledOpenRouterModel(OpenAIChatModel):
        async def request(self, messages, model_settings, model_request_parameters):
            LAST_WAIT_MS["openrouter"] = round(
                await limiter_for("openrouter").acquire() * 1000.0, 2
            )
            return await super().request(messages, model_settings, model_request_parameters)

    model = ThrottledOpenRouterModel(
        model_name, provider=OpenRouterProvider(api_key=OPENROUTER_API_KEY)
    )
    _MODEL_CACHE[key] = model
    return model


def _throttled_xai_model(model_name: str):
    """An xAI Grok model, rate-limited like the others."""
    key = f"xai:{model_name}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from pydantic_ai.models.xai import XaiModel
    from pydantic_ai.providers.xai import XaiProvider

    class ThrottledXaiModel(XaiModel):
        async def request(self, messages, model_settings, model_request_parameters):
            LAST_WAIT_MS["xai"] = round(
                await limiter_for("xai").acquire() * 1000.0, 2
            )
            return await super().request(messages, model_settings, model_request_parameters)

    model = ThrottledXaiModel(
        model_name, provider=XaiProvider(api_key=XAI_API_KEY)
    )
    _MODEL_CACHE[key] = model
    return model


_BUILDERS = {
    "google": _throttled_google_model,
    "openrouter": _throttled_openrouter_model,
    "xai": _throttled_xai_model,
}


def _leg(provider: str, tier: str):
    builder = _BUILDERS.get(provider, _throttled_google_model)
    return builder(model_for(provider, tier))


def chain_for(tier: str) -> list[str]:
    """The providers this tier will try, in order.

    A provider that a health probe has shown cannot be called is left out — putting a dead
    leg first costs a failed round trip on every turn. Anything unprobed is kept in.
    """
    from app.agents.model_health import usable_providers

    provider = resolve_provider()
    if provider in ("google", "openrouter", "xai"):
        return [provider]

    usable = list(usable_providers())
    return usable or ["google"]


def build_model(tier: str):
    """The model — or chain of models — a tier resolves to.

    More than one provider is not redundancy for its own sake: one project's quota is a
    single ceiling, and a run that stops at it is a run that stopped. Where several are
    reachable this returns a FallbackModel over them in preference order, so a refusal on
    one continues on the next.
    """
    providers = chain_for(tier)
    legs = [_leg(p, tier) for p in providers]

    if len(legs) == 1:
        return legs[0], providers[0]

    from pydantic_ai.models.fallback import FallbackModel

    return FallbackModel(*legs), "→".join(providers)


def model_chain_description(tier: str) -> dict[str, Any]:
    """What the platform will actually try, in order."""
    providers = chain_for(tier)
    return {
        "tier": tier,
        "provider": resolve_provider(),
        "chain": [{"provider": p, "model": model_for(p, tier)} for p in providers],
    }


def _model_settings():
    from pydantic_ai.models.google import GoogleModelSettings

    settings: dict[str, Any] = {"temperature": 0.1, "max_tokens": 2048}
    if MODEL_THINKING_BUDGET is not None:
        settings["google_thinking_config"] = {"thinking_budget": MODEL_THINKING_BUDGET}
    return GoogleModelSettings(**settings)


async def _reason_pydantic_ai(
    agent_key: str,
    agent_name: str,
    instruction: str,
    prompt: str,
    tools: list[Callable[..., Any]],
    output_type: type[BaseModel],
    trace: Trace | None,
    tier: str,
) -> ReasonResult:
    from pydantic_ai import Agent

    model, chain_label = build_model(tier)
    model_name = resolve_model_name_for(tier)
    tool_calls: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    wrapped = [
        guarded_tool(t, agent_name=agent_name, trace=trace, sink=tool_calls,
                     findings_sink=findings)
        for t in tools
    ]

    agent = Agent(
        model,
        output_type=output_type,
        instructions=instruction,
        tools=wrapped,
        model_settings=_model_settings(),
        # A failed validation is re-asked rather than passed on. This is the whole point
        # of a typed contract.
        retries=2,
        name=agent_name,
    )

    started = time.perf_counter()
    try:
        result = await agent.run(prompt)
    except Exception as exc:  # noqa: BLE001 — classified by the caller
        return ReasonResult(
            output=None, raw={}, runtime="pydantic-ai", model=model_name,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
            tool_calls=tool_calls, security_findings=findings,
            error=f"{type(exc).__name__}: {exc}"[:400],
        )

    usage = result.usage
    output = result.output
    # Which model actually answered — the fallback may not be the one we asked first.
    answered_by = _answered_by(result) or model_name
    return ReasonResult(
        output=output,
        raw=output.model_dump() if isinstance(output, BaseModel) else {},
        runtime="pydantic-ai",
        model=answered_by,
        prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cost_eur=float(getattr(usage, "cost", 0.0) or 0.0),
        latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
        throttle_wait_ms=max(LAST_WAIT_MS.values()),
        validation_retries=max(0, int(getattr(usage, "requests", 1) or 1) - 1 - len(tool_calls)),
        tool_calls=tool_calls,
        security_findings=findings,
    )


# --------------------------------------------------------------------------
# deterministic
# --------------------------------------------------------------------------
async def _reason_deterministic(
    agent_key: str,
    agent_name: str,
    tools: list[Callable[..., Any]],
    output_type: type[BaseModel],
    trace: Trace | None,
) -> ReasonResult:
    """Walk the agent's fixed tool trajectory, then answer from the real results."""
    from app.agents.scripted_model import PLANS, SYNTHESISERS

    tool_calls: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    by_name = {t.__name__: t for t in tools}
    wrapped = {
        name: guarded_tool(fn, agent_name=agent_name, trace=trace, sink=tool_calls,
                           findings_sink=findings)
        for name, fn in by_name.items()
    }

    started = time.perf_counter()
    results: dict[str, Any] = {}
    for tool_name, arg_builder in PLANS.get(agent_key, []):
        fn = wrapped.get(tool_name)
        if fn is None:
            continue
        args = arg_builder(results) if arg_builder else {}
        results[tool_name] = fn(**args)

    synth = SYNTHESISERS.get(agent_key)
    raw = synth(results) if synth else {}
    prompt_chars = len(json.dumps(results, default=str))
    completion_chars = len(json.dumps(raw, default=str))

    try:
        output = coerce_to(output_type, raw)
        error = None
    except ValidationError as exc:
        output = None
        error = f"ValidationError: {exc.errors()[:2]}"[:400]

    return ReasonResult(
        output=output, raw=raw, runtime="deterministic",
        model="scripted-deterministic",
        prompt_tokens=max(1, prompt_chars // 4),
        completion_tokens=max(1, completion_chars // 4),
        latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
        tool_calls=tool_calls, security_findings=findings, error=error,
    )


# --------------------------------------------------------------------------
# google-adk
# --------------------------------------------------------------------------
async def _reason_adk(
    agent_key: str,
    agent_name: str,
    prompt: str,
    output_type: type[BaseModel],
    trace: Trace | None,
    tier: str,
) -> ReasonResult:
    """Run the agent on Google ADK and validate what comes back."""
    from google.genai import types as genai_types

    from app.agents.definitions import build_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    from app.zero_trust.adk_plugin import ZeroTrustPlugin

    model_name = resolve_model_name_for(tier)
    plugin = ZeroTrustPlugin()
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="claims", user_id="system")
    agent = build_agent(agent_key, "live" if live_model_available() else "deterministic")
    runner = Runner(agent=agent, app_name="claims",
                    session_service=session_service, plugins=[plugin])

    tool_calls: list[dict[str, Any]] = []
    prompt_tokens = completion_tokens = 0
    text = ""
    started = time.perf_counter()

    try:
        async for ev in runner.run_async(
            user_id="system", session_id=session.id,
            new_message=genai_types.Content(role="user",
                                            parts=[genai_types.Part(text=prompt)]),
        ):
            if ev.usage_metadata is not None:
                prompt_tokens += ev.usage_metadata.prompt_token_count or 0
                completion_tokens += ev.usage_metadata.candidates_token_count or 0
            for part in (ev.content.parts if ev.content else []) or []:
                if part.function_call is not None:
                    tool_calls.append({
                        "tool": part.function_call.name, "agent": agent_name,
                        "args": dict(part.function_call.args or {}),
                    })
                elif part.text:
                    text += part.text
    except Exception as exc:  # noqa: BLE001
        return ReasonResult(
            output=None, raw={}, runtime="google-adk", model=model_name,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
            tool_calls=tool_calls,
            error=f"{type(exc).__name__}: {exc}"[:400],
        )

    raw = _parse_json(text) or {}
    try:
        output = coerce_to(output_type, raw)
        error = None
    except ValidationError as exc:
        output = None
        error = f"ValidationError: {exc.errors()[:2]}"[:400]

    return ReasonResult(
        output=output, raw=raw, runtime="google-adk", model=model_name,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
        tool_calls=tool_calls,
        security_findings=[e for e in plugin.events],
        error=error,
    )


def _answered_by(result: Any) -> str | None:
    """Read the model name off the response, so a fallback is visible rather than implied."""
    try:
        for message in reversed(result.all_messages()):
            name = getattr(message, "model_name", None)
            if name:
                return str(name)
    except Exception:  # noqa: BLE001 — provenance must never break a run
        return None
    return None


def _parse_json(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        parts = stripped.split("```")
        if len(parts) > 1:
            stripped = parts[1]
            if stripped.startswith("json"):
                stripped = stripped[4:]
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if 0 <= start < end:
            try:
                parsed = json.loads(stripped[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None


# --------------------------------------------------------------------------
# The one entry point
# --------------------------------------------------------------------------
async def reason(
    agent_key: str,
    *,
    prompt: str,
    runtime: str = DEFAULT_RUNTIME,
    trace: Trace | None = None,
) -> ReasonResult:
    """Serve one agent's reasoning turn on the requested runtime.

    Falls back to the deterministic provider when the requested runtime cannot reach a
    model, so a missing key degrades the reasoning rather than the platform.
    """
    from app.agents.definitions import INSTRUCTIONS, SPECS_BY_KEY
    from app.agents.tools import TOOL_SCOPE

    spec = SPECS_BY_KEY[agent_key]
    output_type = schema_for(agent_key)
    if output_type is None:
        raise ValueError(f"No typed contract registered for agent '{agent_key}'.")

    tools = list(TOOL_SCOPE.get(agent_key, []))
    instruction = INSTRUCTIONS.get(agent_key, "").strip()

    effective = runtime
    if runtime in ("pydantic-ai", "google-adk") and not live_model_available():
        effective = "deterministic"

    span_name = f"agent.{spec.name}"
    if trace is not None:
        with trace.span(span_name, "llm", runtime=effective, agent=spec.name) as span:
            result = await _dispatch(effective, agent_key, spec, instruction, prompt,
                                     tools, output_type, trace)
            span.outputs = {"ok": result.ok, "error": result.error}
            span.metadata = {
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "tool_calls": len(result.tool_calls),
                "validation_retries": result.validation_retries,
            }
            return result

    return await _dispatch(effective, agent_key, spec, instruction, prompt, tools,
                           output_type, trace)


async def _dispatch(runtime, agent_key, spec, instruction, prompt, tools, output_type, trace):
    if runtime == "pydantic-ai":
        return await _reason_pydantic_ai(agent_key, spec.name, instruction, prompt,
                                         tools, output_type, trace, spec.model_tier)
    if runtime == "google-adk":
        return await _reason_adk(agent_key, spec.name, prompt, output_type, trace,
                                 spec.model_tier)
    return await _reason_deterministic(agent_key, spec.name, tools, output_type, trace)
