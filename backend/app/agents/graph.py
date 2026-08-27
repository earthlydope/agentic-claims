"""The claim graph — LangGraph owns the orchestration.

The fifteen lifecycle stages are nodes. The exception paths are conditional edges. That
matters for more than tidiness: a claim's route through the platform is now a thing you can
read, draw and test, rather than control flow buried in a function. The four assessment
stages fan out and the decision waits for all of them, because that is what the
architecture says happens.

Agents recommend. Deterministic services decide. People approve.

Inside an agent node the reasoning turn is served by whichever runtime the run asked for —
pydantic-ai, Google ADK, or none at all. The controls do not live in the runtime; they live
here and in the tool wrapper, so swapping the model out does not swap the controls out.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import operator
import secrets
import time
from collections.abc import AsyncGenerator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.harness import (
    BudgetExceeded,
    RunContext,
    check_budgets,
    reset_run_context,
    set_run_context,
)
from app.agents.providers import DEFAULT_RUNTIME, ReasonResult, reason
from app.config import DEFAULT_RUN_MODE, TENANT, live_model_available
from app.lifecycle import STAGE_BY_ID, STAGES, stage_dicts
from app.models import AgentRun, Claim
from app.personas import persona as get_persona
from app.services import llm_usage
from app.services.tracing import Trace
from app.zero_trust.semantic_gateway import (
    PolicyAction,
    PromptFirewall,
    Surface,
    enforce_decision_policy,
    screen_customer_message,
)

# The deterministic claim services the graph calls into. They are not agents and they are
# not optional — they are what decides.
from app.agents.orchestrator import (  # noqa: E402
    _apply_write,
    _authoritative_package,
    _persist_agent_artefacts,
    _persist_message,
    _persist_security_event,
    _routing_for,
    _run_preflight,
    _explain_failure,
    _remedy_for,
)
from app.services import ledger  # noqa: E402
from app.zero_trust.crypto_guard import sign_action  # noqa: E402
from app.zero_trust.write_gateway import gateway  # noqa: E402


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer for the parallel assessment branches writing into one dict."""
    return {**(left or {}), **(right or {})}


class ClaimState(TypedDict, total=False):
    reference: str
    run_id: str
    persona: str
    user_id: str
    runtime: str
    prompt: str
    # Per-agent additions to the shared prompt, keyed by agent. Used where one stage needs
    # something the others must not see — the message writer being told what to ask for.
    prompt_addendum: dict[str, str]

    events: Annotated[list[dict[str, Any]], operator.add]
    outputs: Annotated[dict[str, Any], _merge]

    halted: bool
    halt_reason: str
    guard: dict[str, Any]
    routing: dict[str, Any]
    final: dict[str, Any]
    envelope: dict[str, Any]
    write: dict[str, Any]


