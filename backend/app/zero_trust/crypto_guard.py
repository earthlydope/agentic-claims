"""Pillar 3 — Cryptographic Identity & Tamper-Evident Ledger.

Every important action can be proved, and any silent change is visible.

Each sensitive action is canonicalised and signed. In this build the signature is
HMAC-SHA256 so the demo is self-contained; the signer is written against a provider
interface so swapping in Cloud KMS asymmetric signing through workload identity is a
configuration change, not a rewrite. The private key never enters the agent container
either way — the agent only ever receives a signature.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import (
    CLOUD_KMS_KEY_NAME,
    TENANT,
    THRESHOLDS,
    USE_CLOUD_KMS,
    ZERO_TRUST_SECRET_KEY,
)

GENESIS_HASH = "0" * 64
SIGNER_VERSION = "action-signer-2.0.0"


def canonical_json(data: Any) -> str:
    """Deterministic, sorted JSON so the same payload always hashes the same."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(data: Any) -> str:
    if isinstance(data, bytes):
        raw = data
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = canonical_json(data).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------
# Signing providers
# --------------------------------------------------------------------------
class SigningProvider(Protocol):
    name: str

    def sign(self, signing_string: str) -> str: ...

    def verify(self, signing_string: str, signature: str) -> bool: ...


class HmacSigningProvider:
    """Self-contained provider used for the demo and for local regression tests."""

    name = "hmac-sha256-local"

    def __init__(self, secret: str | None = None) -> None:
        self._secret = (secret or ZERO_TRUST_SECRET_KEY).encode("utf-8")

    def sign(self, signing_string: str) -> str:
        return hmac.new(self._secret, signing_string.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, signing_string: str, signature: str) -> bool:
        # Constant-time comparison: a timing side channel would leak the signature.
        return hmac.compare_digest(self.sign(signing_string), signature)


class CloudKmsSigningProvider:
    """Cloud KMS asymmetric signing through workload identity.

    Selected automatically when CLOUD_KMS_KEY_NAME is configured. The key never leaves
    KMS; this process only ever holds the resulting signature.
    """

    name = "cloud-kms-asymmetric"

    def __init__(self, key_name: str) -> None:
        self.key_name = key_name
        self._client = None

    def _kms(self):  # pragma: no cover — requires GCP credentials
        if self._client is None:
            from google.cloud import kms  # imported lazily so the demo needs no GCP

            self._client = kms.KeyManagementServiceClient()
        return self._client

    def sign(self, signing_string: str) -> str:  # pragma: no cover
        digest = hashlib.sha256(signing_string.encode("utf-8")).digest()
        response = self._kms().asymmetric_sign(
            request={"name": self.key_name, "digest": {"sha256": digest}}
        )
        return response.signature.hex()

    def verify(self, signing_string: str, signature: str) -> bool:  # pragma: no cover
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        pub = self._kms().get_public_key(request={"name": self.key_name})
        key = serialization.load_pem_public_key(pub.pem.encode("utf-8"))
        try:
            key.verify(
                bytes.fromhex(signature),
                signing_string.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False


def get_signing_provider() -> SigningProvider:
    if USE_CLOUD_KMS and CLOUD_KMS_KEY_NAME:
        return CloudKmsSigningProvider(CLOUD_KMS_KEY_NAME)
    return HmacSigningProvider()


# --------------------------------------------------------------------------
# The signed envelope
# --------------------------------------------------------------------------
@dataclass
class ActionEnvelope:
    """Every field the architecture requires a signed action to carry."""

    claim_id: str
    run_id: str
    step_id: str
    agent_id: str
    service_identity: str
    user_id: str
    tenant: str
    action: str
    policy_version: str
    approval_ref: str | None
    nonce: int
    timestamp: str
    payload_hash: str
    prev_hash: str
    chain_hash: str
    signature: str
    signer: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "agent_id": self.agent_id,
            "service_identity": self.service_identity,
            "user_id": self.user_id,
            "tenant": self.tenant,
            "action": self.action,
            "policy_version": self.policy_version,
            "approval_ref": self.approval_ref,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "chain_hash": self.chain_hash,
            "signature": self.signature,
            "signer": self.signer,
            "payload": self.payload,
        }


