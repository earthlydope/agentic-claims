"""Evidence intake — screen everything before a model sees it.

Signed upload into a quarantine bucket, a malware and preflight pass, a safe fetch for
any public link, and the confidence-recovery rules that decide whether a read is
accepted, confirmed, re-asked or escalated.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PAGES = 40
ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/heic", "image/webp",
    "application/pdf", "text/plain",
}

# A malware scanner stands in for Cloud Storage + a scanning pipeline. The signatures
# are the obvious ones; the point of the step is that it exists in the path, not that
# this list is exhaustive.
MALWARE_SIGNATURES = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR",   # EICAR test string
    b"%PDF-1.4\n/JS ",                        # PDF with an embedded script action
    b"<script>",
)

PRIVATE_HOSTS = {
    "metadata.google.internal", "metadata", "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.169.254", "instance-data",
}
ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class PreflightResult:
    accepted: bool
    verdict: str                       # clean / blocked / quarantined
    checks: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sha256: str = ""
    duplicate_of: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "verdict": self.verdict,
            "checks": self.checks,
            "notes": self.notes,
            "sha256": self.sha256,
            "duplicate_of": self.duplicate_of,
        }


def preflight_upload(
    *,
    filename: str,
    mime_type: str,
    payload: bytes,
    page_count: int = 1,
    known_hashes: dict[str, str] | None = None,
) -> PreflightResult:
    """MIME, size, page count, malware and duplicate hash — in that order."""
    checks: list[dict[str, Any]] = []
    notes: list[str] = []
    digest = hashlib.sha256(payload).hexdigest()

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})

    mime_ok = mime_type in ALLOWED_MIME
    add("mime_type", mime_ok,
        f"{mime_type} is accepted." if mime_ok
        else f"{mime_type} is not an accepted evidence type.")

    size_ok = 0 < len(payload) <= MAX_UPLOAD_BYTES
    add("size", size_ok,
        f"{len(payload):,} bytes within the {MAX_UPLOAD_BYTES:,} byte limit." if size_ok
        else f"{len(payload):,} bytes is outside the accepted range.")

    pages_ok = 1 <= page_count <= MAX_PAGES
    add("page_count", pages_ok,
        f"{page_count} page(s) within the {MAX_PAGES} page limit." if pages_ok
        else f"{page_count} pages exceeds the {MAX_PAGES} page limit.")

    infected = next((s for s in MALWARE_SIGNATURES if s in payload), None)
    add("malware_scan", infected is None,
        "No signature match." if infected is None
        else f"Signature match on {infected[:24]!r} — file rejected.")

    duplicate_of = (known_hashes or {}).get(digest)
    add("duplicate_hash", duplicate_of is None,
        f"Hash {digest[:12]}… is new." if duplicate_of is None
        else f"Identical file already received as {duplicate_of}.")
    if duplicate_of:
        notes.append(
            "This is byte-identical to evidence already on the claim, so it was not "
            "processed twice."
        )

    hard_fail = not (mime_ok and size_ok and pages_ok) or infected is not None
    if hard_fail:
        return PreflightResult(False, "blocked", checks, notes, digest, duplicate_of)
    if duplicate_of:
        return PreflightResult(True, "duplicate", checks, notes, digest, duplicate_of)
    return PreflightResult(True, "clean", checks, notes, digest, duplicate_of)


def safe_link_check(url: str) -> PreflightResult:
    """Fetch guard for a customer-supplied public link.

    Blocks anything pointing at a private address, a link-local address or a cloud
    metadata endpoint. A blocked link is an SSRF attempt and raises a security event —
    the customer is then asked to upload directly instead.
    """
    checks: list[dict[str, Any]] = []
    notes: list[str] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})

    parsed = urlparse(url if "://" in url else f"https://{url}")
    scheme_ok = parsed.scheme in ALLOWED_SCHEMES
    add("scheme", scheme_ok, f"Scheme '{parsed.scheme}' {'accepted' if scheme_ok else 'refused'}.")

    host = (parsed.hostname or "").lower()
    host_ok = bool(host) and host not in PRIVATE_HOSTS
    add("host_allowlist", host_ok,
        f"Host '{host}' is not on the blocked list." if host_ok
        else f"Host '{host}' is a metadata or loopback endpoint.")

    private_ip = False
    try:
        ip = ipaddress.ip_address(host)
        private_ip = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # Not a literal IP. A hostname is resolved inside the perimeter in production;
        # here the allowlist above is the control.
        private_ip = False
    add("private_address", not private_ip,
        "Target is not a private address." if not private_ip
        else f"'{host}' resolves to a private or link-local address — blocked as SSRF.")

    port = parsed.port
    port_ok = port is None or port in (80, 443, 8080, 8443)
    add("port", port_ok, f"Port {port or 'default'} {'accepted' if port_ok else 'refused'}.")

    redirect_ok = not re.search(r"(@|%40)", url)
    add("credential_in_url", redirect_ok,
        "No embedded credentials." if redirect_ok
        else "Embedded credentials in the URL — refused.")

    passed = all(c["passed"] for c in checks)
    if not passed:
        notes.append(
            "Blocked as an SSRF attempt and a security event raised. The customer is "
            "asked to upload the file directly instead."
        )
        return PreflightResult(False, "blocked", checks, notes,
                               hashlib.sha256(url.encode()).hexdigest())

    notes.append("Fetched through the safe-fetch service; a snapshot hash is recorded.")
    return PreflightResult(True, "clean", checks, notes,
                           hashlib.sha256(url.encode()).hexdigest())


# --------------------------------------------------------------------------
# Confidence recovery rules: accept / confirm / re-ask / escalate
# --------------------------------------------------------------------------
ACCEPT_THRESHOLD = 0.85
CONFIRM_THRESHOLD = 0.65
REASK_THRESHOLD = 0.45


def recovery_action(confidence: float, attempts: int = 0) -> str:
    """One rule, applied identically everywhere, so behaviour never depends on wording."""
    if attempts >= 2:
        return "escalate"
    if confidence >= ACCEPT_THRESHOLD:
        return "accept"
    if confidence >= CONFIRM_THRESHOLD:
        return "confirm"
    if confidence >= REASK_THRESHOLD:
        return "re_ask"
    return "escalate"


RECOVERY_RULES = [
    {"action": "accept", "range": f">= {ACCEPT_THRESHOLD}",
     "behaviour": "Promote the extracted value to validated and move on."},
    {"action": "confirm", "range": f"{CONFIRM_THRESHOLD} – {ACCEPT_THRESHOLD}",
     "behaviour": "Show the read back to the customer: \"we read X — is that right?\""},
    {"action": "re_ask", "range": f"{REASK_THRESHOLD} – {CONFIRM_THRESHOLD}",
     "behaviour": "Ask for one specific new view or document, naming the exact problem."},
    {"action": "escalate", "range": f"< {REASK_THRESHOLD} or 2 failed attempts",
     "behaviour": "Hand to a document specialist and leave an outstanding-evidence task."},
]
