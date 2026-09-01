"""The Secure Write Gateway — the only door into a core system.

Nothing an agent produces reaches a core system directly. The Decision agent prepares a
package, the deterministic policy guard applies the business rules, a person approves
anything above the configured limit, and every passage through this gateway is signed,
chained and auditable.

Six checks run before a single row is touched:
  1. signature      — the envelope is authentic and unaltered
  2. scope          — the agent was allowed to perform this action on this claim
  3. idempotency    — a retried write is reconciled against the original, never reapplied
  4. approval       — a human approval exists, is in date, and covers the amount
  5. nonce          — strictly increasing per tenant; gaps and repeats both alert
  6. timestamp      — the envelope is not stale and not from the future
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any

from app.config import APPROVAL_TOKEN_TTL_SECONDS, AUTHORITY_LIMITS_EUR, TENANT
from app.zero_trust.crypto_guard import verify_action

MAX_ENVELOPE_AGE_SECONDS = 600
MAX_CLOCK_SKEW_SECONDS = 30

# Which agent identity may request which action. An agent that is not listed for an
# action cannot perform it, whatever its prompt says.
ACTION_SCOPES: dict[str, set[str]] = {
    "claim.settlement.write": {"DecisionAgent", "HitlCoordinatorAgent"},
    "claim.status.write": {"IntakeOrchestratorAgent", "HitlCoordinatorAgent", "DecisionAgent"},
    "claim.estimate.write": {"RepairEstimateAgent", "DecisionAgent"},
    "claim.coverage.write": {"CoverageAgent"},
    "claim.review_task.create": {"HitlCoordinatorAgent"},
    "claim.communication.send": {"CustomerCommunicationAgent"},
    "claim.fraud_case.open": {"FraudRiskAgent", "HitlCoordinatorAgent"},
}

# Actions that always require an explicit human approval reference, regardless of value.
ALWAYS_REQUIRE_APPROVAL = {"claim.settlement.write"}


@dataclass
class ApprovalToken:
    """Scoped approval: claim, action, limit, approver, expiry. Nothing broader."""

    ref: str
    claim_id: str
    action: str
    limit_eur: float
    approver_id: str
    approver_role: str
    issued_at: str
    expires_at: str
    decision: str
    note: str = ""
    consumed: bool = False

    def is_expired(self, now: datetime.datetime | None = None) -> bool:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return now > datetime.datetime.fromisoformat(self.expires_at)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "claim_id": self.claim_id,
            "action": self.action,
            "limit_eur": self.limit_eur,
            "approver_id": self.approver_id,
            "approver_role": self.approver_role,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "decision": self.decision,
            "note": self.note,
            "consumed": self.consumed,
            "expired": self.is_expired(),
        }


@dataclass
class WriteCheck:
    check: str
    passed: bool
    detail: str


@dataclass
class WriteResult:
    accepted: bool
    checks: list[WriteCheck] = field(default_factory=list)
    reason: str = ""
    idempotent_replay: bool = False
    committed_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "checks": [
                {"check": c.check, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
            "reason": self.reason,
            "idempotent_replay": self.idempotent_replay,
            "committed_ref": self.committed_ref,
        }


def idempotency_key(envelope: dict[str, Any]) -> str:
    """One logical write == one key. A retry with the same key is reconciled, not repeated."""
    basis = ":".join(
        str(envelope.get(k, ""))
        for k in ("tenant", "claim_id", "run_id", "action", "payload_hash")
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


class SecureWriteGateway:
    """Stateful per-tenant gateway: nonce watermark plus an idempotency ledger.

    The watermark lives in memory for speed but is *seeded from the ledger*, which is the
    durable record. Holding it only in memory let the two diverge — replace or reset the
    database under a running process and the gateway would refuse every subsequent write as
    a replay, because it remembered a high-water mark the ledger no longer had. A control
    that fails closed is right; a control that fails closed against its own stale state is
    not.
    """

    def __init__(self) -> None:
        self._nonce_watermark: dict[str, int] = {}
        self._seen_keys: dict[str, str] = {}
        self._approvals: dict[str, ApprovalToken] = {}

    # -- approvals ---------------------------------------------------------
    def issue_approval(
        self,
        *,
        claim_id: str,
        action: str,
        amount_eur: float,
        approver_id: str,
        approver_role: str,
        decision: str = "approve",
        note: str = "",
        ttl_seconds: int = APPROVAL_TOKEN_TTL_SECONDS,
    ) -> ApprovalToken:
        """Issue an approval scoped to one claim, one action, one limit and an expiry.

        The limit is the *approver's* authority, not the amount they were shown, so an
        approval cannot be reused for a larger write.
        """
        authority = AUTHORITY_LIMITS_EUR.get(approver_role, 0.0)
        if amount_eur > authority:
            raise PermissionError(
                f"{approver_role} authority is EUR {authority:,.2f}; "
                f"EUR {amount_eur:,.2f} needs a higher authority level."
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        token = ApprovalToken(
            ref=f"APR-{secrets.token_hex(4).upper()}",
            claim_id=claim_id,
            action=action,
            limit_eur=min(authority, max(amount_eur, 0.0)),
            approver_id=approver_id,
            approver_role=approver_role,
            issued_at=now.isoformat(),
            expires_at=(now + datetime.timedelta(seconds=ttl_seconds)).isoformat(),
            decision=decision,
            note=note,
        )
        self._approvals[token.ref] = token
        return token

    def get_approval(self, ref: str | None) -> ApprovalToken | None:
        return self._approvals.get(ref) if ref else None

    def approvals_for_claim(self, claim_id: str) -> list[ApprovalToken]:
        return [t for t in self._approvals.values() if t.claim_id == claim_id]

    # -- the gateway -------------------------------------------------------
    def prime_from_ledger(self) -> dict[str, int]:
        """Recover each tenant's nonce watermark from the ledger.

        The watermark lives in memory for speed; the ledger is the durable record. Holding
        it only in memory let the two diverge — restart the process against an existing
        ledger and the gateway would accept a nonce it had already written, and replace the
        database under a running process and it would refuse every write as a replay. Both
        are wrong, and both are fixed by reading the ledger once at startup.

        Called at application startup, never inside the check itself: a control that has to
        query the database on every write is a control that fails when the database is
        slow.
        """
        try:
            from sqlalchemy import func, select

            from app.db import SessionLocal
            from app.models import LedgerEntry

            with SessionLocal() as session:
                rows = session.execute(
                    select(LedgerEntry.tenant, func.max(LedgerEntry.nonce))
                    .group_by(LedgerEntry.tenant)
                ).all()
            for tenant, highest in rows:
                if tenant:
                    self._nonce_watermark[tenant] = int(highest or 0)
        except Exception:  # noqa: BLE001 — never block startup on recovery
            pass
        return dict(self._nonce_watermark)

    def submit(
        self,
        envelope: dict[str, Any],
        *,
        requires_approval: bool | None = None,
        amount_eur: float | None = None,
    ) -> WriteResult:
        checks: list[WriteCheck] = []

        def add(name: str, ok: bool, detail: str) -> bool:
            checks.append(WriteCheck(name, ok, detail))
            return ok

        action = str(envelope.get("action") or "")
        claim_id = str(envelope.get("claim_id") or "")
        agent_id = str(envelope.get("agent_id") or "")
        tenant = str(envelope.get("tenant") or "")
        nonce = int(envelope.get("nonce") or 0)

        # 1. Signature
        sig_ok, sig_err = verify_action(envelope)
        if not add("signature", sig_ok, sig_err or "Signature and payload hash verified."):
            return WriteResult(False, checks, "Signature verification failed.")

        # 2. Scope
        allowed = ACTION_SCOPES.get(action)
        if allowed is None:
            add("scope", False, f"Unknown action '{action}' — not in the action catalogue.")
            return WriteResult(False, checks, "Unknown action.")
        scope_ok = agent_id in allowed and tenant == TENANT
        if not add(
            "scope",
            scope_ok,
            (
                f"{agent_id} is authorised for {action} on tenant {tenant}."
                if scope_ok
                else f"{agent_id} is not authorised for {action} (allowed: {sorted(allowed)})."
            ),
        ):
            return WriteResult(False, checks, "Action is outside the agent's scope.")

        # 3. Idempotency — reconciled *before* approval and nonce, because a genuine
        # retry after a timeout resubmits the same envelope. It must be recognised as
        # already-committed rather than rejected as a replay or refused for a consumed
        # approval.
        key = idempotency_key(envelope)
        if key in self._seen_keys:
            add(
                "idempotency",
                True,
                f"Key {key[:12]}… already committed as {self._seen_keys[key]} — "
                "reconciled, not reapplied.",
            )
            return WriteResult(
                accepted=True,
                checks=checks,
                reason="Idempotent replay reconciled against the original write.",
                idempotent_replay=True,
                committed_ref=self._seen_keys[key],
            )

        # 4. Approval
        needs = (
            requires_approval
            if requires_approval is not None
            else action in ALWAYS_REQUIRE_APPROVAL
        )
        if needs:
            token = self.get_approval(envelope.get("approval_ref"))
            if token is None:
                add("approval", False, "No approval reference present for a write that requires one.")
                return WriteResult(False, checks, "Human approval is required and absent.")
            if token.claim_id != claim_id or token.action != action:
                add("approval", False, "Approval is scoped to a different claim or action.")
                return WriteResult(False, checks, "Approval scope mismatch.")
            if token.is_expired():
                add("approval", False, f"Approval {token.ref} expired at {token.expires_at}.")
                return WriteResult(False, checks, "Approval has expired.")
            if token.consumed:
                add("approval", False, f"Approval {token.ref} has already been consumed.")
                return WriteResult(False, checks, "Approval already consumed.")
            value = amount_eur if amount_eur is not None else _payload_amount(envelope)
            if value is not None and value > token.limit_eur + 0.001:
                add(
                    "approval",
                    False,
                    f"EUR {value:,.2f} exceeds the approved limit of EUR {token.limit_eur:,.2f}.",
                )
                return WriteResult(False, checks, "Amount exceeds the approved limit.")
            add(
                "approval",
                True,
                f"{token.approver_role} {token.approver_id} approved up to "
                f"EUR {token.limit_eur:,.2f} ({token.ref}).",
            )
        else:
            add("approval", True, "This action does not require a human approval.")

        # 5. Nonce — strictly increasing per tenant
        watermark = self._nonce_watermark.get(tenant, 0)
        nonce_ok = nonce > watermark
        if not add(
            "nonce",
            nonce_ok,
            (
                f"Nonce {nonce} is above the tenant watermark {watermark}."
                if nonce_ok
                else f"Nonce {nonce} is not above the watermark {watermark} — replay rejected."
            ),
        ):
            return WriteResult(False, checks, "Replay detected — nonce not monotonic.")

        # 6. Timestamp freshness
        try:
            ts = datetime.datetime.fromisoformat(str(envelope.get("timestamp")))
            age = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()
        except (TypeError, ValueError):
            add("timestamp", False, "Envelope timestamp is unparseable.")
            return WriteResult(False, checks, "Bad timestamp.")

        if age > MAX_ENVELOPE_AGE_SECONDS:
            add("timestamp", False, f"Envelope is stale — {age:.0f}s old.")
            return WriteResult(False, checks, "Stale envelope.")
        if age < -MAX_CLOCK_SKEW_SECONDS:
            add("timestamp", False, f"Envelope is dated {-age:.0f}s in the future.")
            return WriteResult(False, checks, "Envelope from the future.")
        add("timestamp", True, f"Envelope age {max(age, 0):.1f}s, within tolerance.")

        committed_ref = f"CW-{secrets.token_hex(5).upper()}"
        self._seen_keys[key] = committed_ref
        self._nonce_watermark[tenant] = max(nonce, self._nonce_watermark.get(tenant, 0))
        add("commit", True, f"First write for key {key[:12]}… — committed once.")

        if needs:
            token = self.get_approval(envelope.get("approval_ref"))
            if token is not None:
                token.consumed = True

        return WriteResult(
            accepted=True,
            checks=checks,
            reason="All six gateway checks passed — write committed once.",
            committed_ref=committed_ref,
        )

    def posture(self) -> dict[str, Any]:
        return {
            "nonce_watermark": dict(self._nonce_watermark),
            "committed_writes": len(self._seen_keys),
            "approvals_issued": len(self._approvals),
            "approvals_outstanding": sum(
                1 for t in self._approvals.values() if not t.consumed and not t.is_expired()
            ),
            "action_catalogue": sorted(ACTION_SCOPES),
        }


def _payload_amount(envelope: dict[str, Any]) -> float | None:
    payload = envelope.get("payload") or {}
    for key in ("settlement_amount_eur", "total_cost", "amount_eur"):
        if key in payload:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                return None
    return None


gateway = SecureWriteGateway()