def _signing_string(env: dict[str, Any]) -> str:
    """The exact bytes that are signed. Order is fixed and every field is included, so
    altering any one of them invalidates the signature."""
    return ":".join(
        str(env[k])
        for k in (
            "nonce", "tenant", "claim_id", "run_id", "step_id", "agent_id",
            "service_identity", "user_id", "action", "policy_version",
            "approval_ref", "payload_hash", "timestamp",
        )
    )


def sign_action(
    *,
    payload: dict[str, Any],
    nonce: int,
    claim_id: str,
    run_id: str,
    step_id: str,
    agent_id: str,
    action: str,
    user_id: str = "system",
    service_identity: str = "claims-agent-runtime@allianz-at.iam",
    approval_ref: str | None = None,
    prev_hash: str | None = None,
    policy_version: str | None = None,
    provider: SigningProvider | None = None,
) -> ActionEnvelope:
    """Canonicalise, hash, sign, then link to the previous entry with a chain hash."""
    provider = provider or get_signing_provider()
    payload_hash = compute_hash(payload)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    prev = prev_hash or GENESIS_HASH

    base = {
        "nonce": nonce,
        "tenant": TENANT,
        "claim_id": claim_id,
        "run_id": run_id,
        "step_id": step_id,
        "agent_id": agent_id,
        "service_identity": service_identity,
        "user_id": user_id,
        "action": action,
        "policy_version": policy_version or THRESHOLDS.policy_version,
        "approval_ref": approval_ref or "",
        "payload_hash": payload_hash,
        "timestamp": timestamp,
    }

    signing_string = _signing_string(base)
    signature = provider.sign(signing_string)
    chain_hash = compute_hash(f"{prev}:{signing_string}:{signature}")

    return ActionEnvelope(
        claim_id=claim_id,
        run_id=run_id,
        step_id=step_id,
        agent_id=agent_id,
        service_identity=service_identity,
        user_id=user_id,
        tenant=TENANT,
        action=action,
        policy_version=base["policy_version"],
        approval_ref=approval_ref,
        nonce=nonce,
        timestamp=timestamp,
        payload_hash=payload_hash,
        prev_hash=prev,
        chain_hash=chain_hash,
        signature=signature,
        signer=provider.name,
        payload=payload,
    )


def verify_action(
    entry: dict[str, Any], provider: SigningProvider | None = None
) -> tuple[bool, str | None]:
    """Recompute the payload hash and the signature and compare them.

    A mismatch on either means the record was altered after it was signed.
    """
    provider = provider or get_signing_provider()

    required = (
        "nonce", "tenant", "claim_id", "run_id", "step_id", "agent_id",
        "service_identity", "user_id", "action", "policy_version",
        "payload_hash", "timestamp", "signature", "payload",
    )
    for key in required:
        if key not in entry:
            return False, f"Missing required cryptographic field: {key}"

    expected_payload_hash = compute_hash(entry["payload"])
    if expected_payload_hash != entry["payload_hash"]:
        return False, (
            "Payload hash mismatch — the payload was altered after signing "
            f"(expected {expected_payload_hash[:16]}…, stored {str(entry['payload_hash'])[:16]}…)."
        )

    base = {k: entry.get(k) for k in (
        "nonce", "tenant", "claim_id", "run_id", "step_id", "agent_id",
        "service_identity", "user_id", "action", "policy_version",
        "payload_hash", "timestamp",
    )}
    base["approval_ref"] = entry.get("approval_ref") or ""

    if not provider.verify(_signing_string(base), str(entry["signature"])):
        return False, "Signature verification failed — invalid signature or tampered envelope."

    return True, None


