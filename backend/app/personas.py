"""Personas — who uses this platform, what they see, and the coworker that helps them.

Six personas. Five are the roles a European motor claims department actually runs on,
and one is the customer. They are deliberately few, and each one exists because it owns
a different part of the claim.

Two of them came out of looking at how the work is really divided:

  * The **Kfz-Sachverständiger** (motor assessor) is a distinct role, not a variant of the
    handler. They judge the damage, whether the vehicle is worth repairing at all
    (Reparaturwürdigkeit), and what it was worth on the day (Zeitwert). They hold no
    settlement authority — the technical call and the money are deliberately separated.
  * **Recovery** (Regress) is part of the handler's job, not an afterthought: identifying
    whether there is a third party to recover from is one of the things they are measured on.

Everything below is synthetic. The names, addresses, policy numbers and vehicles were
written for this build and correspond to no real person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# The feature catalogue. A persona sees only its own entries — this is the whole
# simplification: one platform, six small products.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    hint: str
    icon: str
    stages: tuple[str, ...] = ()


FEATURES: dict[str, Feature] = {
    "my_claims": Feature("my_claims", "My claims", "Where each of your claims stands",
                         "folder", ("notify", "close")),
    "file_claim": Feature("file_claim", "Report an accident", "Tell us what happened",
                          "plus", ("notify", "screen")),
    "work_queue": Feature("work_queue", "My desk", "Claims waiting on you",
                          "inbox", ("triage", "coverage", "decision")),
    "assessment_queue": Feature("assessment_queue", "Assessments",
                                "Damage, estimates and repairability", "wrench",
                                ("damage", "estimate", "total_loss")),
    "approvals": Feature("approvals", "Approvals",
                         "Decisions above handler authority", "check", ("approval",)),
    "investigations": Feature("investigations", "Investigations",
                              "Referrals and the relationships behind them", "shield",
                              ("risk",)),
    "recovery": Feature("recovery", "Recovery",
                        "Third-party recovery on settled claims", "arrow-back",
                        ("recovery",)),
    "team": Feature("team", "Team", "Throughput, SLA and where automation stops",
                    "chart", ("approval", "close")),
    "governance": Feature("governance", "Zero trust",
                          "The three pillars, the ledger and the drills", "lock",
                          ("screen", "guard", "settle")),
    "evaluations": Feature("evaluations", "Evaluations",
                           "Golden cases, groundedness and drift", "beaker", ("close",)),
    "llm_usage": Feature("llm_usage", "Model usage",
                         "Rate limits, tokens and cost per claim", "gauge", ()),
    "platform": Feature("platform", "Agents & data",
                        "The agents, their scopes and the semantic layer", "graph", ()),
    "coworker": Feature("coworker", "AI coworker", "Ask it to do your work with you",
                        "sparkle", ()),
}


# --------------------------------------------------------------------------
# Coworker tool catalogue. A coworker is just another agent identity, so it is
# scoped the same way: it can only reach what its persona is allowed to reach.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CoworkerTool:
    name: str
    label: str
    description: str
    risk_class: str = "read-low"
    writes: bool = False


COWORKER_TOOLS: dict[str, CoworkerTool] = {
    "list_my_claims": CoworkerTool(
        "list_my_claims", "My claims",
        "List the claims belonging to this policyholder and where each one stands."),
    "explain_my_claim": CoworkerTool(
        "explain_my_claim", "Explain a claim",
        "Explain in plain language what has happened on a claim and what happens next."),
    "what_do_you_need": CoworkerTool(
        "what_do_you_need", "Outstanding items",
        "Say exactly what is still needed from the customer, and why."),
    "list_my_queue": CoworkerTool(
        "list_my_queue", "My queue",
        "List the open work on this persona's queues, most pressing first."),
    "summarise_claim": CoworkerTool(
        "summarise_claim", "Summarise a claim",
        "A working summary of a claim: cover, damage, estimate, risk and current position.",
        risk_class="read-medium"),
    "why_was_it_held": CoworkerTool(
        "why_was_it_held", "Why was it held",
        "Name the deterministic checks that stopped a claim and what would clear each one.",
        risk_class="read-medium"),
    "check_coverage": CoworkerTool(
        "check_coverage", "Check cover",
        "Answer a coverage question against the policy wording, with the clause quoted.",
        risk_class="read-medium"),
    "check_repairability": CoworkerTool(
        "check_repairability", "Repairability",
        "Repair cost against replacement value, and whether this is a total loss.",
        risk_class="read-medium"),
    "review_estimate": CoworkerTool(
        "review_estimate", "Review an estimate",
        "Walk an itemised estimate line by line against the approved catalogue and rates.",
        risk_class="read-medium"),
    "risk_picture": CoworkerTool(
        "risk_picture", "Risk picture",
        "The signals on a claim and the party, vehicle, device, address and repairer graph.",
        risk_class="read-high"),
    "recovery_prospects": CoworkerTool(
        "recovery_prospects", "Recovery prospects",
        "Whether there is a third party to recover from, and what it is worth pursuing.",
        risk_class="read-medium"),
    "my_authority": CoworkerTool(
        "my_authority", "My authority",
        "What this persona may approve, and what has to go higher."),
    "team_position": CoworkerTool(
        "team_position", "Team position",
        "Open work, SLA pressure and where automation is stopping most often.",
        risk_class="read-medium"),
    "draft_customer_note": CoworkerTool(
        "draft_customer_note", "Draft a note to the customer",
        "Draft a customer-safe message from an approved template. The outbound guard "
        "applies, so it is a draft for a person to send.",
        risk_class="draft-only"),
    "security_posture": CoworkerTool(
        "security_posture", "Security posture",
        "Which controls are active, what is enforced, and the state of the ledger.",
        risk_class="read-medium"),
    "verify_integrity": CoworkerTool(
        "verify_integrity", "Verify integrity",
        "Walk the ledger chain and reconcile it against the live rows.",
        risk_class="read-high"),
    "model_usage": CoworkerTool(
        "model_usage", "Model usage",
        "Rate limits, token consumption and cost per claim by model."),
}


@dataclass(frozen=True)
class Coworker:
    name: str
    tagline: str
    remit: str
    tools: tuple[str, ...]
    starters: tuple[str, ...]
    cannot: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "tagline": self.tagline, "remit": self.remit,
            "starters": list(self.starters), "cannot": list(self.cannot),
            "tools": [
                {
                    "name": COWORKER_TOOLS[t].name,
                    "label": COWORKER_TOOLS[t].label,
                    "description": COWORKER_TOOLS[t].description,
                    "risk_class": COWORKER_TOOLS[t].risk_class,
                }
                for t in self.tools if t in COWORKER_TOOLS
            ],
        }


# --------------------------------------------------------------------------
# The personas
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Persona:
    key: str
    user_id: str
    name: str
    initials: str
    role_label: str
    role_de: str
    kind: str                      # customer | staff
    location: str
    authority_limit_eur: float
    queues: tuple[str, ...]
    remit: str
    measured_on: tuple[str, ...]
    features: tuple[str, ...]
    coworker: Coworker
    party_id: str | None = None    # customers only
    accent: str = "blue"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "user_id": self.user_id, "name": self.name,
            "initials": self.initials, "role_label": self.role_label,
            "role_de": self.role_de, "kind": self.kind, "location": self.location,
            "authority_limit_eur": self.authority_limit_eur,
            "queues": list(self.queues), "remit": self.remit,
            "measured_on": list(self.measured_on), "party_id": self.party_id,
            "accent": self.accent,
            "features": [
                {**FEATURES[f].__dict__, "stages": list(FEATURES[f].stages)}
                for f in self.features if f in FEATURES
            ],
            "coworker": self.coworker.as_dict(),
        }


PERSONAS: tuple[Persona, ...] = (
    Persona(
        key="policyholder",
        user_id="lena.hofer",
        name="Lena Hofer",
        initials="LH",
        role_label="Policyholder",
        role_de="Versicherungsnehmerin",
        kind="customer",
        location="Wien",
        authority_limit_eur=0.0,
        queues=(),
        party_id="PTY-AT-100241",
        accent="teal",
        remit=(
            "Reports an accident from her phone, adds what she has, and wants to know "
            "where her claim is without having to ring anyone."
        ),
        measured_on=("time to a decision", "how often she has to ask twice"),
        features=("my_claims", "file_claim", "coworker"),
        coworker=Coworker(
            name="Claim Assistant",
            tagline="Reports an accident with you and tells you where things stand",
            remit=(
                "Helps a customer report an accident, explains where their claim is in "
                "plain language, and says exactly what is still needed. It never quotes a "
                "figure the decision does not carry, and it always leaves a route to a person."
            ),
            tools=("list_my_claims", "explain_my_claim", "what_do_you_need"),
            starters=(
                "Where is my claim?",
                "What do you still need from me?",
                "Why is my claim with a person?",
                "How much will I get, and when?",
            ),
            cannot=("approve anything", "change a decision", "see another customer's claim"),
        ),
    ),
    Persona(
        key="claims_handler",
        user_id="klaus.reiter",
        name="Klaus Reiter",
        initials="KR",
        role_label="Claims Handler",
        role_de="Sachbearbeiter Kfz-Schadenregulierung",
        kind="staff",
        location="Wien",
        authority_limit_eur=5_000.0,
        queues=("handler", "coverage"),
        accent="blue",
        remit=(
            "Owns the desk file. Establishes cover, routes the claim to an assessor or a "
            "repairer, settles within his authority, refers what he cannot settle, flags "
            "anything that smells wrong to SIU, and looks for a third party to recover from."
        ),
        measured_on=("claims closed per week", "first-time-right", "recovery identified",
                     "leakage"),
        features=("work_queue", "recovery", "coworker"),
        coworker=Coworker(
            name="Desk Assistant",
            tagline="Works the file with you — cover, position, and the next move",
            remit=(
                "Reads the file the way a handler would: what the cover says and on which "
                "clause, what stopped the claim, what it would take to clear it, and "
                "whether there is anyone to recover from. It drafts customer notes; it does "
                "not send them."
            ),
            tools=("list_my_queue", "summarise_claim", "why_was_it_held", "check_coverage",
                   "recovery_prospects", "draft_customer_note", "my_authority"),
            starters=(
                "What is on my desk, most pressing first?",
                "Why was AT-2026-004418 held?",
                "Is own-vehicle damage covered under a liability-only policy?",
                "Is there anyone to recover from on AT-2026-004421?",
                "Draft a note to the customer explaining the delay.",
            ),
            cannot=("approve above EUR 5,000", "send a message to a customer",
                    "open an SIU investigation itself"),
        ),
    ),
    Persona(
        key="motor_assessor",
        user_id="martin.gruber",
        name="Martin Gruber",
        initials="MG",
        role_label="Motor Assessor",
        role_de="Kfz-Sachverständiger",
        kind="staff",
        location="Graz",
        authority_limit_eur=0.0,
        queues=("assessment",),
        accent="amber",
        remit=(
            "Judges the damage itself: which panels, repair or replace, whether the "
            "structure is affected, and whether the vehicle is worth repairing at all. "
            "Holds no settlement authority — the technical call and the money are separate "
            "on purpose."
        ),
        measured_on=("estimate accuracy against final invoice",
                     "total-loss calls that hold up", "assessment turnaround"),
        features=("assessment_queue", "coworker"),
        coworker=Coworker(
            name="Assessor Assistant",
            tagline="Checks the estimate and the repairability call with you",
            remit=(
                "Walks an itemised estimate against the approved parts catalogue and the "
                "regional labour rate, flags any line that is outside the band, and works "
                "the repair-cost-to-replacement-value test that decides a total loss."
            ),
            tools=("list_my_queue", "review_estimate", "check_repairability",
                   "summarise_claim"),
            starters=(
                "Which assessments are waiting on me?",
                "Walk me through the estimate on AT-2026-004418.",
                "Is AT-2026-004420 economically repairable?",
                "Which lines on this estimate are outside the band?",
            ),
            cannot=("settle a claim", "approve a payment", "change the cover position"),
        ),
    ),
    Persona(
        key="team_leader",
        user_id="ingrid.mayer",
        name="Ingrid Mayer",
        initials="IM",
        role_label="Claims Team Leader",
        role_de="Teamleiterin Schaden Kfz",
        kind="staff",
        location="Wien",
        authority_limit_eur=25_000.0,
        queues=("supervisor", "handler", "injury"),
        accent="indigo",
        remit=(
            "Approves what is above handler authority, owns the team's SLA, and reviews a "
            "sample of what the platform decided on its own. Where automation stops most "
            "often is her problem to fix, not the platform's to hide."
        ),
        measured_on=("SLA attainment", "approval turnaround",
                     "override rate by reason", "straight-through rate"),
        features=("approvals", "team", "coworker"),
        coworker=Coworker(
            name="Supervisor Assistant",
            tagline="Prepares the approvals and shows where automation is stopping",
            remit=(
                "Prepares an approval: what the agent proposed, which checks stopped it, "
                "what the exposure is, and what authority it needs. Then shows where "
                "automation is stopping most often across the team and why."
            ),
            tools=("list_my_queue", "why_was_it_held", "summarise_claim", "my_authority",
                   "team_position"),
            starters=(
                "What is waiting on my approval?",
                "Prepare AT-2026-004418 for me — what am I signing?",
                "Where is automation stopping most often this week?",
                "Which claims are at risk of breaching SLA?",
            ),
            cannot=("approve on her behalf", "raise its own authority",
                    "release an SIU freeze"),
        ),
    ),
    Persona(
        key="siu_investigator",
        user_id="thomas.wagner",
        name="Thomas Wagner",
        initials="TW",
        role_label="Special Investigations",
        role_de="Sonderermittlung / Betrugsabwehr",
        kind="staff",
        location="Wien",
        authority_limit_eur=0.0,
        queues=("siu",),
        accent="rose",
        remit=(
            "Takes referrals from handlers and from the platform's own signals, works the "
            "relationships behind them, and either releases the claim or refers it on. "
            "Settlement authority is zero by design: he investigates, he does not decide "
            "the money."
        ),
        measured_on=("referrals worked", "confirmed leakage prevented",
                     "false-positive rate"),
        features=("investigations", "coworker"),
        coworker=Coworker(
            name="Investigation Assistant",
            tagline="Walks the network and separates signal from coincidence",
            remit=(
                "Lays out the signals on a referred claim and walks the party, vehicle, "
                "device, address and repairer graph around it. It reports signals, never "
                "findings — and it will say when a pattern is more likely coincidence."
            ),
            tools=("list_my_queue", "risk_picture", "summarise_claim"),
            starters=(
                "What has been referred to me?",
                "Show me the network around AT-2026-004420.",
                "Why was this claim frozen?",
                "Is this pattern strong enough to open an investigation?",
            ),
            cannot=("decline a claim", "settle a claim",
                    "act on a signal without a person confirming it"),
        ),
    ),
    Persona(
        key="compliance_officer",
        user_id="eva.pichler",
        name="Eva Pichler",
        initials="EP",
        role_label="Compliance & Operational Risk",
        role_de="Compliance & Operationelles Risiko",
        kind="staff",
        location="Wien",
        authority_limit_eur=0.0,
        queues=(),
        accent="slate",
        remit=(
            "Reads the platform rather than the claims. Which controls are on, what they "
            "stopped, whether the ledger still verifies, whether quality has drifted, and "
            "what the models are costing. Read-only everywhere by design."
        ),
        measured_on=("control coverage", "audit findings closed",
                     "evaluation pass rate", "cost per claim"),
        features=("governance", "evaluations", "llm_usage", "platform", "coworker"),
        coworker=Coworker(
            name="Assurance Assistant",
            tagline="Answers what is enforced, what it stopped, and what it cost",
            remit=(
                "Reports the state of the control plane: which pillars are active, what "
                "each one is enforcing, what it has stopped, whether the ledger chain and "
                "the live rows still agree, and what the models are consuming."
            ),
            tools=("security_posture", "verify_integrity", "model_usage",
                   "why_was_it_held"),
            starters=(
                "What is being enforced right now?",
                "Has anything been changed out of band?",
                "What have the controls stopped this week?",
                "What are we spending per claim, and on which model?",
            ),
            cannot=("approve anything", "change a threshold", "clear a security event"),
        ),
    ),
)

PERSONA_BY_KEY: dict[str, Persona] = {p.key: p for p in PERSONAS}
PERSONA_BY_USER: dict[str, Persona] = {p.user_id: p for p in PERSONAS}
DEFAULT_PERSONA = "claims_handler"


def persona(key: str | None) -> Persona:
    return PERSONA_BY_KEY.get(key or "", PERSONA_BY_KEY[DEFAULT_PERSONA])


def persona_by_user(user_id: str | None) -> Persona | None:
    return PERSONA_BY_USER.get(user_id or "")


def has_feature(key: str | None, feature: str) -> bool:
    return feature in persona(key).features


def coworker_tools_for(key: str | None) -> tuple[str, ...]:
    return persona(key).coworker.tools


# Queue → the personas that work it. Used to scope a work list to whoever is looking.
QUEUE_OWNERS: dict[str, tuple[str, ...]] = {
    "handler": ("claims_handler", "team_leader"),
    "coverage": ("claims_handler",),
    "assessment": ("motor_assessor",),
    "supervisor": ("team_leader",),
    "injury": ("team_leader",),
    "siu": ("siu_investigator",),
}

# Legacy queue names still written by the guard routing, mapped onto the roles above.
QUEUE_ALIASES: dict[str, str] = {
    "adjuster": "handler",
    "specialist": "injury",
}


def normalise_queue(queue: str | None) -> str | None:
    if not queue:
        return None
    return QUEUE_ALIASES.get(queue, queue)


def queues_for(key: str | None) -> tuple[str, ...]:
    return persona(key).queues


AUTHORITY_BY_PERSONA: dict[str, float] = {p.key: p.authority_limit_eur for p in PERSONAS}
