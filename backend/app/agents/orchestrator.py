"""The end-to-end run: fifteen steps from notification to a signed, audited outcome.

Agents recommend. Deterministic services decide. People approve.

The four assessment agents run as a real ADK ParallelAgent inside a real SequentialAgent,
so the fan-out in the architecture is the fan-out in the code. Every step emits a trace
event, which is what the console streams and what the observability page later reads back.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import time
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import ParallelAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from sqlalchemy.orm import Session

from app.agents.definitions import SPECS_BY_KEY, build_agent
from app.agents.harness import (
    BudgetExceeded,
    RunContext,
    cost_eur,
    reset_run_context,
    set_run_context,
)
from app.config import (
    AUTHORITY_LIMITS_EUR,
    DEFAULT_RUN_MODE,
    TENANT,
    THRESHOLDS,
    model_mode,
)
from app.models import (
    AgentRun,
    Claim,
    CoverageAssessment,
    Estimate,
    Message,
    SecurityEvent,
)
from app.semantic.definitions import STRUCTURAL_PANELS
from app.services import ledger
from app.services.preflight import preflight_upload, recovery_action
from app.zero_trust.adk_plugin import AGENT_NAME_TO_KEY, ZeroTrustPlugin
from app.zero_trust.crypto_guard import sign_action
from app.zero_trust.semantic_gateway import (
    PolicyAction,
    PromptFirewall,
    Surface,
    enforce_decision_policy,
    screen_customer_message,
)
from app.zero_trust.write_gateway import gateway

APP_NAME = "agentic-motor-claims"

# The fifteen steps, in the order the business flow diagram sets out.
STEPS: list[dict[str, Any]] = [
    {"no": 1,  "id": "intake.screen",         "lane": "platform", "title": "Screen everything",        "pillar": 1},
    {"no": 2,  "id": "evidence.preflight",    "lane": "platform", "title": "Preflight the evidence",   "pillar": 1},
    {"no": 3,  "id": "document.understanding","lane": "platform", "title": "Read the documents",        "pillar": None},
    {"no": 4,  "id": "intake.orchestrate",    "lane": "platform", "title": "Decide what is missing",   "pillar": None},
    {"no": 5,  "id": "coverage.assess",       "lane": "platform", "title": "Ground the coverage",      "pillar": None},
    {"no": 6,  "id": "damage.assess",         "lane": "platform", "title": "Assess the damage",        "pillar": None},
    {"no": 7,  "id": "estimate.build",        "lane": "platform", "title": "Build the estimate",       "pillar": 2},
    {"no": 8,  "id": "risk.screen",           "lane": "platform", "title": "Screen for risk",          "pillar": None},
    {"no": 9,  "id": "decision.assemble",     "lane": "platform", "title": "Assemble the decision",    "pillar": None},
    {"no": 10, "id": "policy.guard",          "lane": "platform", "title": "Apply the rules",          "pillar": 1},
    {"no": 11, "id": "hitl.route",            "lane": "people",   "title": "Route to the right person", "pillar": None},
    {"no": 12, "id": "action.sign",           "lane": "platform", "title": "Sign the action",          "pillar": 3},
    {"no": 13, "id": "write.gateway",         "lane": "platform", "title": "Verify and write once",    "pillar": 3},
    {"no": 14, "id": "comms.draft",           "lane": "customer", "title": "Explain the outcome",      "pillar": None},
    {"no": 15, "id": "observe.record",        "lane": "platform", "title": "Record and learn",         "pillar": None},
]
STEP_BY_ID = {s["id"]: s for s in STEPS}

AGENT_STEP = {
    "document_understanding": "document.understanding",
    "intake_orchestrator": "intake.orchestrate",
    "coverage": "coverage.assess",
    "damage_assessment": "damage.assess",
    "repair_estimate": "estimate.build",
    "fraud_risk": "risk.screen",
    "decision": "decision.assemble",
    "hitl_coordinator": "hitl.route",
    "customer_communication": "comms.draft",
}


class Emitter:
    """Sequenced trace events. Everything the console renders comes from here."""

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.seq = 0
        self.trace: list[dict[str, Any]] = []

    def make(
        self,
        kind: str,
        step_id: str,
        *,
        status: str = "ok",
        detail: str = "",
        agent: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seq += 1
        step = STEP_BY_ID.get(step_id, {})
        event = {
            "seq": self.seq,
            "run_id": self.ctx.run_id,
            "claim_reference": self.ctx.claim_reference,
            "kind": kind,
            "step_id": step_id,
            "step_no": step.get("no"),
            "step_title": step.get("title"),
            "lane": step.get("lane"),
            "pillar": step.get("pillar"),
            "agent": agent,
            "status": status,
            "detail": detail,
            "data": data or {},
            "elapsed_ms": self.ctx.elapsed_ms(),
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self.trace.append(event)
        return event


# --------------------------------------------------------------------------
def build_pipeline(mode: str = "auto") -> SequentialAgent:
    """Real ADK composition: read, orchestrate, fan out to assess, then decide."""
    return SequentialAgent(
        name="ClaimsPipeline",
        description="Reads the evidence, assesses in parallel, then proposes one decision.",
        sub_agents=[
            build_agent("document_understanding", mode),
            build_agent("intake_orchestrator", mode),
            ParallelAgent(
                name="AssessmentFanOut",
                description="Coverage, damage, estimate and risk assessed in parallel.",
                sub_agents=[
                    build_agent("coverage", mode),
                    build_agent("damage_assessment", mode),
                    build_agent("repair_estimate", mode),
                    build_agent("fraud_risk", mode),
                ],
            ),
            build_agent("decision", mode),
        ],
    )


async def run_claim(
    db: Session,
    reference: str,
    *,
    user_id: str = "system",
    trigger: str = "customer",
    mode: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run one claim end to end, yielding a trace event at every step.

    `mode` is "live", "deterministic", or None to follow the environment.
    """
    claim = db.get(Claim, reference)
    if claim is None:
        yield {"kind": "error", "detail": f"Claim {reference} not found."}
        return

    ctx = RunContext(
        run_id=f"run-{secrets.token_hex(5)}",
        claim_reference=reference,
        tenant=TENANT,
        user_id=user_id,
        db=db,
        language=claim.language or "de",
        trigger=trigger,
    )
    em = Emitter(ctx)
    token = set_run_context(ctx)
    plugin = ZeroTrustPlugin()
    started = time.perf_counter()

    run_mode = (mode or "auto").strip().lower()
    if run_mode == "auto":
        run_mode = DEFAULT_RUN_MODE
    if run_mode not in ("live", "hybrid", "deterministic"):
        run_mode = "hybrid"
    effective_mode = _effective_mode(run_mode)

    run_row = AgentRun(
        run_id=ctx.run_id, claim_reference=reference, status="running",
        model_mode=effective_mode, trigger=trigger,
    )
    db.add(run_row)
    db.commit()

    try:
        yield em.make(
            "run_start", "intake.screen",
            detail=f"Run {ctx.run_id} started on {reference} in {effective_mode} mode.",
            data={"model_mode": effective_mode, "steps": STEPS,
                  "requested_mode": run_mode,
                  "live_agents": _live_agent_names(run_mode)},
        )

        # -- Step 1: inbound screening ---------------------------------
        fw = PromptFirewall.inspect(claim.fnol_text or "", Surface.USER_MESSAGE)
        blocked = fw.action is PolicyAction.BLOCK
        yield em.make(
            "guard", "intake.screen",
            status="blocked" if blocked else "ok",
            detail=(
                fw.reasoning if fw.violations
                else "The customer's account of the accident passed all eight inbound rules."
            ),
            data={"firewall": fw.as_dict()},
        )
        if blocked:
            _persist_security_event(db, ctx, "injection_blocked", "high", fw.reasoning,
                                    [v.rule_id for v in fw.violations])
            claim.status = "blocked_security_review"
            db.commit()
            yield em.make("run_end", "intake.screen", status="blocked",
                          detail="Stopped at the gateway. No token was generated.",
                          data={"outcome": "blocked"})
            _finish_run(db, run_row, ctx, em, "blocked", started)
            return

        # -- Step 2: evidence preflight --------------------------------
        preflight = _run_preflight(db, claim)
        yield em.make(
            "preflight", "evidence.preflight",
            status="ok" if preflight["accepted_count"] else "blocked",
            detail=(
                f"{preflight['accepted_count']} of {preflight['total']} item(s) accepted; "
                f"{preflight['low_quality_count']} below the readable-quality threshold."
            ),
            data=preflight,
        )

        # -- Steps 3-9: the ADK pipeline -------------------------------
        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=user_id or "system"
        )
        pipeline = build_pipeline(run_mode)
        runner = Runner(
            agent=pipeline, app_name=APP_NAME,
            session_service=session_service, plugins=[plugin],
        )

        prompt = _build_prompt(claim)
        open_steps: set[str] = set()

        async for ev in runner.run_async(
            user_id=user_id or "system", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            key = AGENT_NAME_TO_KEY.get(ev.author or "")
            step_id = AGENT_STEP.get(key or "", "decision.assemble")

            if key and step_id not in open_steps:
                open_steps.add(step_id)
                yield em.make(
                    "step_start", step_id, status="running", agent=ev.author,
                    detail=f"{SPECS_BY_KEY[key].title} started.",
                    data={"tool_scope": SPECS_BY_KEY[key].tool_scope},
                )

            for part in (ev.content.parts if ev.content else []) or []:
                if part.function_call is not None:
                    yield em.make(
                        "tool_call", step_id, agent=ev.author,
                        detail=f"{ev.author} → {part.function_call.name}()",
                        data={
                            "tool": part.function_call.name,
                            "args": dict(part.function_call.args or {}),
                            "risk_class": _risk_class(part.function_call.name),
                        },
                    )
                elif part.function_response is not None:
                    response = part.function_response.response
                    sanitised = isinstance(response, dict) and "_zero_trust" in response
                    yield em.make(
                        "tool_result", step_id, agent=ev.author,
                        status="downgraded" if sanitised else "ok",
                        detail=(
                            f"{part.function_response.name} returned content that was "
                            "sanitised before the model saw it."
                            if sanitised
                            else f"{part.function_response.name} returned."
                        ),
                        data={
                            "tool": part.function_response.name,
                            "provenance": (response or {}).get("provenance")
                            if isinstance(response, dict) else None,
                            "zero_trust": (response or {}).get("_zero_trust")
                            if isinstance(response, dict) else None,
                            "result": _trim(response),
                        },
                    )
                elif part.text:
                    parsed = _try_json(part.text)
                    if key:
                        ctx.agent_outputs[key] = parsed if isinstance(parsed, dict) else {"raw": part.text}
                    yield em.make(
                        "agent_output", step_id, agent=ev.author,
                        detail=(parsed or {}).get("summary")
                        or f"{ev.author} produced its output.",
                        data={"output": parsed if parsed is not None else {"raw": part.text}},
                    )

            for event in plugin.events:
                if not event.get("_emitted"):
                    event["_emitted"] = True
                    _persist_security_event(
                        db, ctx, event["kind"], event["severity"], event["detail"],
                        event["rule_ids"], event.get("payload"),
                    )
                    yield em.make(
                        "security", step_id, status="blocked", agent=event.get("agent"),
                        detail=event["detail"],
                        data={k: v for k, v in event.items() if k != "_emitted"},
                    )

        for step_id in sorted(open_steps, key=lambda s: STEP_BY_ID[s]["no"]):
            yield em.make("step_end", step_id, detail="Complete.")

        _persist_agent_artefacts(db, claim, ctx)

        # -- Step 10: the deterministic policy guard --------------------
        package = _authoritative_package(ctx, claim)
        enforced, guard = enforce_decision_policy(package)
        ctx.agent_outputs["_guard"] = guard.as_dict()
        ctx.agent_outputs["_final"] = enforced

        yield em.make(
            "guard", "policy.guard",
            status="downgraded" if not guard.passed else "ok",
            detail=guard.reasoning,
            data={
                "guard": guard.as_dict(),
                "proposed_decision": guard.original_decision,
                "final_decision": enforced.get("decision"),
                "settlement_amount_eur": enforced.get("settlement_amount_eur"),
            },
        )

        # -- Step 11: route to a person --------------------------------
        routing = _routing_for(guard, enforced, claim)
        ctx.agent_outputs["_routing"] = routing
        task_info: dict[str, Any] = {}

        if routing["needs_human"]:
            hitl_session = await session_service.create_session(
                app_name=APP_NAME, user_id=user_id or "system"
            )
            hitl_runner = Runner(
                agent=build_agent("hitl_coordinator", mode), app_name=APP_NAME,
                session_service=session_service, plugins=[plugin],
            )
            yield em.make(
                "step_start", "hitl.route", status="running",
                agent="HitlCoordinatorAgent",
                detail=f"Routing to the {routing['queue']} queue: {routing['reason']}.",
                data=routing,
            )
            async for ev in hitl_runner.run_async(
                user_id=user_id or "system", session_id=hitl_session.id,
                new_message=types.Content(role="user", parts=[types.Part(
                    text=f"Create the review task for {reference}. {routing['reason_detail']}"
                )]),
            ):
                for part in (ev.content.parts if ev.content else []) or []:
                    if part.function_call is not None:
                        yield em.make(
                            "tool_call", "hitl.route", agent=ev.author,
                            detail=f"{ev.author} → {part.function_call.name}()",
                            data={"tool": part.function_call.name,
                                  "args": dict(part.function_call.args or {}),
                                  "risk_class": _risk_class(part.function_call.name)},
                        )
                    elif part.function_response is not None:
                        yield em.make(
                            "tool_result", "hitl.route", agent=ev.author,
                            detail=f"{part.function_response.name} returned.",
                            data={"tool": part.function_response.name,
                                  "result": _trim(part.function_response.response)},
                        )
                    elif part.text:
                        parsed = _try_json(part.text) or {}
                        ctx.agent_outputs["hitl_coordinator"] = parsed
                        task_info = parsed.get("task") or {}
                        yield em.make(
                            "agent_output", "hitl.route", agent=ev.author,
                            detail=parsed.get("summary", "Review task created."),
                            data={"output": parsed},
                        )
            yield em.make("step_end", "hitl.route", detail="Complete.")
        else:
            yield em.make(
                "step_end", "hitl.route", status="ok",
                detail="No human touch required — every deterministic check passed.",
                data={"needs_human": False},
            )

        # -- Step 12: sign the action ----------------------------------
        action, payload, requires_approval = _action_for(enforced, routing, claim, task_info)
        envelope = sign_action(
            payload=payload,
            nonce=ledger.next_nonce(db),
            claim_id=reference,
            run_id=ctx.run_id,
            step_id="action.sign",
            agent_id=routing["signing_agent"],
            action=action,
            user_id=user_id or "system",
            prev_hash=ledger.last_chain_hash(db),
        )
        yield em.make(
            "sign", "action.sign",
            detail=(
                f"Action '{action}' canonicalised and signed with nonce "
                f"{envelope.nonce} by {envelope.signer}."
            ),
            data={"envelope": {k: v for k, v in envelope.as_dict().items() if k != "payload"},
                  "payload_keys": sorted(payload)},
        )

        # -- Step 13: the Secure Write Gateway --------------------------
        write = gateway.submit(
            envelope.as_dict(),
            requires_approval=requires_approval,
            amount_eur=float(payload.get("settlement_amount_eur") or 0.0),
        )
        ledger.append(
            db, envelope.as_dict(),
            status="VERIFIED_AUTHENTIC" if write.accepted else "REJECTED_AT_GATEWAY",
        )
        yield em.make(
            "write", "write.gateway",
            status="ok" if write.accepted else "blocked",
            detail=write.reason,
            data={"gateway": write.as_dict(), "nonce": envelope.nonce},
        )

        if write.accepted:
            _apply_write(db, claim, enforced, routing, write.committed_ref)

        # -- Step 14: explain the outcome ------------------------------
        comms_session = await session_service.create_session(
            app_name=APP_NAME, user_id=user_id or "system"
        )
        comms_runner = Runner(
            agent=build_agent("customer_communication", mode), app_name=APP_NAME,
            session_service=session_service, plugins=[plugin],
        )
        yield em.make("step_start", "comms.draft", status="running",
                      agent="CustomerCommunicationAgent",
                      detail="Drafting the customer-safe explanation.")
        async for ev in comms_runner.run_async(
            user_id=user_id or "system", session_id=comms_session.id,
            new_message=types.Content(role="user", parts=[types.Part(
                text=f"Write the customer message for {reference}."
            )]),
        ):
            for part in (ev.content.parts if ev.content else []) or []:
                if part.function_call is not None:
                    yield em.make("tool_call", "comms.draft", agent=ev.author,
                                  detail=f"{ev.author} → {part.function_call.name}()",
                                  data={"tool": part.function_call.name,
                                        "args": dict(part.function_call.args or {}),
                                        "risk_class": _risk_class(part.function_call.name)})
                elif part.function_response is not None:
                    yield em.make("tool_result", "comms.draft", agent=ev.author,
                                  detail=f"{part.function_response.name} returned.",
                                  data={"tool": part.function_response.name,
                                        "result": _trim(part.function_response.response)})
                elif part.text:
                    parsed = _try_json(part.text) or {}
                    ctx.agent_outputs["customer_communication"] = parsed

                    # The outbound guard always applies. A message that leaks platform
                    # internals, hints at an investigation, or quotes a figure the
                    # decision does not carry is withheld rather than sent.
                    comms_guard = screen_customer_message(
                        parsed.get("body") or "",
                        approved_amount_eur=float(enforced.get("settlement_amount_eur") or 0.0),
                    )
                    parsed["outbound_guard"] = comms_guard.as_dict()
                    _persist_message(db, claim, parsed, comms_guard)

                    yield em.make(
                        "agent_output", "comms.draft", agent=ev.author,
                        status="ok" if comms_guard.passed else "blocked",
                        detail=(
                            "Customer message drafted from an approved template and "
                            "cleared the outbound guard."
                            if comms_guard.passed
                            else comms_guard.reasoning
                        ),
                        data={"output": parsed, "outbound_guard": comms_guard.as_dict()},
                    )
        yield em.make("step_end", "comms.draft", detail="Complete.")

        # -- Step 15: record and learn ---------------------------------
        summary = _finish_run(
            db, run_row, ctx, em,
            "completed",
            started,
            outcome=enforced.get("decision"),
            run_mode=run_mode,
        )
        yield em.make(
            "run_end", "observe.record", status="ok",
            detail=(
                f"{enforced.get('decision')} — {summary['tool_calls']} tool calls, "
                f"{summary['total_tokens']:,} tokens, EUR {summary['cost_eur']:.4f}."
            ),
            data={
                "summary": summary,
                "final": enforced,
                "guard": guard.as_dict(),
                "routing": routing,
                "agent_outputs": ctx.agent_outputs,
            },
        )

    except BudgetExceeded as exc:
        yield em.make("run_end", "observe.record", status="stopped", detail=str(exc),
                      data={"budget_stops": ctx.budget_stops})
        _finish_run(db, run_row, ctx, em, "stopped", started, outcome="safe_stop", run_mode=run_mode)
    except Exception as exc:  # noqa: BLE001 — a failed run must still leave a trace
        # A hung run is worse than a failed one. Whatever went wrong, the trace comes
        # back and the reason is stated in words an operator can act on.
        yield em.make(
            "run_end", "observe.record", status="failed",
            detail=_explain_failure(exc),
            data={
                "error_type": type(exc).__name__,
                "error": str(exc)[:600],
                "remedy": _remedy_for(exc),
                "completed_steps": ctx.steps,
                "tool_calls": len(ctx.tool_calls),
            },
        )
        _finish_run(db, run_row, ctx, em, "failed", started, outcome="error", run_mode=run_mode)
        return
    finally:
        reset_run_context(token)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _throttle_stats() -> dict[str, Any]:
    try:
        from app.agents.throttle import limiter

        return limiter.stats()
    except Exception:  # noqa: BLE001 — telemetry must never break a run
        return {}


def _explain_failure(exc: Exception) -> str:
    """Say what actually went wrong, in the operator's language."""
    text = str(exc).lower()
    name = type(exc).__name__

    if "resourceexhausted" in name.lower() or "429" in text or "quota" in text:
        return (
            "The model provider refused the request: the project's Gemini quota is "
            "exhausted. The run stopped cleanly and no partial decision was written."
        )
    if "not_found" in text or "404" in text:
        return (
            "The configured Gemini model is not available to this project. Set MODEL_FAST "
            "and MODEL_CAPABLE to models the project can actually call."
        )
    if "permission" in text or "401" in text or "403" in text:
        return (
            "The model provider rejected the credentials. Check GOOGLE_API_KEY, or the "
            "Vertex project and location."
        )
    if "deadline" in text or "timeout" in text:
        return "The model provider timed out. The run stopped cleanly with its trace intact."
    return f"{name}: {str(exc)[:240]}"


def _remedy_for(exc: Exception) -> str:
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    if "resourceexhausted" in name or "429" in text or "quota" in text:
        return (
            "Re-run in deterministic mode to continue the demonstration, or raise the "
            "project's quota. Every control below the model runs identically either way."
        )
    if "not_found" in text or "404" in text:
        return "Update MODEL_FAST / MODEL_CAPABLE in backend/.env."
    return "Retry the run; if it persists, check the backend logs."


def _authoritative_package(ctx: RunContext, claim: Claim) -> dict[str, Any]:
    """Assemble the package the guard evaluates.

    The model contributes exactly one thing: the proposed decision and its reasoning.
    Every number and every status the guard checks is read from the tool outputs and the
    claim record — the coverage position from the Coverage agent's cited retrieval, the
    totals from the sandboxed calculation, the risk score from the recorded signals, and
    the injury flag from the system of record. A model cannot move a figure by restating
    it, and where it does restate one, PG-10 compares the two.
    """
    out = ctx.agent_outputs
    proposal = out.get("decision") or {}
    coverage = out.get("coverage") or {}
    estimate = out.get("repair_estimate") or {}
    damage = out.get("damage_assessment") or {}
    risk = out.get("fraud_risk") or {}
    # TriageResult is flat, not nested under an "evidence" key. Reading a nested one
    # silently turned a measured completeness into 0.0 — and 0.0 is not a neutral default
    # here: it is the value that says "we have nothing", which is a different claim.
    triage = out.get("intake_orchestrator") or {}

    decision = str(proposal.get("decision") or "Review Required").strip() or "Review Required"

    total = _num(estimate.get("total_cost"))
    excess = _num(coverage.get("excess_eur"))
    approving = decision.lower() in ("approved", "approve", "auto-approved")

    indemnity = _indemnity_basis(out, claim, gross_repair=total)
    settlement = round(max(indemnity["gross"] - excess, 0.0), 2) if approving else 0.0

    # A claim whose indemnity does not clear the excess pays nothing. The cover position
    # is still "approved" — that is what the guard evaluates — but the outcome is a nil
    # settlement, and the file closes rather than promising money. Telling a customer a
    # claim is "geprüft und freigegeben" when nothing will be paid is the wrong answer on
    # the highest-frequency small motor claim there is.
    below_excess = approving and 0.0 < indemnity["gross"] <= excess
    if below_excess:
        settlement = 0.0

    claimed_estimate = proposal.get("estimate") or {}

    return {
        "claim_reference": claim.reference,
        "decision": decision,
        "reasoning": proposal.get("reasoning"),
        "settlement_amount_eur": settlement,
        "indemnity": indemnity,
        "below_excess": below_excess,
        "severity": damage.get("severity") or claim.severity,
        "structural_damage": bool(damage.get("structural_damage")),
        # Never taken from the model: the claim record is the authority on injury.
        "injury_reported": bool(claim.injury_reported),
        "coverage": {
            "status": coverage.get("status") or "unknown",
            "excess_eur": excess,
            "citations": coverage.get("citations") or [],
            "clauses_applied": coverage.get("clauses_applied") or [],
            "reasoning": coverage.get("reasoning"),
            "abstained": bool(coverage.get("abstained")),
        },
        "estimate": {
            "total_cost": total,
            "total_parts": _num(estimate.get("total_parts")),
            "total_labour": _num(estimate.get("total_labour")),
            "total_tax": _num(estimate.get("total_tax")),
            "labour_hours": _num(estimate.get("labour_hours")),
            "labour_rate_eur": _num(estimate.get("labour_rate_eur")),
            "items": estimate.get("items") or [],
            "reasonableness": estimate.get("reasonableness"),
        },
        "risk": {
            "score": _num(risk.get("score")),
            "signals": risk.get("signals") or [],
            "recommendation": risk.get("recommendation"),
        },
        "evidence": {
            "missing": list(triage.get("missing") or []),
            "unreadable": list(triage.get("unreadable") or []),
            "completeness": _num(triage.get("evidence_completeness")),
            "next_step": triage.get("next_step") or "",
            "questions": list(triage.get("customer_questions") or []),
        },
        "model_restatement": {
            "total_cost": _num(claimed_estimate.get("total_cost")),
            "settlement_amount_eur": _num(proposal.get("settlement_amount_eur")),
        },
    }


def _indemnity_basis(
    out: dict[str, Any], claim: Claim, *, gross_repair: float
) -> dict[str, Any]:
    """What the indemnity is measured on, before the excess comes off.

    The repair estimate is only the basis where the vehicle is being repaired. On a total
    loss the basis is the replacement value less salvage (AKKB Art 5.1.2), and where the
    schedule carries Neuwertersatz and the vehicle is inside the endorsement's window the
    basis is the new price instead. Settling every claim on the repair estimate — which is
    what this did — underpays a total loss by the whole difference between a repair bill
    and a vehicle, and makes the Neuwertersatz endorsement sold to the customer inert.
    """
    total_loss = out.get("total_loss") or {}
    verdict = str(total_loss.get("verdict") or "")

    if verdict != "total_loss":
        return {
            "basis": "repair_cost",
            "gross": round(gross_repair, 2),
            "clause": "AKKB Art 5.2",
            "explanation": "Partial damage: the indemnity is the cost of restoring the vehicle.",
        }

    replacement = _num(total_loss.get("replacement_value_eur"))
    residual = _num(total_loss.get("residual_value_eur"))
    payable = _num(total_loss.get("payable_on_total_loss_eur")) or round(
        max(replacement - residual, 0.0), 2
    )

    # Neuwertersatz, where the schedule actually carries it and the age test passes.
    endorsements = (out.get("coverage") or {}).get("endorsements") or []
    has_new_for_old = any(
        (e.get("code") or "").upper() == "ZB-NEUWERT" for e in endorsements
    )
    if has_new_for_old and bool(total_loss.get("new_for_old_available")):
        new_price = _num(total_loss.get("new_price_eur")) or round(replacement * 1.35, 2)
        return {
            "basis": "new_for_old",
            "gross": round(max(new_price - residual, 0.0), 2),
            "clause": "AKKB Art 5.1.2 · ZB-NEUWERT",
            "explanation": (
                "Total loss inside the Neuwertersatz window, so the basis is the new price "
                "rather than the replacement value, less salvage."
            ),
        }

    return {
        "basis": "total_loss",
        "gross": payable,
        "clause": "AKKB Art 5.1.1 · 5.1.2",
        "explanation": (
            f"Total loss: replacement value EUR {replacement:,.2f} less salvage of "
            f"EUR {residual:,.2f}."
        ),
    }


def _num(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _build_prompt(claim: Claim) -> str:
    return (
        f"Claim {claim.reference} has been notified.\n"
        f"Incident: {claim.incident_type} on {claim.incident_date} at "
        f"{claim.incident_location or claim.incident_city}.\n"
        f"The customer's account, verbatim:\n---\n{claim.fnol_text}\n---\n"
        "Work the claim within your own scope."
    )


def _risk_class(tool_name: str) -> str:
    from app.agents.tools import TOOL_RISK_CLASS

    return TOOL_RISK_CLASS.get(tool_name, "unclassified")


def _try_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _trim(value: Any, limit: int = 4000) -> Any:
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)[:limit]
    if len(text) <= limit:
        return value
    return {"_truncated": True, "preview": text[:limit] + "…"}


def _run_preflight(db: Session, claim: Claim) -> dict[str, Any]:
    """Re-run the preflight checks over the evidence already on the claim."""
    seen: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    low_quality = 0

    for doc in claim.documents:
        payload = (doc.ocr_text or doc.filename or "").encode("utf-8")
        result = preflight_upload(
            filename=doc.filename or doc.doc_id,
            mime_type=doc.mime_type or "application/octet-stream",
            payload=payload or b"x",
            page_count=doc.page_count or 1,
            known_hashes=seen,
        )
        seen[result.sha256] = doc.doc_id
        quality = doc.quality_score or 0.0
        action = recovery_action(quality)
        if quality < 0.55:
            low_quality += 1
        items.append({
            "doc_id": doc.doc_id,
            "filename": doc.filename,
            "kind": doc.kind,
            "doc_type": doc.doc_type,
            "mime_type": doc.mime_type,
            "size_bytes": doc.size_bytes,
            "page_count": doc.page_count,
            "quality_score": quality,
            "quality_action": action,
            "verdict": result.verdict,
            "checks": result.checks,
            "notes": result.notes + (doc.preflight_notes or []),
        })

    return {
        "total": len(items),
        "accepted_count": sum(1 for i in items if i["verdict"] in ("clean", "duplicate")),
        "low_quality_count": low_quality,
        "items": items,
    }


def _queue_from_signals(
    enforced: dict[str, Any], claim: Claim, value: float
) -> tuple[str, str, str]:
    """Which queue a claim belongs on, read from the claim rather than from the model.

    Used when a decision needs a person but no guard check forced it — the agent asked for
    review on its own. The claim's own facts decide who sees it.
    """
    risk_score = float((enforced.get("risk") or {}).get("score") or 0.0)
    coverage_status = str((enforced.get("coverage") or {}).get("status") or "unknown")

    if claim.injury_reported:
        return (
            "injury", "injury_reported",
            "Injury reported — the claim is handled by the bodily-injury team.",
        )
    if risk_score > THRESHOLDS.max_fraud_score_for_autonomy:
        return (
            "siu", "fraud_signal_elevated",
            f"Composite risk score {risk_score:.2f} is above the autonomy threshold of "
            f"{THRESHOLDS.max_fraud_score_for_autonomy:.2f} — referred for investigation "
            "with the evidence trail preserved.",
        )
    if not coverage_status.startswith("covered"):
        return (
            "coverage", "coverage_uncertain_or_excluded",
            f"Coverage position is '{coverage_status}' — referred to a coverage adjuster.",
        )
    if value > AUTHORITY_LIMITS_EUR["claim_handler"]:
        return (
            "operations", "agent_requested_review",
            f"Automation stopped on a claim valued at EUR {value:,.2f}, which is above "
            "handler authority.",
        )
    return (
        "handler", "agent_requested_review",
        "Automation did not reach an outcome it could issue on its own, so a person "
        "decides.",
    )


def _routing_for(guard, enforced: dict[str, Any], claim: Claim) -> dict[str, Any]:
    """Where the claim goes, decided from which checks failed — not from a prompt."""
    failed = {c.check_id for c in guard.checks if not c.passed}
    amount = float(enforced.get("settlement_amount_eur") or 0.0)
    estimate_total = float((enforced.get("estimate") or {}).get("total_cost") or 0.0)
    value = max(amount, estimate_total)
    decision = enforced.get("decision")

    if decision == "Request Information":
        return {
            "needs_human": False, "queue": None, "reason": "awaiting_customer",
            "reason_detail": "Outstanding evidence has been requested from the customer.",
            "signing_agent": "IntakeOrchestratorAgent",
            "failed_checks": sorted(failed),
        }

    if not failed:
        # An approval that clears every check is finished. Anything else is not — a
        # decision of "Review Required" means review is required, whether the guard
        # forced it or the agent asked for it itself, and the queue is derived from the
        # claim's own signals rather than from what the model said about them.
        if enforced.get("below_excess"):
            return {
                "needs_human": False, "queue": None, "reason": "below_excess",
                "reason_detail": (
                    "The assessed amount does not exceed the excess, so there is nothing "
                    "to pay and nothing to approve."
                ),
                "signing_agent": "DecisionAgent",
                "failed_checks": [],
            }
        if decision.lower() in ("approved", "approve", "auto-approved"):
            return {
                "needs_human": False, "queue": None, "reason": "straight_through",
                "reason_detail": (
                    "Every deterministic check passed within the autonomous limit."
                ),
                "signing_agent": "DecisionAgent",
                "failed_checks": [],
            }

        queue, reason, detail = _queue_from_signals(enforced, claim, value)
        return {
            "needs_human": True,
            "queue": queue,
            "reason": reason,
            "reason_detail": detail,
            "signing_agent": "HitlCoordinatorAgent",
            "failed_checks": [],
            "authority_required": _authority_for_queue(queue),
        }

    if "PG-07" in failed:
        queue, reason, detail = ("injury", "injury_reported",
            "Injury reported — financial auto-adjudication stopped and referred to the "
            "bodily-injury team.")
    elif "PG-08" in failed:
        queue, reason, detail = ("siu", "fraud_signal_elevated",
            "Composite risk score above the autonomy threshold — autonomous progression "
            "frozen and the evidence trail preserved.")
    elif failed & {"PG-04", "PG-06"}:
        queue, reason, detail = ("coverage", "coverage_uncertain_or_excluded",
            "The coverage position could not be autonomously relied upon — referred to a "
            "coverage adjuster.")
    elif "PG-09" in failed:
        queue, reason, detail = ("coverage", "adverse_decision_review",
            "An adverse outcome is never issued autonomously — a named person confirms it.")
    elif "PG-05" in failed:
        queue, reason, detail = ("handler", "evidence_incomplete",
            "Required evidence is incomplete for the decision proposed.")
    elif failed & {"PG-01", "PG-02", "PG-03"}:
        queue = "operations" if value > AUTHORITY_LIMITS_EUR["claim_handler"] else "handler"
        reason = "ceiling_or_severity"
        detail = (
            f"EUR {value:,.2f} with severity '{enforced.get('severity')}' is outside the "
            f"autonomous limit of EUR {THRESHOLDS.auto_approval_ceiling_eur:,.2f}."
        )
    else:
        queue, reason, detail = ("handler", "policy_guard_violation",
            "One or more deterministic checks failed.")

    return {
        "needs_human": True,
        "queue": queue,
        "reason": reason,
        "reason_detail": detail,
        "signing_agent": "HitlCoordinatorAgent",
        "failed_checks": sorted(failed),
        "authority_required": _authority_for_queue(queue),
    }


AUTHORITY_BY_QUEUE: dict[str, str] = {
    "operations": "compliance_ops",
    "large_loss": "compliance_ops",
    "recovery": "claim_handler",
    "supervisor": "compliance_ops",   # older name for the same queue
    "injury": "compliance_ops",
    "siu": "siu",
    "assessment": "motor_assessor",
    "handler": "claim_handler",
    "coverage": "claim_handler",
    "security": "compliance_ops",
}


def _authority_for_queue(queue: str | None) -> str:
    """Which persona's authority a queue demands."""
    return AUTHORITY_BY_QUEUE.get(queue or "", "claim_handler")


def _action_for(
    enforced: dict[str, Any], routing: dict[str, Any], claim: Claim,
    task_info: dict[str, Any],
) -> tuple[str, dict[str, Any], bool]:
    """What is actually written, and whether a human approval is required first.

    An autonomous approval inside the ceiling needs no approval reference — that is what
    the ceiling *is*. Anything else writes a status change and a review task, and the
    settlement waits for a person.
    """
    decision = enforced.get("decision")

    if not routing["needs_human"] and decision == "Approved":
        payload = {
            "claim_id": claim.reference,
            "decision": "Approved",
            "settlement_amount_eur": float(enforced.get("settlement_amount_eur") or 0.0),
            "severity": enforced.get("severity"),
            "status": "approved",
            "coverage_clauses": (enforced.get("coverage") or {}).get("citations") and [
                c.get("clause_id") for c in (enforced.get("coverage") or {}).get("citations") or []
            ] or [],
            "estimate_total_eur": float((enforced.get("estimate") or {}).get("total_cost") or 0.0),
            "policy_guard": enforced.get("policy_enforcement"),
        }
        return "claim.settlement.write", payload, False

    payload = {
        "claim_id": claim.reference,
        "decision": enforced.get("decision"),
        "proposed_decision": enforced.get("original_decision"),
        "settlement_amount_eur": 0.0,
        "severity": enforced.get("severity"),
        "status": "awaiting_customer" if decision == "Request Information" else "in_review",
        "queue": routing.get("queue"),
        "reason": routing.get("reason"),
        "review_task_id": task_info.get("task_id"),
        "violations": (enforced.get("policy_enforcement") or {}).get("violations") or [],
    }
    return "claim.status.write", payload, False


def _apply_write(
    db: Session, claim: Claim, enforced: dict[str, Any], routing: dict[str, Any],
    committed_ref: str | None,
) -> None:
    decision = enforced.get("decision")
    claim.decision = decision
    claim.severity = enforced.get("severity") or claim.severity
    claim.structural_damage = bool(enforced.get("structural_damage"))
    claim.fraud_score = float((enforced.get("risk") or {}).get("score") or 0.0)
    claim.evidence_completeness = float(
        (enforced.get("evidence") or {}).get("completeness") or 0.0
    )
    claim.assigned_queue = routing.get("queue")

    if not routing["needs_human"] and decision == "Approved" and enforced.get("below_excess"):
        claim.status = "closed_without_payment"
        claim.stage = "closed"
        claim.settlement_amount_eur = 0.0
        claim.straight_through = True
        claim.closed_at = dt.datetime.now(dt.timezone.utc)
    elif not routing["needs_human"] and decision == "Approved":
        claim.status = "approved"
        claim.stage = "settlement"
        claim.settlement_amount_eur = float(enforced.get("settlement_amount_eur") or 0.0)
        claim.straight_through = True
        claim.closed_at = dt.datetime.now(dt.timezone.utc)
    elif decision == "Request Information":
        claim.status = "awaiting_customer"
        claim.stage = "intake"
    else:
        claim.status = "in_review"
        claim.stage = "human_review"
        claim.settlement_amount_eur = 0.0
        claim.human_touches = (claim.human_touches or 0) + 1
    db.commit()


def _persist_agent_artefacts(db: Session, claim: Claim, ctx: RunContext) -> None:
    coverage = ctx.agent_outputs.get("coverage") or {}
    if coverage:
        db.add(CoverageAssessment(
            claim_reference=claim.reference,
            status=coverage.get("status"),
            excess_eur=float(coverage.get("excess_eur") or 0.0),
            reasoning=coverage.get("reasoning"),
            citations=coverage.get("citations") or [],
            clauses_applied=coverage.get("clauses_applied") or [],
            confidence=float(coverage.get("confidence") or 0.0),
        ))

    est = ctx.agent_outputs.get("repair_estimate") or {}
    if est.get("total_cost") is not None:
        db.add(Estimate(
            claim_reference=claim.reference,
            items=est.get("items") or [],
            labour_hours=float(est.get("labour_hours") or 0.0),
            labour_rate_eur=float(est.get("labour_rate_eur") or 0.0),
            total_parts=float(est.get("total_parts") or 0.0),
            total_labour=float(est.get("total_labour") or 0.0),
            total_tax=float(est.get("total_tax") or 0.0),
            total_cost=float(est.get("total_cost") or 0.0),
            reasonableness_band=(est.get("reasonableness") or {}).get("verdict"),
            sandbox_telemetry=(est.get("sandbox") or {}).get("telemetry") or {},
        ))

    damage = ctx.agent_outputs.get("damage_assessment") or {}
    if damage.get("severity"):
        claim.severity = damage["severity"]
        claim.structural_damage = bool(damage.get("structural_damage")) or any(
            p.get("panel") in STRUCTURAL_PANELS for p in damage.get("panels") or []
        )
    db.commit()


def _persist_message(db: Session, claim: Claim, parsed: dict[str, Any], guard=None) -> None:
    if not parsed.get("body"):
        return
    db.add(Message(
        message_id=f"MSG-{secrets.token_hex(4).upper()}",
        claim_reference=claim.reference,
        channel="portal",
        language=parsed.get("language") or claim.language,
        template_id=parsed.get("template_id"),
        subject=parsed.get("subject"),
        body=parsed.get("body"),
        tone=parsed.get("tone") or "plain",
        status="drafted" if (guard is None or guard.passed) else "blocked",
        guard_findings=(guard.findings if guard is not None else []),
    ))
    db.commit()


def _persist_security_event(
    db: Session, ctx: RunContext, kind: str, severity: str, detail: str,
    rule_ids: list[str], payload: dict[str, Any] | None = None,
) -> None:
    db.add(SecurityEvent(
        event_id=f"SEC-{secrets.token_hex(5).upper()}",
        claim_reference=ctx.claim_reference,
        run_id=ctx.run_id,
        kind=kind,
        severity=severity,
        rule_ids=rule_ids,
        detail=detail,
        payload=payload or {},
    ))
    db.commit()


def _effective_mode(run_mode: str) -> str:
    """What the run will actually use, after the environment has its say."""
    from app.config import live_model_available

    if run_mode == "deterministic" or not live_model_available():
        return "scripted-deterministic"
    if run_mode == "hybrid":
        return "hybrid-gemini"
    return model_mode()


def _live_agent_names(run_mode: str) -> list[str]:
    """Which agents will actually reason on a model in this run."""
    from app.agents.definitions import AGENT_SPECS, wants_live

    return [s.name for s in AGENT_SPECS if wants_live(s, run_mode)]


def _finish_run(
    db: Session, run_row: AgentRun, ctx: RunContext, em: Emitter, status: str,
    started: float, outcome: str | None = None, run_mode: str = "auto",
) -> dict[str, Any]:
    from app.agents.harness import resolve_model_name

    effective = _effective_mode(run_mode)
    model_name = (
        "scripted-deterministic"
        if effective == "scripted-deterministic"
        else resolve_model_name("fast")
    )
    total_tokens = ctx.prompt_tokens + ctx.completion_tokens
    cost = cost_eur(model_name, ctx.prompt_tokens, ctx.completion_tokens)

    run_row.status = status
    run_row.outcome = outcome
    run_row.ended_at = dt.datetime.now(dt.timezone.utc)
    run_row.duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    run_row.steps_completed = ctx.steps
    run_row.tool_calls = len(ctx.tool_calls)
    run_row.prompt_tokens = ctx.prompt_tokens
    run_row.completion_tokens = ctx.completion_tokens
    run_row.cost_eur = cost
    run_row.budget_stops = ctx.budget_stops
    run_row.trace = em.trace
    db.commit()

    return {
        "run_id": ctx.run_id,
        "status": status,
        "outcome": outcome,
        "duration_ms": run_row.duration_ms,
        "steps": ctx.steps,
        "tool_calls": len(ctx.tool_calls),
        "prompt_tokens": ctx.prompt_tokens,
        "completion_tokens": ctx.completion_tokens,
        "total_tokens": total_tokens,
        "cost_eur": cost,
        "cost_basis": "metered" if model_name != "scripted-deterministic" else "modelled",
        "model": model_name,
        "model_mode": effective,
        "live_agents": _live_agent_names(run_mode),
        "throttle": _throttle_stats(),
        "security_events": len(ctx.security_events),
        "budget_stops": ctx.budget_stops,
    }
