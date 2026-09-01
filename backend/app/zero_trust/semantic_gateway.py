"""Pillar 1 — Semantic Gateway & Policy Guard.

Nothing reaches the model unchecked, and nothing leaves it unchecked.

Inbound:  an eight-class injection rule pack screens every customer message, note,
          document and tool response before a single token is generated.
Outbound: six deterministic checks are applied to what the model produced. The rules
          live here, in versioned and unit-tested code outside the prompt, so changing
          a prompt can never change what the business allows.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import THRESHOLDS

RULE_PACK_VERSION = "allianz-at-injection-rules-1.4.0"
POLICY_GUARD_VERSION = "allianz-at-decision-policy-2.1.0"


class PolicyAction(str, enum.Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    QUARANTINE_FOR_REVIEW = "QUARANTINE_FOR_REVIEW"


class Surface(str, enum.Enum):
    """Where the screened text came from. Retrieved content and tool output are held to
    the same standard as customer input — they are data, never instructions."""

    USER_MESSAGE = "user_message"
    DOCUMENT = "document"
    TOOL_RESPONSE = "tool_response"
    RETRIEVED_CONTENT = "retrieved_content"
    ADJUSTER_NOTE = "adjuster_note"


@dataclass
class Violation:
    rule_id: str
    attack_class: str
    detail: str
    matched: str = ""


@dataclass
class InspectionResult:
    action: PolicyAction
    passed: bool
    risk_score: float
    violations: list[Violation] = field(default_factory=list)
    reasoning: str = ""
    remediated_decision: str | None = None
    rule_pack_version: str = RULE_PACK_VERSION
    surface: str = Surface.USER_MESSAGE.value
    sanitised_text: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "passed": self.passed,
            "risk_score": round(self.risk_score, 3),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "attack_class": v.attack_class,
                    "detail": v.detail,
                    "matched": v.matched,
                }
                for v in self.violations
            ],
            "reasoning": self.reasoning,
            "remediated_decision": self.remediated_decision,
            "rule_pack_version": self.rule_pack_version,
            "surface": self.surface,
        }


# --------------------------------------------------------------------------
# Inbound: the eight named attack classes
# --------------------------------------------------------------------------
class PromptFirewall:
    """Screens every inbound surface for the eight attack classes named in the
    blueprint. A block can always be traced back to a rule id and a rule-pack
    version."""

    RULES: list[tuple[str, str, re.Pattern[str], str]] = [
        (
            "ZT-INJ-001",
            "instruction_override",
            re.compile(
                r"(ignore|forget|discard|bypass)\s+(all\s+|any\s+)?"
                r"(previous|prior|above|earlier|system)\s+"
                r"(instructions?|directives?|rules?|guidelines?|prompts?)",
                re.IGNORECASE,
            ),
            "Instruction override attempt.",
        ),
        (
            "ZT-INJ-002",
            "safety_directive_bypass",
            re.compile(
                r"(disregard|override|switch\s+off|turn\s+off|skip)\s+(all\s+)?"
                r"(the\s+)?(safety|security|adjuster|policy|compliance|guard)\s*"
                r"(directives?|rules?|checks?|controls?|guard(rails?)?)?",
                re.IGNORECASE,
            ),
            "Safety-directive bypass attempt.",
        ),
        (
            "ZT-INJ-003",
            "severity_manipulation",
            re.compile(
                r"(override|change|set|mark|classify|record)\s+(the\s+)?"
                r"(severity|damage|assessment)\s+(as\s+|to\s+)['\"]?(simple|minor|trivial)['\"]?",
                re.IGNORECASE,
            ),
            "Adversarial severity manipulation.",
        ),
        (
            "ZT-INJ-004",
            "forced_approval",
            re.compile(
                r"(approve|authorise|authorize|settle|pay\s?out|refund)\s+"
                r"(this\s+|the\s+)?(claim\s+)?"
                r"(immediately|now|at\s+once|without\s+review|regardless|automatically|"
                r"no\s+questions|unconditionally)",
                re.IGNORECASE,
            ),
            "Forced claim-approval bypass.",
        ),
        (
            "ZT-INJ-005",
            "unauthorised_high_value_transaction",
            re.compile(
                r"(issue|payout|pay\s?out|transfer|send|wire|release|disburse)\s+"
                r"(a\s+|the\s+)?(refund|claim|payment|settlement|amount)?\s*"
                r"(of\s+)?[€$£]?\s?\d[\d.,]{3,}",
                re.IGNORECASE,
            ),
            "Unauthorised high-value transaction injection.",
        ),
        (
            "ZT-INJ-006",
            "credential_or_prompt_probing",
            re.compile(
                r"(print|show|dump|reveal|leak|exfiltrate|repeat|output|list)\s+"
                r"(me\s+)?(the\s+|your\s+)?"
                r"(system\s+prompt|instructions|environment|env\s+vars?|"
                r"api[_\s-]?keys?|secrets?|credentials?|tokens?|service\s+account)",
                re.IGNORECASE,
            ),
            "Credential or system-prompt exfiltration probe.",
        ),
        (
            "ZT-INJ-007",
            "code_injection",
            re.compile(
                r"(os\.environ|environ\.get|subprocess|__import__|"
                r"\beval\s*\(|\bexec\s*\(|import\s+socket|open\s*\(\s*['\"]/|"
                r"requests\.(get|post)|urllib\.request)",
                re.IGNORECASE,
            ),
            "Code injection or environment-variable extraction pattern.",
        ),
        (
            "ZT-INJ-008",
            "persona_switching",
            re.compile(
                r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be|switch\s+to)\s+"
                r"(in\s+|an?\s+|the\s+)?"
                r"(developer|maintenance|debug|unrestricted|god|admin|root|dan)\s*"
                r"(mode|user|account)?",
                re.IGNORECASE,
            ),
            "Persona switching for privilege escalation.",
        ),
    ]

    # Instruction-shaped text hidden inside a document is stripped rather than trusted.
    HIDDEN_INSTRUCTION_MARKERS = re.compile(
        r"(<!--.*?-->|\[\[.*?\]\]|\bSYSTEM\s*:|\bASSISTANT\s*:|"
        r"###\s*(instruction|system)|<\|.*?\|>)",
        re.IGNORECASE | re.DOTALL,
    )

    @classmethod
    def inspect(
        cls, text: str, surface: Surface = Surface.USER_MESSAGE
    ) -> InspectionResult:
        if not text or not text.strip():
            return InspectionResult(
                action=PolicyAction.ALLOW,
                passed=True,
                risk_score=0.0,
                reasoning="Empty input — nothing to screen.",
                surface=surface.value,
            )

        violations: list[Violation] = []
        content_surface = surface in (
            Surface.DOCUMENT,
            Surface.TOOL_RESPONSE,
            Surface.RETRIEVED_CONTENT,
        )

        # On a content surface the smuggled instruction is stripped *first*, then the
        # remaining text is screened. That is the difference between "a customer is
        # attacking us" (block) and "a file carried a payload" (strip, quarantine the
        # file, and let the inert data through so the claim keeps moving).
        sanitised = text
        if content_surface:
            hidden = cls.HIDDEN_INSTRUCTION_MARKERS.findall(text)
            if hidden:
                sanitised = cls.HIDDEN_INSTRUCTION_MARKERS.sub(
                    " [instruction stripped] ", text
                )
                violations.append(
                    Violation(
                        rule_id="ZT-INJ-009",
                        attack_class="hidden_instruction_in_content",
                        detail=(
                            "Instruction-shaped markup found inside retrieved content. "
                            "Stripped and the source quarantined — retrieved content is "
                            "data, never an instruction."
                        ),
                        matched=str(hidden[0])[:120],
                    )
                )

        screened = sanitised if content_surface else text
        for rule_id, attack_class, pattern, detail in cls.RULES:
            m = pattern.search(screened)
            if m:
                violations.append(
                    Violation(
                        rule_id=rule_id,
                        attack_class=attack_class,
                        detail=detail,
                        matched=m.group(0)[:120],
                    )
                )

        if not violations:
            return InspectionResult(
                action=PolicyAction.ALLOW,
                passed=True,
                risk_score=0.0,
                reasoning="Passed all inbound semantic security filters.",
                surface=surface.value,
                sanitised_text=text,
            )

        risk = min(1.0, 0.4 + 0.22 * len(violations))

        # Customer-supplied prose that attacks the platform is blocked outright.
        # Content that merely *contains* smuggled instructions is stripped and allowed
        # through as inert data, so the claim keeps moving.
        only_hidden = all(
            v.attack_class == "hidden_instruction_in_content" for v in violations
        )
        action = PolicyAction.QUARANTINE_FOR_REVIEW if only_hidden else PolicyAction.BLOCK

        return InspectionResult(
            action=action,
            passed=False,
            risk_score=risk,
            violations=violations,
            reasoning="Semantic gateway fired: "
            + "; ".join(f"{v.rule_id} {v.detail}" for v in violations),
            surface=surface.value,
            sanitised_text=sanitised,
        )


# --------------------------------------------------------------------------
# Outbound: the six deterministic checks
# --------------------------------------------------------------------------
@dataclass
class GuardCheck:
    check_id: str
    name: str
    passed: bool
    detail: str


@dataclass
class GuardResult:
    action: PolicyAction
    passed: bool
    checks: list[GuardCheck]
    violations: list[str]
    remediated_decision: str | None
    original_decision: str | None
    reasoning: str
    policy_guard_version: str = POLICY_GUARD_VERSION
    policy_version: str = THRESHOLDS.policy_version

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "passed": self.passed,
            "checks": [
                {
                    "check_id": c.check_id,
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
            "violations": self.violations,
            "remediated_decision": self.remediated_decision,
            "original_decision": self.original_decision,
            "reasoning": self.reasoning,
            "policy_guard_version": self.policy_guard_version,
            "policy_version": self.policy_version,
            "auto_approval_ceiling_eur": THRESHOLDS.auto_approval_ceiling_eur,
        }


class DecisionPolicyGuard:
    """Applies the business rules after the model has spoken.

    A violation never simply fails: the decision is downgraded to "Review Required",
    the original recommendation is preserved, and every violation is recorded on the
    claim so the adjuster sees exactly why it arrived.
    """

    APPROVE = "Approved"
    REVIEW = "Review Required"
    DECLINE = "Declined"
    REQUEST_INFO = "Request Information"

    @staticmethod
    def evaluate(package: dict[str, Any]) -> GuardResult:
        decision = str(package.get("decision") or "").strip()
        estimate = package.get("estimate") or {}
        coverage = package.get("coverage") or {}
        risk = package.get("risk") or {}
        evidence = package.get("evidence") or {}
        severity = str(package.get("severity") or "").lower()

        total = _f(estimate.get("total_cost"))
        labour = _f(estimate.get("total_labour"))
        parts = _f(estimate.get("total_parts"))
        tax = _f(estimate.get("total_tax"))

        checks: list[GuardCheck] = []
        violations: list[str] = []

        def add(check_id: str, name: str, ok: bool, detail: str) -> None:
            checks.append(GuardCheck(check_id, name, ok, detail))
            if not ok:
                violations.append(f"{check_id} {name}: {detail}")

        approving = decision.lower() in ("approved", "approve", "auto-approved")

        # 1. Financial ceiling
        ceiling = THRESHOLDS.auto_approval_ceiling_eur
        add(
            "PG-01",
            "Financial ceiling",
            not (approving and total > ceiling),
            (
                f"Approved amount EUR {total:,.2f} exceeds the autonomous limit of "
                f"EUR {ceiling:,.2f}."
                if approving and total > ceiling
                else f"EUR {total:,.2f} is within the autonomous limit of EUR {ceiling:,.2f}."
            ),
        )

        # 2. Severity coherence
        complex_damage = "complex" in severity or bool(package.get("structural_damage"))
        add(
            "PG-02",
            "Severity coherence",
            not (
                approving
                and complex_damage
                and not THRESHOLDS.complex_damage_auto_approve_allowed
            ),
            (
                "Complex or structural damage can never be autonomously approved."
                if approving and complex_damage
                else f"Severity '{severity or 'unspecified'}' is coherent with the decision."
            ),
        )

        # 3. Arithmetic integrity — parts plus labour (plus tax) must reconcile to the cent
        expected = round(labour + parts + tax, 2)
        arithmetic_ok = (
            total == 0.0 and expected == 0.0
        ) or abs(total - expected) <= THRESHOLDS.arithmetic_tolerance_eur
        add(
            "PG-03",
            "Arithmetic integrity",
            arithmetic_ok,
            (
                f"total_cost EUR {total:,.2f} does not reconcile to labour EUR {labour:,.2f} "
                f"+ parts EUR {parts:,.2f} + tax EUR {tax:,.2f} = EUR {expected:,.2f}."
                if not arithmetic_ok
                else f"EUR {labour:,.2f} + EUR {parts:,.2f} + EUR {tax:,.2f} = EUR {total:,.2f}."
            ),
        )

        # 4. Coverage certainty
        cov_status = str(coverage.get("status") or "unknown").lower()
        coverage_ok = not (approving and cov_status not in ("covered", "covered_with_excess"))
        add(
            "PG-04",
            "Coverage certainty",
            coverage_ok,
            (
                f"Coverage status '{cov_status}' is not certain enough to approve — "
                "routed to a coverage adjuster."
                if not coverage_ok
                else f"Coverage confirmed as '{cov_status}'."
            ),
        )

        # 5. Evidence completeness
        missing = list(evidence.get("missing") or [])
        evidence_ok = not (approving and missing)
        add(
            "PG-05",
            "Evidence completeness",
            evidence_ok,
            (
                "Required evidence is still missing: " + ", ".join(missing)
                if not evidence_ok
                else "All required evidence is present."
            ),
        )

        # 6. Citation rule — a material policy answer with no authoritative citation is refused
        citations = list(coverage.get("citations") or [])
        needs_citation = (
            THRESHOLDS.require_citation_for_policy_answers
            and cov_status != "unknown"
        )
        citation_ok = not (needs_citation and not citations)
        add(
            "PG-06",
            "Citation rule",
            citation_ok,
            (
                "A material policy answer was produced with no authoritative citation."
                if not citation_ok
                else f"{len(citations)} authoritative citation(s) attached."
            ),
        )

        # Additional guards the architecture calls out explicitly.
        if THRESHOLDS.injury_blocks_financial_automation:
            injury = bool(package.get("injury_reported"))
            # Any autonomous outcome counts, not only an approval. Where an injury is
            # reported, automated adjudication stops and the bodily-injury team takes the
            # claim — that is PROC-INJ-01, and it does not depend on what the agent
            # happened to propose.
            autonomous_outcome = decision.lower() in (
                "approved", "approve", "auto-approved", "declined", "decline",
                "rejected", "request information",
            )
            add(
                "PG-07",
                "Injury stop",
                not (injury and autonomous_outcome),
                (
                    "Injury reported — automated adjudication is suspended and the claim "
                    "is referred to the bodily-injury team."
                    if injury and autonomous_outcome
                    else "No injury reported on this claim."
                ),
            )

        # 10. Model restatement integrity.
        # The numbers the guard checks come from the tools, not from the model. Where the
        # model also restated a figure, it must agree — a model that misreports the
        # estimate or the settlement it is recommending is not a model to act on.
        restated = package.get("model_restatement") or {}
        restatement_issues: list[str] = []
        for label, claimed_key, authoritative in (
            ("estimate total", "total_cost", total),
            ("settlement", "settlement_amount_eur", _f(package.get("settlement_amount_eur"))),
        ):
            claimed = restated.get(claimed_key)
            if claimed in (None, 0.0):
                continue
            if abs(_f(claimed) - authoritative) > 0.01:
                restatement_issues.append(
                    f"the model stated a {label} of EUR {_f(claimed):,.2f} against an "
                    f"authoritative EUR {authoritative:,.2f}"
                )
        add(
            "PG-10",
            "Model restatement integrity",
            not restatement_issues,
            (
                "The model misreported a figure it was recommending: "
                + "; ".join(restatement_issues)
                + "."
                if restatement_issues
                else "Every figure the model restated matches the authoritative tool output."
            ),
        )

        # An adverse outcome is never autonomous. A decline or a reduction is a
        # materially adverse decision for a customer, and the architecture guarantees a
        # visible route to a person — so it is confirmed by one before it is issued.
        # A nil payment is adverse to the person receiving it, whatever the decision
        # string says. Closing a claim at nothing because the assessed amount did not clear
        # the excess is the right answer, but it is not an answer to issue without a person
        # having confirmed the figure the excess was tested against.
        nil_outcome = bool(package.get("below_excess"))
        adverse = (
            decision.lower() in ("declined", "decline", "rejected", "reduced") or nil_outcome
        )
        add(
            "PG-09",
            "Adverse decision review",
            not adverse,
            (
                (
                    "The claim pays nothing because the assessed amount does not exceed "
                    "the excess. That is adverse to the customer and is never issued "
                    "autonomously — a named person confirms it."
                    if nil_outcome
                    else f"A '{decision}' outcome is materially adverse to the customer "
                         "and is never issued autonomously — a named person confirms it."
                )
                if adverse
                else "The proposed outcome is not adverse to the customer."
            ),
        )

        fraud_score = _f(risk.get("score"))
        add(
            "PG-08",
            "Fraud threshold",
            not (approving and fraud_score > THRESHOLDS.max_fraud_score_for_autonomy),
            (
                f"Fraud score {fraud_score:.2f} exceeds the autonomy threshold "
                f"{THRESHOLDS.max_fraud_score_for_autonomy:.2f} — autonomous progression frozen."
                if approving and fraud_score > THRESHOLDS.max_fraud_score_for_autonomy
                else f"Fraud score {fraud_score:.2f} is within the autonomy threshold."
            ),
        )

        if violations:
            return GuardResult(
                action=PolicyAction.QUARANTINE_FOR_REVIEW,
                passed=False,
                checks=checks,
                violations=violations,
                remediated_decision=DecisionPolicyGuard.REVIEW,
                original_decision=decision,
                reasoning=(
                    f"{len(violations)} deterministic policy check(s) failed. The "
                    "recommendation is preserved and the decision is downgraded to "
                    "'Review Required'."
                ),
            )

        return GuardResult(
            action=PolicyAction.ALLOW,
            passed=True,
            checks=checks,
            violations=[],
            remediated_decision=None,
            original_decision=decision,
            reasoning="The decision package complies with every deterministic policy check.",
        )


def enforce_decision_policy(package: dict[str, Any]) -> tuple[dict[str, Any], GuardResult]:
    """Evaluate and remediate in one call. Returns the enforced package and the result."""
    result = DecisionPolicyGuard.evaluate(package)
    enforced = dict(package)

    if not result.passed and result.remediated_decision:
        enforced["original_decision"] = result.original_decision
        enforced["decision"] = result.remediated_decision
        enforced["policy_enforcement"] = {
            "remediated": True,
            "violations": result.violations,
            "reasoning": result.reasoning,
            "policy_guard_version": result.policy_guard_version,
        }
    else:
        enforced["policy_enforcement"] = {
            "remediated": False,
            "violations": [],
            "reasoning": "Compliant",
            "policy_guard_version": result.policy_guard_version,
        }

    return enforced, result


def _f(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# Outbound guard on customer communication
# --------------------------------------------------------------------------
def parse_eur_amount(raw: str) -> float | None:
    """Parse a EUR figure written in either Austrian or English convention.

    German-Austrian writes 1.442,30 and English writes 1,442.30. Whichever separator
    appears last is the decimal one; a lone separator followed by exactly two digits is
    also a decimal. Anything else is a thousands separator.
    """
    text_value = (raw or "").strip().rstrip(".,")
    if not text_value:
        return None

    last_comma = text_value.rfind(",")
    last_dot = text_value.rfind(".")

    if last_comma >= 0 and last_dot >= 0:
        decimal_at = max(last_comma, last_dot)
    elif last_comma >= 0:
        decimal_at = last_comma if len(text_value) - last_comma - 1 == 2 else -1
    elif last_dot >= 0:
        decimal_at = last_dot if len(text_value) - last_dot - 1 == 2 else -1
    else:
        decimal_at = -1

    if decimal_at >= 0:
        whole = re.sub(r"[.,]", "", text_value[:decimal_at])
        frac = re.sub(r"[^0-9]", "", text_value[decimal_at + 1 :])
        candidate = f"{whole}.{frac or '0'}"
    else:
        candidate = re.sub(r"[.,]", "", text_value)

    try:
        return round(float(candidate), 2)
    except ValueError:
        return None


INTERNAL_ARTEFACT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("rule_identifier", re.compile(r"\b(PG-\d{2}|ZT-[A-Z]+-\d{3}|SBX-\d{2})\b"),
     "An internal rule identifier appeared in customer-facing text."),
    ("guard_reasoning", re.compile(
        r"(autonomous limit|policy guard|deterministic check|severity coherence|"
        r"arithmetic integrity|auto-approval ceiling|downgraded to)", re.IGNORECASE),
     "Internal guard reasoning appeared in customer-facing text."),
    ("queue_name", re.compile(r"\b(siu|special investigation|fraud|adjuster queue|"
                              r"supervisor queue)\b", re.IGNORECASE),
     "An internal queue or investigation status appeared in customer-facing text."),
    ("system_identifier", re.compile(r"\b(run-[0-9a-f]{6,}|TSK-[0-9A-F]{6,}|"
                                     r"SEC-[0-9A-F]{6,}|nonce)\b", re.IGNORECASE),
     "An internal system identifier appeared in customer-facing text."),
    ("prompt_leak", re.compile(r"(system prompt|instruction|tool call|semantic model)",
                               re.IGNORECASE),
     "Platform internals appeared in customer-facing text."),
]


@dataclass
class CommsGuardResult:
    passed: bool
    findings: list[dict[str, Any]] = field(default_factory=list)
    approved_amount_only: bool = True
    reasoning: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": self.findings,
            "approved_amount_only": self.approved_amount_only,
            "reasoning": self.reasoning,
        }


def screen_customer_message(
    body: str, *, approved_amount_eur: float | None = None
) -> CommsGuardResult:
    """The outbound guard that always applies to customer communication.

    Two things are checked: that no platform internals leaked into the text, and that any
    figure quoted is the approved figure. A message that quotes an amount the decision
    does not carry is withheld rather than sent.
    """
    findings: list[dict[str, Any]] = []

    for name, pattern, detail in INTERNAL_ARTEFACT_PATTERNS:
        m = pattern.search(body or "")
        if m:
            findings.append({
                "finding": name,
                "detail": detail,
                "matched": m.group(0)[:80],
            })

    amount_ok = True
    quoted = re.findall(r"EUR\s*(\d(?:[\d.,]*\d)?)", body or "")
    if quoted:
        parsed: list[float] = []
        for q in quoted:
            value = parse_eur_amount(q)
            if value is not None:
                parsed.append(value)
        allowed = {round(approved_amount_eur or 0.0, 2)}
        stray = [v for v in parsed if v not in allowed and v != 0.0]
        # An excess is quoted alongside the settlement, so a second figure is expected;
        # what is refused is a figure larger than the approved settlement.
        over = [v for v in stray if approved_amount_eur is not None and v > approved_amount_eur]
        if over:
            amount_ok = False
            findings.append({
                "finding": "unapproved_amount",
                "detail": (
                    f"The message quotes EUR {over[0]:,.2f}, which is above the approved "
                    f"settlement of EUR {approved_amount_eur or 0.0:,.2f}."
                ),
                "matched": f"EUR {over[0]:,.2f}",
            })

    passed = not findings
    return CommsGuardResult(
        passed=passed,
        findings=findings,
        approved_amount_only=amount_ok,
        reasoning=(
            "Customer message cleared the outbound guard."
            if passed
            else f"{len(findings)} outbound finding(s) — message withheld for review."
        ),
    )