# --------------------------------------------------------------------------
# Event bus — nodes emit, the driver streams
# --------------------------------------------------------------------------
class Bus:
    """Live trace events out of a running graph.

    LangGraph reports a node when it finishes; a claims console needs to show the tool
    call while it is happening. So nodes push onto this queue and the driver drains it in
    parallel with the graph.
    """

    def __init__(self, run_id: str, reference: str) -> None:
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.run_id = run_id
        self.reference = reference
        self.seq = 0
        self.trail: list[dict[str, Any]] = []
        self.started = time.perf_counter()

    def emit(
        self, kind: str, stage_id: str, *, status: str = "ok", detail: str = "",
        agent: str | None = None, data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seq += 1
        stage = STAGE_BY_ID.get(stage_id)
        event = {
            "seq": self.seq,
            "run_id": self.run_id,
            "claim_reference": self.reference,
            "kind": kind,
            "stage_id": stage_id,
            "step_id": stage_id,          # the console reads either name
            "step_no": stage.no if stage else None,
            "step_title": stage.title if stage else None,
            "lane": stage.lane if stage else None,
            "owner": stage.owner if stage else None,
            "pillar": stage.pillar if stage else None,
            "agent": agent,
            "status": status,
            "detail": detail,
            "data": data or {},
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000.0, 2),
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self.trail.append(event)
        self.queue.put_nowait(event)
        return event

    def close(self) -> None:
        self.queue.put_nowait(None)


# --------------------------------------------------------------------------
# Node helpers
# --------------------------------------------------------------------------
def _agent_node(agent_key: str, stage_id: str):
    """Build the node that runs one agent at one stage."""

    async def node(state: ClaimState) -> dict[str, Any]:
        from app.agents.definitions import SPECS_BY_KEY

        spec = SPECS_BY_KEY[agent_key]
        bus: Bus = _BUS.get()
        ctx = _CTX.get()
        trace: Trace = _TRACE.get()

        bus.emit("step_start", stage_id, status="running", agent=spec.name,
                 detail=f"{spec.title} started.",
                 data={"tool_scope": spec.tool_scope, "runtime": state["runtime"]})

        ctx.steps += 1
        try:
            check_budgets(ctx)
        except BudgetExceeded as exc:
            bus.emit("step_end", stage_id, status="stopped", agent=spec.name,
                     detail=str(exc))
            return {"events": [], "halted": True, "halt_reason": str(exc)}

        prompt = state["prompt"]
        extra = state.get("prompt_addendum") or {}
        if agent_key in extra:
            prompt = f"{prompt}\n\n{extra[agent_key]}"

        result: ReasonResult = await reason(
            agent_key, prompt=prompt, runtime=state["runtime"], trace=trace,
        )

        for call in result.tool_calls:
            ctx.tool_calls.append(call)
            bus.emit("tool_call", stage_id, agent=spec.name,
                     detail=f"{spec.name} → {call['tool']}()",
                     data={"tool": call["tool"], "args": call.get("args") or {},
                           "risk_class": call.get("risk_class"),
                           "sanitised": bool(call.get("sanitised"))})

        for finding in result.security_findings:
            _persist_security_event(
                _CTX.get().db, ctx, "retrieved_content_sanitised", "high",
                f"Untrusted content returned to {spec.name} was stripped before the model "
                "saw it.",
                list(finding.get("rule_ids") or []), finding,
            )
            ctx.security_events.append(finding)
            bus.emit("security", stage_id, status="blocked", agent=spec.name,
                     detail=("Instruction-shaped content was stripped from a tool result "
                             "before it entered the model context."),
                     data=finding)

        ctx.prompt_tokens += result.prompt_tokens
        ctx.completion_tokens += result.completion_tokens
        llm_usage.record(
            ctx.db, model=result.model, runtime=result.runtime,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            agent=spec.name, persona=state.get("persona"), purpose="claim_run",
            claim_reference=state["reference"], run_id=state["run_id"],
            latency_ms=result.latency_ms, throttle_wait_ms=result.throttle_wait_ms,
            outcome="ok" if result.ok else ("quota" if result.error and "quota" in
                                            result.error.lower() else "error"),
            error=result.error,
            cost_eur=result.cost_eur or None,
        )

        if not result.ok:
            bus.emit("step_end", stage_id, status="failed", agent=spec.name,
                     detail=_explain_failure(RuntimeError(result.error or "unknown")),
                     data={"error": result.error, "remedy": _remedy_for(
                         RuntimeError(result.error or ""))})
            return {"events": [], "halted": True,
                    "halt_reason": result.error or f"{spec.name} produced no valid output."}

        payload = result.raw
        ctx.agent_outputs[agent_key] = payload

        bus.emit("agent_output", stage_id, agent=spec.name,
                 detail=payload.get("summary") or f"{spec.name} produced its output.",
                 data={"output": payload, "contract": type(result.output).__name__,
                       "runtime": result.runtime, "model": result.model,
                       "validation_retries": result.validation_retries})
        bus.emit("step_end", stage_id, agent=spec.name, detail="Complete.")

        return {"events": [], "outputs": {agent_key: payload}}

    node.__name__ = f"node_{agent_key}"
    return node


# Context handles for the nodes. LangGraph nodes take only state, so the run's context,
# bus and trace travel out of band — the same reason a tool never takes a claim id from
# the model.
import contextvars  # noqa: E402

_BUS: contextvars.ContextVar[Bus] = contextvars.ContextVar("claim_bus")
_CTX: contextvars.ContextVar[RunContext] = contextvars.ContextVar("claim_ctx")
_TRACE: contextvars.ContextVar[Trace] = contextvars.ContextVar("claim_trace")


# --------------------------------------------------------------------------
# Deterministic nodes
# --------------------------------------------------------------------------
async def node_screen(state: ClaimState) -> dict[str, Any]:
    """Pillar 1 inbound. Nothing reaches a model before this."""
    bus, ctx, trace = _BUS.get(), _CTX.get(), _TRACE.get()
    claim = ctx.db.get(Claim, state["reference"])

    with trace.span("stage.screen", "guard", reference=state["reference"]) as span:
        result = PromptFirewall.inspect(claim.fnol_text or "", Surface.USER_MESSAGE)
        span.outputs = {"action": result.action.value, "risk": result.risk_score}

    blocked = result.action is PolicyAction.BLOCK
    bus.emit("guard", "screen", status="blocked" if blocked else "ok",
             detail=(result.reasoning if result.violations
                     else "The customer's account passed every inbound rule."),
             data={"firewall": result.as_dict()})

    if blocked:
        _persist_security_event(ctx.db, ctx, "injection_blocked", "high",
                                result.reasoning,
                                [v.rule_id for v in result.violations])
        claim.status = "blocked_security_review"
        ctx.db.commit()
        return {"events": [], "halted": True,
                "halt_reason": "Stopped at the gateway. No token was generated."}

    preflight = _run_preflight(ctx.db, claim)
    bus.emit("preflight", "screen",
             detail=(f"{preflight['accepted_count']} of {preflight['total']} item(s) "
                     f"accepted; {preflight['low_quality_count']} below the readable "
                     "threshold."),
             data=preflight)
    return {"events": []}


async def node_guard(state: ClaimState) -> dict[str, Any]:
    """The deterministic policy guard. Ten checks, in versioned code outside the prompt."""
    bus, ctx, trace = _BUS.get(), _CTX.get(), _TRACE.get()
    claim = ctx.db.get(Claim, state["reference"])

    _persist_agent_artefacts(ctx.db, claim, ctx)

    with trace.span("stage.guard", "guard") as span:
        package = _authoritative_package(ctx, claim)
        # The repairability verdict is part of what the guard must see.
        verdict = (state.get("outputs") or {}).get("total_loss") or {}
        if verdict.get("verdict") == "total_loss":
            package["total_loss"] = True
            package["structural_damage"] = True
        enforced, guard = enforce_decision_policy(package)
        span.outputs = {"passed": guard.passed,
                        "failed": [c.check_id for c in guard.checks if not c.passed]}

    ctx.agent_outputs["_guard"] = guard.as_dict()
    ctx.agent_outputs["_final"] = enforced

    bus.emit("guard", "guard", status="ok" if guard.passed else "downgraded",
             detail=guard.reasoning,
             data={"guard": guard.as_dict(),
                   "proposed_decision": guard.original_decision,
                   "final_decision": enforced.get("decision"),
                   "settlement_amount_eur": enforced.get("settlement_amount_eur")})

    routing = _routing_for(guard, enforced, claim)
    if verdict.get("verdict") == "total_loss" and routing["needs_human"]:
        routing["queue"] = "assessment"
        routing["reason"] = "total_loss"
        routing["reason_detail"] = (
            f"Repair cost is {verdict.get('ratio', 0) * 100:.1f}% of replacement value — "
            "the assessor confirms the total loss before anything is settled."
        )
    ctx.agent_outputs["_routing"] = routing

    return {"events": [], "guard": guard.as_dict(), "final": enforced, "routing": routing}


async def node_settle(state: ClaimState) -> dict[str, Any]:
    """Pillar 3. Sign, verify at the gateway, write once."""
    from app.agents.orchestrator import _action_for

    bus, ctx, trace = _BUS.get(), _CTX.get(), _TRACE.get()
    claim = ctx.db.get(Claim, state["reference"])
    enforced = state.get("final") or {}
    routing = state.get("routing") or {}
    task_info = (state.get("outputs") or {}).get("hitl_coordinator") or {}

    action, payload, requires_approval = _action_for(enforced, routing, claim, task_info)

    with trace.span("stage.settle", "write", action=action) as span:
        envelope = sign_action(
            payload=payload, nonce=ledger.next_nonce(ctx.db),
            claim_id=state["reference"], run_id=state["run_id"], step_id="settle",
            agent_id=routing.get("signing_agent") or "DecisionAgent",
            action=action, user_id=state["user_id"],
            prev_hash=ledger.last_chain_hash(ctx.db),
        )
        bus.emit("sign", "settle",
                 detail=(f"Action '{action}' canonicalised and signed with nonce "
                         f"{envelope.nonce} by {envelope.signer}."),
                 data={"envelope": {k: v for k, v in envelope.as_dict().items()
                                    if k != "payload"},
                       "payload_keys": sorted(payload)})

        write = gateway.submit(envelope.as_dict(), requires_approval=requires_approval,
                              amount_eur=float(payload.get("settlement_amount_eur") or 0.0))
        ledger.append(ctx.db, envelope.as_dict(),
                      status="VERIFIED_AUTHENTIC" if write.accepted
                      else "REJECTED_AT_GATEWAY")
        span.outputs = {"accepted": write.accepted, "reason": write.reason}

    bus.emit("write", "settle", status="ok" if write.accepted else "blocked",
             detail=write.reason,
             data={"gateway": write.as_dict(), "nonce": envelope.nonce})

    if write.accepted:
        _apply_write(ctx.db, claim, enforced, routing, write.committed_ref)

    return {"events": [], "envelope": envelope.as_dict(), "write": write.as_dict()}


async def node_close(state: ClaimState) -> dict[str, Any]:
    """Close the file, and make sure the run leaves a trace worth reading."""
    bus, ctx = _BUS.get(), _CTX.get()
    claim = ctx.db.get(Claim, state["reference"])
    final = state.get("final") or {}
    recovery = (state.get("outputs") or {}).get("recovery") or {}

    if claim is not None and claim.status == "approved" and not recovery.get("recoverable"):
        claim.status = "settled"
        ctx.db.commit()
    elif claim is not None and recovery.get("recoverable"):
        claim.status = "recovery_open"
        ctx.db.commit()

    bus.emit("step_end", "close",
             detail=(f"{final.get('decision', 'Recorded')} — file at "
                     f"'{claim.status if claim else 'unknown'}'."),
             data={"recovery": recovery})
    return {"events": []}


def _non_fatal(node, stage_id: str):
    """Let a bookkeeping stage fail loudly without losing the claim.

    The guard has already decided by this point. If creating the review task fails, that is
    a problem to surface — but dropping the claim on the floor is a worse one.
    """

    async def wrapped(state: ClaimState) -> dict[str, Any]:
        result = await node(state)
        if result.get("halted"):
            _BUS.get().emit(
                "step_end", stage_id, status="failed",
                detail=(f"{stage_id} did not complete: {result.get('halt_reason', '')}. "
                        "The decision still stands and nothing partial was written."),
                data={"error": result.get("halt_reason")},
            )
            return {"events": [], "outputs": result.get("outputs") or {}}
        return result

    wrapped.__name__ = getattr(node, "__name__", "wrapped")
    return wrapped


def _assessor_node():
    """The estimate and the repairability call, in one node.

    They belong together: the total-loss test is arithmetic on the estimate, so it can only
    run once there is an estimate to test. Keeping them in one node also keeps the four
    assessment branches at the same depth, which is what makes the decision wait for all
    four exactly once — LangGraph schedules a fan-in node as soon as any of its inbound
    edges fires, so uneven depth would run the decision twice.
    """
    estimate = _agent_node("repair_estimate", "estimate")
    repairability = _agent_node("total_loss", "total_loss")

    async def node(state: ClaimState) -> dict[str, Any]:
        first = await estimate(state)
        if first.get("halted"):
            return first
        merged = {**(state.get("outputs") or {}), **(first.get("outputs") or {})}
        second = await repairability({**state, "outputs": merged})
        return {
            "events": [],
            "outputs": {**(first.get("outputs") or {}), **(second.get("outputs") or {})},
            **({"halted": True, "halt_reason": second.get("halt_reason", "")}
               if second.get("halted") else {}),
        }

    node.__name__ = "node_assess_damage_cost"
    return node


def _comms_node():
    inner = _agent_node("customer_communication", "close")

    async def node(state: ClaimState) -> dict[str, Any]:
        bus, ctx = _BUS.get(), _CTX.get()
        # A "Request Information" letter that does not say what information is worse than
        # no letter — the customer now knows something is wrong and cannot act on it. So
        # the specific asks are put in front of the writer, taken from the decision and the
        # triage rather than from the model's memory of the run.
        state = {**state, "prompt_addendum": {
            **(state.get("prompt_addendum") or {}),
            "customer_communication": _what_to_ask_for(state),
        }}
        out = await inner(state)
        payload = (out.get("outputs") or {}).get("customer_communication") or {}
        if payload:
            claim = ctx.db.get(Claim, state["reference"])
            guard = screen_customer_message(
                payload.get("body") or "",
                approved_amount_eur=float(
                    (state.get("final") or {}).get("settlement_amount_eur") or 0.0),
            )
            payload["outbound_guard"] = guard.as_dict()
            _persist_message(ctx.db, claim, payload, guard)
            bus.emit("guard", "close", status="ok" if guard.passed else "blocked",
                     detail=("The customer message cleared the outbound guard."
                             if guard.passed else guard.reasoning),
                     data={"outbound_guard": guard.as_dict()})
        return out

    node.__name__ = "node_comms"
    return node


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
def _what_to_ask_for(state: ClaimState) -> str:
    """The instruction the message writer needs when something is being requested."""
    final = state.get("final") or {}
    decision = str(final.get("decision") or "")
    evidence = final.get("evidence") or {}
    outputs = state.get("outputs") or {}

    if decision != "Request Information":
        return ""

    asks: list[str] = []
    asks.extend(str(q) for q in (evidence.get("questions") or []) if q)
    asks.extend(str(m).replace("_", " ") for m in (evidence.get("missing") or []) if m)
    for gap in (outputs.get("intake_orchestrator") or {}).get("needs_confirmation") or []:
        if isinstance(gap, dict) and gap.get("ask"):
            asks.append(str(gap["ask"]))
    for gap in (outputs.get("intake_orchestrator") or {}).get("unreadable") or []:
        if isinstance(gap, dict) and gap.get("ask"):
            asks.append(str(gap["ask"]))

    # The decision's own reasoning is the fallback, and often the only place the reason
    # lives — a coverage condition the customer has not met is not "missing evidence".
    reasoning = str((outputs.get("decision") or {}).get("reasoning") or "")

    lines = [
        "THIS CLAIM IS ASKING THE CUSTOMER FOR SOMETHING. The message must say plainly, "
        "in one short paragraph, exactly what they need to send and why, and it must be "
        "the first thing after the greeting. Do not write a generic 'we are reviewing "
        "your claim' letter.",
    ]
    if asks:
        lines.append("What to ask for, in the customer's own language:")
        lines.extend(f"- {a}" for a in dict.fromkeys(asks))
    if reasoning:
        lines.append(f"Why it is needed (do not quote clause numbers to them): {reasoning}")
    lines.append(
        "Say how to send it and that the claim continues as soon as it arrives. Do not "
        "quote any amount.",
    )
    return "\n".join(lines)


def _after_screen(state: ClaimState) -> str:
    return "halt" if state.get("halted") else "continue"


def _after_guard(state: ClaimState) -> str:
    if state.get("halted"):
        return "halt"
    return "approval" if (state.get("routing") or {}).get("needs_human") else "settle"


def _after_settle(state: ClaimState) -> str:
    """A settled claim with a third party in it goes to recovery before it closes."""
    claim_settled = bool((state.get("write") or {}).get("accepted")) and (
        (state.get("final") or {}).get("decision") == "Approved"
    )
    return "recovery" if claim_settled else "comms"


def _halt_guard(name: str):
    """Skip a node cleanly once the run has halted, rather than running it anyway."""

    def check(state: ClaimState) -> str:
        return "halt" if state.get("halted") else name

    return check


# --------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------
def build_graph():
    g = StateGraph(ClaimState)

    g.add_node("screen", node_screen)
    g.add_node("intake", _agent_node("document_understanding", "intake"))
    g.add_node("triage", _agent_node("intake_orchestrator", "triage"))
    g.add_node("coverage", _agent_node("coverage", "coverage"))
    g.add_node("damage", _agent_node("damage_assessment", "damage"))
    g.add_node("estimate", _assessor_node())
    g.add_node("risk", _agent_node("fraud_risk", "risk"))
    g.add_node("decision", _agent_node("decision", "decision"))
    g.add_node("guard", node_guard)
    g.add_node("approval", _non_fatal(_agent_node("hitl_coordinator", "approval"),
                                      "approval"))
    g.add_node("settle", node_settle)
    g.add_node("recovery", _agent_node("recovery", "recovery"))
    g.add_node("comms", _comms_node())
    g.add_node("close", node_close)

    g.add_edge(START, "screen")
    g.add_conditional_edges("screen", _after_screen,
                            {"continue": "intake", "halt": END})
    g.add_conditional_edges("intake", _halt_guard("triage"),
                            {"triage": "triage", "halt": END})

    # The four assessments fan out, exactly as the architecture draws them.
    for branch in ("coverage", "damage", "estimate", "risk"):
        g.add_edge("triage", branch)

    # The decision waits for every branch. All four sit at the same depth, so it runs
    # once, with everything in hand.
    for branch in ("coverage", "damage", "estimate", "risk"):
        g.add_edge(branch, "decision")

    g.add_edge("decision", "guard")
    g.add_conditional_edges("guard", _after_guard,
                            {"approval": "approval", "settle": "settle", "halt": END})
    g.add_edge("approval", "settle")
    g.add_conditional_edges("settle", _after_settle,
                            {"recovery": "recovery", "comms": "comms"})
    g.add_edge("recovery", "comms")
    g.add_edge("comms", "close")
    g.add_edge("close", END)

    return g.compile(checkpointer=InMemorySaver())


_GRAPH = None


def graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def graph_shape() -> dict[str, Any]:
    """What the graph actually looks like, read off the compiled graph itself."""
    compiled = graph()
    drawn = compiled.get_graph()
    return {
        "orchestrator": "langgraph",
        "nodes": sorted(n for n in drawn.nodes if not n.startswith("__")),
        "edges": [
            {"from": e.source, "to": e.target,
             "conditional": bool(getattr(e, "conditional", False))}
            for e in drawn.edges
        ],
        "stages": stage_dicts(),
        "mermaid": drawn.draw_mermaid(),
    }


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def _build_prompt(claim: Claim) -> str:
    return (
        f"Claim {claim.reference} has been notified.\n"
        f"Incident: {claim.incident_type} on {claim.incident_date} at "
        f"{claim.incident_location or claim.incident_city}.\n"
        f"The customer's account, verbatim:\n---\n{claim.fnol_text}\n---\n"
        "Work the claim within your own scope."
    )


async def run_claim(
    db: Session,
    reference: str,
    *,
    user_id: str = "system",
    trigger: str = "customer",
    mode: str | None = None,
    runtime: str | None = None,
    persona: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run one claim through the graph, streaming a trace event at every step."""
    claim = db.get(Claim, reference)
    if claim is None:
        yield {"kind": "error", "detail": f"Claim {reference} not found."}
        return

    run_mode = (mode or DEFAULT_RUN_MODE).strip().lower()
    chosen_runtime = (runtime or DEFAULT_RUNTIME).strip().lower()
    if run_mode == "deterministic" or not live_model_available():
        chosen_runtime = "deterministic"

    run_id = f"run-{secrets.token_hex(5)}"
    ctx = RunContext(run_id=run_id, claim_reference=reference, tenant=TENANT,
                     user_id=user_id, db=db, language=claim.language or "de",
                     trigger=trigger)
    bus = Bus(run_id, reference)
    trace = Trace("claim.run", metadata={"claim": reference, "run_id": run_id,
                                         "runtime": chosen_runtime,
                                         "persona": persona or "system"})

    run_row = AgentRun(run_id=run_id, claim_reference=reference, status="running",
                       model_mode=chosen_runtime, trigger=trigger)
    db.add(run_row)
    db.commit()

    tokens = (set_run_context(ctx), _BUS.set(bus), _CTX.set(ctx), _TRACE.set(trace))
    started = time.perf_counter()

    initial: ClaimState = {
        "reference": reference, "run_id": run_id,
        "persona": persona or "system", "user_id": user_id,
        "runtime": chosen_runtime, "prompt": _build_prompt(claim),
        "events": [], "outputs": {}, "halted": False, "halt_reason": "",
        "guard": {}, "routing": {}, "final": {}, "envelope": {}, "write": {},
    }

    bus.emit("run_start", "notify",
             detail=f"Run {run_id} started on {reference} — {chosen_runtime}.",
             data={"runtime": chosen_runtime, "mode": run_mode,
                   "stages": stage_dicts(), "orchestrator": "langgraph"})

    async def drive() -> ClaimState:
        try:
            return await graph().ainvoke(
                initial, config={"configurable": {"thread_id": run_id},
                                 "recursion_limit": 60},
            )
        finally:
            bus.close()

    task = asyncio.create_task(drive())

    try:
        while True:
            event = await bus.queue.get()
            if event is None:
                break
            yield event

        final_state = await task
        summary = _finish(db, run_row, ctx, bus, trace, started, final_state,
                          chosen_runtime, run_mode)
        yield bus.emit(
            "run_end", "close",
            status="stopped" if final_state.get("halted") else "ok",
            detail=(final_state.get("halt_reason") or
                    f"{(final_state.get('final') or {}).get('decision', 'Recorded')} — "
                    f"{summary['tool_calls']} tool calls, "
                    f"{summary['total_tokens']:,} tokens, "
                    f"EUR {summary['cost_eur']:.4f}."),
            data={"summary": summary, "final": final_state.get("final") or {},
                  "guard": final_state.get("guard") or {},
                  "routing": final_state.get("routing") or {},
                  "agent_outputs": final_state.get("outputs") or {},
                  "trace": trace.flush()},
        )
    except Exception as exc:  # noqa: BLE001 — a failed run must still leave a trace
        task.cancel()
        summary = _finish(db, run_row, ctx, bus, trace, started, {}, chosen_runtime,
                          run_mode, status="failed")
        yield bus.emit("run_end", "close", status="failed",
                       detail=_explain_failure(exc),
                       data={"error": str(exc)[:600], "remedy": _remedy_for(exc),
                             "summary": summary})
    finally:
        reset_run_context(tokens[0])
        _BUS.reset(tokens[1])
        _CTX.reset(tokens[2])
        _TRACE.reset(tokens[3])


def _trace_destination() -> str:
    from app.services.tracing import langsmith_enabled

    return "langsmith" if langsmith_enabled() else "in-process"


def _finish(db, run_row, ctx, bus, trace, started, final_state, runtime, mode,
            status: str | None = None) -> dict[str, Any]:
    halted = bool(final_state.get("halted")) if final_state else False
    total_tokens = ctx.prompt_tokens + ctx.completion_tokens

    consumption = llm_usage.run_cost(db, ctx.run_id)
    cost = consumption["cost_eur"]

    run_row.status = status or ("stopped" if halted else "completed")
    run_row.outcome = (final_state.get("final") or {}).get("decision") if final_state else None
    run_row.ended_at = dt.datetime.now(dt.timezone.utc)
    run_row.duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    run_row.steps_completed = ctx.steps
    run_row.tool_calls = len(ctx.tool_calls)
    run_row.prompt_tokens = ctx.prompt_tokens
    run_row.completion_tokens = ctx.completion_tokens
    run_row.cost_eur = cost
    run_row.budget_stops = ctx.budget_stops
    run_row.trace = bus.trail
    db.commit()

    return {
        "run_id": ctx.run_id,
        "status": run_row.status,
        "outcome": run_row.outcome,
        "duration_ms": run_row.duration_ms,
        "steps": ctx.steps,
        "tool_calls": len(ctx.tool_calls),
        "prompt_tokens": ctx.prompt_tokens,
        "completion_tokens": ctx.completion_tokens,
        "total_tokens": total_tokens,
        "cost_eur": cost,
        "cost_basis": "metered" if runtime != "deterministic" else "modelled",
        "runtime": runtime,
        "mode": mode,
        "orchestrator": "langgraph",
        "model_mode": runtime,
        "model_calls": consumption["calls"],
        "models_used": consumption["by_model"],
        "throttle_wait_ms": consumption["throttle_wait_ms"],
        "security_events": len(ctx.security_events),
        "budget_stops": ctx.budget_stops,
        "trace_id": trace.trace_id,
        "trace_destination": _trace_destination(),
        "span_count": len(trace.spans),
    }
