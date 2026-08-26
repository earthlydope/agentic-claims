"""The zero-trust control plane, wired into the ADK runtime as a plugin.

One object screens prompts, authorises tool calls, treats every tool response as
untrusted data, screens what the model produced, and keeps the budget honest. It is
installed once on the Runner, so every agent inherits the controls the day it is created
and no individual agent has to remember to apply any of them.

Callback → control mapping:
    on_user_message_callback   Pillar 1 — inbound prompt firewall
    before_agent_callback      harness  — step accounting and circuit breakers
    before_tool_callback       Pillar 2 — tool scope, risk class, per-call provenance
    after_tool_callback        Pillar 1 — retrieved-content isolation
    after_model_callback       Pillar 1 — outbound screening, token accounting
    after_agent_callback       harness  — capture the agent's structured output
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from google.adk.plugins import BasePlugin
from google.genai import types

from app.agents.harness import BudgetExceeded, check_budgets, maybe_run_context
from app.agents.tools import TOOL_NAMES_BY_AGENT, TOOL_RISK_CLASS
from app.zero_trust.semantic_gateway import PolicyAction, PromptFirewall, Surface

# Agent display name → registry key, so tool scope can be resolved from the ADK agent.
AGENT_NAME_TO_KEY: dict[str, str] = {
    "IntakeOrchestratorAgent": "intake_orchestrator",
    "DocumentUnderstandingAgent": "document_understanding",
    "CoverageAgent": "coverage",
    "DamageAssessmentAgent": "damage_assessment",
    "RepairEstimateAgent": "repair_estimate",
    "FraudRiskAgent": "fraud_risk",
    "DecisionAgent": "decision",
    "HitlCoordinatorAgent": "hitl_coordinator",
    "CustomerCommunicationAgent": "customer_communication",
}

# String fields that carry content originating outside the platform. These are the ones
# that get screened on the way back from a tool.
UNTRUSTED_KEYS = {
    "ocr_text", "fnol_text", "quote", "detail", "note", "notes", "body",
    "reason_detail", "extracted_value", "description", "persona_note",
}

MAX_SCREENED_CHARS = 20_000

# Context budget. A tool result is data, and it is also cost: every turn resends the
# whole exchange, so a verbose result is paid for repeatedly. These caps trim what the
# *model* receives; the claim record keeps the full evidence either way, and the console
# shows exactly what the model was given.
MAX_STRING_CHARS = 600
MAX_LIST_ITEMS = 12
DROP_FROM_MODEL_CONTEXT = {
    # Isolation telemetry is proof for an auditor, not input for a decision.
    "telemetry",
    # Retrieval scoring detail is useful in the console, not to the model.
    "matched_terms",
    "retrieval_score",
    # The German and English variants of a clause are both present; one is enough.
    "text_de",
    # Raw persona prose and internal notes are never decision inputs.
    "persona_note",
}


class ZeroTrustPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="zero_trust_control_plane")
        self.events: list[dict[str, Any]] = []

    # -- helpers ---------------------------------------------------------
    def _record(
        self,
        kind: str,
        *,
        severity: str = "medium",
        surface: str = "",
        rule_ids: list[str] | None = None,
        detail: str = "",
        payload: dict[str, Any] | None = None,
        agent: str = "",
    ) -> dict[str, Any]:
        ctx = maybe_run_context()
        event = {
            "event_id": f"SEC-{secrets.token_hex(4).upper()}",
            "kind": kind,
            "severity": severity,
            "surface": surface,
            "rule_ids": rule_ids or [],
            "detail": detail,
            "payload": payload or {},
            "agent": agent,
            "claim_reference": ctx.claim_reference if ctx else None,
            "run_id": ctx.run_id if ctx else None,
        }
        self.events.append(event)
        if ctx is not None:
            ctx.security_events.append(event)
        return event

    # -- Pillar 1: inbound ----------------------------------------------
    async def on_user_message_callback(self, *, invocation_context, user_message):
        text = " ".join(p.text for p in (user_message.parts or []) if p.text)
        result = PromptFirewall.inspect(text, Surface.USER_MESSAGE)

        if result.action is PolicyAction.BLOCK:
            self._record(
                "injection_blocked",
                severity="high",
                surface=result.surface,
                rule_ids=[v.rule_id for v in result.violations],
                detail=result.reasoning,
                payload={"risk_score": result.risk_score, "excerpt": text[:280]},
            )
            # Returning content short-circuits the run: not one token is generated.
            return types.Content(
                role="model",
                parts=[types.Part(text=json.dumps({
                    "blocked_by": "semantic_gateway.prompt_firewall",
                    "rule_pack_version": result.rule_pack_version,
                    "rules_fired": [v.rule_id for v in result.violations],
                    "risk_score": result.risk_score,
                    "message": (
                        "This request was stopped before it reached a model. Prompt "
                        "instructions are not a security boundary here."
                    ),
                }))],
            )

        if result.violations:
            self._record(
                "injection_quarantined",
                severity="medium",
                surface=result.surface,
                rule_ids=[v.rule_id for v in result.violations],
                detail=result.reasoning,
            )
        return None

    # -- harness: step accounting --------------------------------------
    async def before_agent_callback(self, *, agent, callback_context):
        ctx = maybe_run_context()
        if ctx is None:
            return None
        ctx.steps += 1
        try:
            check_budgets(ctx)
        except BudgetExceeded as exc:
            self._record(
                "budget_safe_stop",
                severity="medium",
                detail=str(exc),
                agent=agent.name,
            )
            return types.Content(
                role="model",
                parts=[types.Part(text=json.dumps({
                    "safe_stop": True, "reason": str(exc),
                    "note": "Trace preserved; no external action was repeated.",
                }))],
            )
        return None

    # -- Pillar 2: tool authorisation ----------------------------------
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        ctx = maybe_run_context()
        agent_name = getattr(tool_context, "agent_name", "") or ""
        key = AGENT_NAME_TO_KEY.get(agent_name)
        allowed = TOOL_NAMES_BY_AGENT.get(key or "", set())

        # A tool outside the agent's declared scope is refused here, at the boundary —
        # not left to the agent's instructions to avoid.
        if key and tool.name not in allowed:
            self._record(
                "tool_scope_violation",
                severity="high",
                rule_ids=["ZT-SCOPE-001"],
                detail=(
                    f"{agent_name} attempted {tool.name}, which is outside its declared "
                    f"tool scope {sorted(allowed)}."
                ),
                agent=agent_name,
            )
            return {
                "error": "tool_out_of_scope",
                "tool": tool.name,
                "agent": agent_name,
                "allowed_tools": sorted(allowed),
                "message": (
                    "Refused by the zero-trust control plane: this agent identity is not "
                    "authorised for this capability."
                ),
            }

        if ctx is not None:
            # Every tool call carries claim_id, run_id, agent_id, tenant, purpose,
            # risk class and an idempotency key.
            ctx.tool_calls.append({
                "tool": tool.name,
                "agent": agent_name,
                "agent_key": key,
                "risk_class": TOOL_RISK_CLASS.get(tool.name, "unclassified"),
                "claim_id": ctx.claim_reference,
                "run_id": ctx.run_id,
                "tenant": ctx.tenant,
                "args": {k: _short(v) for k, v in (tool_args or {}).items()},
                "idempotency_key": f"{ctx.run_id}:{agent_name}:{tool.name}:{len(ctx.tool_calls)}",
            })
            try:
                check_budgets(ctx)
            except BudgetExceeded as exc:
                self._record("budget_safe_stop", detail=str(exc), agent=agent_name)
                return {"error": "budget_exceeded", "message": str(exc)}
        return None

    # -- Pillar 1: retrieved-content isolation -------------------------
    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        """Tool output is data, never an instruction.

        Anything a tool hands back that originated outside the platform — OCR text,
        customer prose, adjuster notes — is screened here. Smuggled instructions are
        stripped, the source is marked, and a security event is raised. The claim keeps
        moving on the inert remainder.
        """
        if not isinstance(result, dict):
            return None

        findings: list[dict[str, Any]] = []
        cleaned = _screen_tree(result, findings)

        trimmed: list[str] = []
        cleaned = _compact_for_model(cleaned, trimmed)

        if trimmed:
            cleaned.setdefault("_context_budget", {})
            cleaned["_context_budget"] = {
                "trimmed": sorted(set(trimmed))[:20],
                "note": (
                    "Trimmed before entering the model context. The full value is kept on "
                    "the claim and in the audit trail."
                ),
            }

        if findings:
            agent_name = getattr(tool_context, "agent_name", "") or ""
            self._record(
                "retrieved_content_sanitised",
                severity="high",
                surface=Surface.RETRIEVED_CONTENT.value,
                rule_ids=sorted({r for f in findings for r in f["rule_ids"]}),
                detail=(
                    f"{len(findings)} untrusted field(s) returned by {tool.name} carried "
                    "instruction-shaped content. Stripped before the model saw it."
                ),
                payload={"fields": [f["path"] for f in findings]},
                agent=agent_name,
            )
            cleaned["_zero_trust"] = {
                "sanitised": True,
                "findings": findings,
                "note": (
                    "Retrieved content was treated as data. Instruction-shaped markup was "
                    "removed before this result entered the model context."
                ),
            }
            return cleaned
        return cleaned if trimmed else None

    # -- Pillar 1: outbound screening + token accounting ---------------
    async def after_model_callback(self, *, callback_context, llm_response):
        ctx = maybe_run_context()
        if ctx is not None and llm_response.usage_metadata is not None:
            ctx.prompt_tokens += llm_response.usage_metadata.prompt_token_count or 0
            ctx.completion_tokens += llm_response.usage_metadata.candidates_token_count or 0

        content = llm_response.content
        if content is None or not content.parts:
            return None

        text = " ".join(p.text for p in content.parts if p.text)
        if not text:
            return None

        result = PromptFirewall.inspect(text[:MAX_SCREENED_CHARS], Surface.TOOL_RESPONSE)
        if result.action is PolicyAction.BLOCK:
            agent_name = getattr(callback_context, "agent_name", "") or ""
            self._record(
                "outbound_content_blocked",
                severity="high",
                surface="model_output",
                rule_ids=[v.rule_id for v in result.violations],
                detail=(
                    "Model output reproduced instruction-shaped content and was withheld."
                ),
                agent=agent_name,
            )
        return None

    # -- harness: capture structured output ----------------------------
    async def after_agent_callback(self, *, agent, callback_context):
        ctx = maybe_run_context()
        if ctx is None:
            return None
        key = AGENT_NAME_TO_KEY.get(agent.name)
        if not key:
            return None
        raw = (callback_context.state or {}).get(f"{key}_output")
        if isinstance(raw, str):
            try:
                ctx.agent_outputs[key] = json.loads(raw)
            except json.JSONDecodeError:
                ctx.agent_outputs[key] = {"raw": raw}
        return None


# --------------------------------------------------------------------------
def _compact_for_model(node: Any, trimmed: list[str], path: str = "") -> Any:
    """Trim a tool result down to what a decision actually needs.

    Nothing load-bearing is removed: clause quotes, amounts, statuses and confidences all
    survive. What goes is bulk — long free text, repeated language variants, and telemetry
    that belongs in the audit trail rather than in a prompt. Every turn resends the whole
    exchange, so a verbose result is paid for repeatedly in both latency and cost.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            child = f"{path}.{k}" if path else str(k)
            if k in DROP_FROM_MODEL_CONTEXT:
                trimmed.append(child)
                continue
            out[k] = _compact_for_model(v, trimmed, child)
        return out

    if isinstance(node, list):
        if len(node) > MAX_LIST_ITEMS:
            trimmed.append(f"{path}[{MAX_LIST_ITEMS}:{len(node)}]")
            node = node[:MAX_LIST_ITEMS]
        return [_compact_for_model(v, trimmed, f"{path}[{i}]") for i, v in enumerate(node)]

    if isinstance(node, str) and len(node) > MAX_STRING_CHARS:
        trimmed.append(path)
        return node[:MAX_STRING_CHARS] + " […truncated]"

    return node


def _screen_tree(node: Any, findings: list[dict[str, Any]], path: str = "") -> Any:
    """Walk a tool result and screen every untrusted string field it contains."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            child = f"{path}.{k}" if path else str(k)
            if isinstance(v, str) and k in UNTRUSTED_KEYS:
                res = PromptFirewall.inspect(v[:MAX_SCREENED_CHARS], Surface.RETRIEVED_CONTENT)
                if res.violations:
                    findings.append({
                        "path": child,
                        "rule_ids": [x.rule_id for x in res.violations],
                        "attack_classes": [x.attack_class for x in res.violations],
                        "risk_score": res.risk_score,
                        "removed": [x.matched for x in res.violations],
                    })
                    out[k] = res.sanitised_text or ""
                else:
                    out[k] = v
            else:
                out[k] = _screen_tree(v, findings, child)
        return out
    if isinstance(node, list):
        return [_screen_tree(v, findings, f"{path}[{i}]") for i, v in enumerate(node)]
    return node


def _short(value: Any, limit: int = 160) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value