# --------------------------------------------------------------------------
# Ledger verification
# --------------------------------------------------------------------------
class LedgerAuditor:
    """Walks the chain and reconciles it against live database rows."""

    @staticmethod
    def verify_chain(
        entries: list[dict[str, Any]], provider: SigningProvider | None = None
    ) -> dict[str, Any]:
        """Three checks per entry: nonce order, signature validity, chain continuity."""
        provider = provider or get_signing_provider()
        if not entries:
            return {"valid": True, "count": 0, "errors": [], "checked": []}

        ordered = sorted(entries, key=lambda e: int(e.get("nonce") or 0))
        errors: list[dict[str, Any]] = []
        checked: list[dict[str, Any]] = []
        last_nonce = 0
        last_chain = GENESIS_HASH

        for idx, entry in enumerate(ordered):
            nonce = int(entry.get("nonce") or 0)
            row: dict[str, Any] = {
                "nonce": nonce,
                "claim_id": entry.get("claim_id"),
                "action": entry.get("action"),
                "agent_id": entry.get("agent_id"),
                "nonce_ok": True,
                "signature_ok": True,
                "chain_ok": True,
            }

            if nonce <= last_nonce:
                row["nonce_ok"] = False
                errors.append({
                    "index": idx, "nonce": nonce,
                    "error": (
                        f"Nonce out of sequence — replay or gap. Previous {last_nonce}, "
                        f"current {nonce}."
                    ),
                })

            sig_ok, sig_err = verify_action(entry, provider)
            if not sig_ok:
                row["signature_ok"] = False
                errors.append({"index": idx, "nonce": nonce, "error": sig_err})

            prev = entry.get("prev_hash") or GENESIS_HASH
            if idx > 0 and prev != last_chain:
                row["chain_ok"] = False
                errors.append({
                    "index": idx, "nonce": nonce,
                    "error": (
                        f"Broken chain — expected prev_hash {last_chain[:16]}…, "
                        f"found {str(prev)[:16]}…"
                    ),
                })

            checked.append(row)
            last_nonce = nonce
            last_chain = str(entry.get("chain_hash") or "")

        return {
            "valid": not errors,
            "count": len(ordered),
            "errors": errors,
            "checked": checked,
            "signer": provider.name,
        }

    @staticmethod
    def audit_database(
        db_rows: list[dict[str, Any]],
        ledger_entries: list[dict[str, Any]],
        watched_fields: tuple[str, ...] = (
            "decision", "settlement_amount_eur", "severity", "status",
        ),
    ) -> dict[str, Any]:
        """Compare live rows against the latest signed entry for each claim.

        Three buckets: verified, tampered, and untracked — a row that exists with no
        signed entry at all.
        """
        latest: dict[str, dict[str, Any]] = {}
        for entry in sorted(ledger_entries, key=lambda e: int(e.get("nonce") or 0)):
            claim_id = entry.get("claim_id")
            payload = entry.get("payload") or {}
            if claim_id and any(f in payload for f in watched_fields):
                latest[str(claim_id)] = entry

        verified, tampered, untracked = [], [], []

        for row in db_rows:
            claim_id = str(row.get("claim_id") or row.get("reference") or "")
            entry = latest.get(claim_id)

            if entry is None:
                untracked.append({
                    "claim_id": claim_id,
                    "reason": (
                        "Database record exists with no corresponding signed ledger entry."
                    ),
                })
                continue

            signed = entry.get("payload") or {}
            discrepancies = []
            for f in watched_fields:
                if f not in signed or f not in row:
                    continue
                sv, dv = signed[f], row[f]
                if isinstance(sv, (int, float)) and isinstance(dv, (int, float)):
                    if abs(float(sv) - float(dv)) > 0.001:
                        discrepancies.append({
                            "field": f, "signed": sv, "database": dv,
                        })
                elif str(sv).strip() != str(dv).strip():
                    discrepancies.append({"field": f, "signed": sv, "database": dv})

            if discrepancies:
                tampered.append({
                    "claim_id": claim_id,
                    "discrepancies": discrepancies,
                    "signed_nonce": entry.get("nonce"),
                    "signed_at": entry.get("timestamp"),
                    "signed_by": entry.get("agent_id"),
                    "payload_hash": entry.get("payload_hash"),
                })
            else:
                verified.append({
                    "claim_id": claim_id,
                    "nonce": entry.get("nonce"),
                    "status": "VERIFIED_AUTHENTIC",
                })

        return {
            "healthy": not tampered and not untracked,
            "verified_count": len(verified),
            "tampered_count": len(tampered),
            "untracked_count": len(untracked),
            "verified": verified,
            "tampered": tampered,
            "untracked": untracked,
        }
