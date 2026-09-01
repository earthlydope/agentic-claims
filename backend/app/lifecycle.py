"""The claim lifecycle — every stage, and who owns it.

Fifteen stages from first notification to closure. The earlier build stopped at the
signed write; research into how a motor claims department actually works surfaced four
stages that were missing and that a claim genuinely cannot finish without:

  * the total-loss test — repair cost against replacement value, which is the assessor's
    call and not the handler's (AKKB Art 5.1.1)
  * settlement execution — the money actually moving, which is never autonomous
  * recovery — identifying and pursuing a claim against a third party (Regress)
  * closure — the file being closed, with the reason recorded

Each stage names the persona that owns it, so a role only ever sees its own work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Lanes, as the business-flow diagram draws them.
LANE_CUSTOMER = "customer"
LANE_PLATFORM = "platform"
LANE_PEOPLE = "people"


@dataclass(frozen=True)
class Stage:
    no: int
    id: str
    title: str
    lane: str
    owner: str                     # the persona whose work this is
    pillar: int | None = None      # which zero-trust pillar guards it, if any
    agent: str | None = None       # the agent that reasons here, if any
    summary: str = ""
    exceptions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "no": self.no, "id": self.id, "title": self.title, "lane": self.lane,
            "owner": self.owner, "pillar": self.pillar, "agent": self.agent,
            "summary": self.summary, "exceptions": list(self.exceptions),
        }


STAGES: tuple[Stage, ...] = (
    Stage(1, "notify", "Notify", LANE_CUSTOMER, "policyholder",
          summary="The customer reports the accident and adds whatever evidence they have.",
          exceptions=("no evidence at all — the assistant asks for what it needs",)),
    Stage(2, "screen", "Screen", LANE_PLATFORM, "platform", pillar=1,
          summary="Everything is screened before a model sees it and before a claim record exists.",
          exceptions=("prompt injection — blocked at the gateway",
                      "hidden instruction inside a file — stripped, file quarantined")),
    Stage(3, "intake", "Read the evidence", LANE_PLATFORM, "platform",
          agent="DocumentUnderstandingAgent",
          summary="Each document is classified and every field carries its own confidence.",
          exceptions=("unreadable photo — one specific new view is requested",
                      "documents contradict each other — the conflict is surfaced")),
    Stage(4, "triage", "Triage", LANE_PLATFORM, "claim_handler",
          agent="IntakeOrchestratorAgent",
          summary="What is still missing, what to ask, and which desk the claim belongs on.",
          exceptions=("injury mentioned — routed to the injury desk immediately",)),
    Stage(5, "coverage", "Coverage", LANE_PLATFORM, "claim_handler",
          agent="CoverageAgent",
          summary="The policy position on the date of loss, with the clause relied on.",
          exceptions=("no authoritative clause — the platform abstains and refers",)),
    Stage(6, "damage", "Damage assessment", LANE_PLATFORM, "motor_assessor",
          agent="DamageAssessmentAgent",
          summary="Which panels, what action each needs, and whether the damage is structural.",
          exceptions=("structural damage — autonomy is off from here on",)),
    Stage(7, "estimate", "Repair estimate", LANE_PLATFORM, "motor_assessor", pillar=2,
          agent="RepairEstimateAgent",
          summary="An itemised figure from the approved catalogue and the regional rate card.",
          exceptions=("estimate outside the reasonableness band — flagged as an outlier",)),
    Stage(8, "total_loss", "Repairability", LANE_PLATFORM, "motor_assessor",
          agent="TotalLossAgent",
          summary="Repair cost against replacement value. Above the threshold it is a total loss.",
          exceptions=("total loss — the file changes shape and the assessor decides",)),
    Stage(9, "risk", "Risk screening", LANE_PLATFORM, "siu",
          agent="FraudRiskAgent",
          summary="Duplicate, pattern, velocity and relationship signals, with the graph behind them.",
          exceptions=("elevated signal — autonomy frozen, evidence trail preserved",)),
    Stage(10, "decision", "Decision", LANE_PLATFORM, "claim_handler",
          agent="DecisionAgent",
          summary="One proposed decision, assembled from coverage and evidence alone.",
          exceptions=()),
    Stage(11, "guard", "Policy guard", LANE_PLATFORM, "platform", pillar=1,
          summary="Ten deterministic checks applied after the model has spoken.",
          exceptions=("any check fails — downgraded to review, recommendation preserved",)),
    Stage(12, "approval", "Human approval", LANE_PEOPLE, "compliance_ops",
          agent="HitlCoordinatorAgent",
          summary="Approve, amend, reject or ask for more — scoped to claim, action, limit and expiry.",
          exceptions=("above the approver's authority — refused before anything is signed",)),
    Stage(13, "settle", "Settlement", LANE_PLATFORM, "claim_handler", pillar=3,
          agent="SettlementAgent",
          summary="The money moving: signed, verified at the gateway, written once.",
          exceptions=("write times out — the idempotency key is reconciled before any retry",)),
    Stage(14, "recovery", "Recovery", LANE_PEOPLE, "claim_handler",
          agent="RecoveryAgent",
          summary="Whether there is a third party to recover from, and what it is worth pursuing.",
          exceptions=("no recoverable party — recorded and closed with the reason",)),
    Stage(15, "close", "Close & learn", LANE_PLATFORM, "compliance_ops",
          summary="The file is closed, and the trace, cost and evaluation feed the next release.",
          exceptions=()),
)

STAGE_BY_ID: dict[str, Stage] = {s.id: s for s in STAGES}
STAGE_IDS: tuple[str, ...] = tuple(s.id for s in STAGES)


def stages_for(owner: str) -> list[Stage]:
    """The stages a given persona is accountable for."""
    return [s for s in STAGES if s.owner == owner]


def stage_dicts() -> list[dict[str, Any]]:
    return [s.as_dict() for s in STAGES]


# --------------------------------------------------------------------------
# Claim status, and how it maps onto the lifecycle
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ClaimStatus:
    """One claim status, in both of the languages the platform speaks.

    The German is carried here rather than translated in the browser because a status is a
    business term with a settled Austrian wording — "Mit einem Mitarbeiter" is what a
    handler would say, and a client-side translation table would drift from it.
    """

    key: str
    label: str
    stage: str
    tone: str            # ok | warn | stop | info | neutral
    terminal: bool = False
    description: str = ""
    label_de: str = ""
    description_de: str = ""


STATUSES: tuple[ClaimStatus, ...] = (
    ClaimStatus("fnol_received", "Reported", "notify", "info",
                description="The customer has told us. Nothing has been assessed yet.",
                label_de="Gemeldet",
                description_de="Die Meldung ist eingegangen. Es wurde noch nichts geprüft."),
    ClaimStatus("blocked_security_review", "Held at the gateway", "screen", "stop",
                description="Stopped before a model saw it. A security review owns it.",
                label_de="Am Gateway gestoppt",
                description_de="Gestoppt, bevor ein Modell es gesehen hat. Die "
                               "Sicherheitsprüfung übernimmt."),
    ClaimStatus("awaiting_customer", "Waiting on the customer", "triage", "warn",
                description="One specific thing has been asked for.",
                label_de="Warten auf den Kunden",
                description_de="Eine konkrete Unterlage wurde angefordert."),
    ClaimStatus("assessing", "Being assessed", "damage", "info",
                description="Coverage, damage, estimate and risk are being established.",
                label_de="In Prüfung",
                description_de="Deckung, Schaden, Kostenvoranschlag und Risiko werden "
                               "festgestellt."),
    ClaimStatus("in_review", "With a person", "approval", "warn",
                description="A check stopped it, or automation could not reach an outcome on its own.",
                label_de="Bei einem Mitarbeiter",
                description_de="Eine Prüfung hat den Fall gestoppt, oder es wurde eine "
                               "Begutachtung angefordert."),
    ClaimStatus("total_loss_review", "Total loss review", "total_loss", "warn",
                description="Repair cost is above the threshold. The assessor decides.",
                label_de="Totalschadenprüfung",
                description_de="Die Reparaturkosten liegen über der Grenze. Der "
                               "Sachverständige entscheidet."),
    ClaimStatus("under_investigation", "Under investigation", "risk", "stop",
                description="Autonomous progression frozen. SIU owns the file.",
                label_de="In Sonderprüfung",
                description_de="Die automatische Bearbeitung ist gesperrt. Die "
                               "Sonderermittlung führt den Fall."),
    ClaimStatus("approved", "Approved", "settle", "ok",
                description="Cleared to settle. The write is signed.",
                label_de="Genehmigt",
                description_de="Zur Abrechnung freigegeben. Der Vorgang ist signiert."),
    ClaimStatus("settled", "Settled", "settle", "ok",
                description="The money has moved, once, against a signed envelope.",
                label_de="Abgerechnet",
                description_de="Die Zahlung ist erfolgt — genau einmal, gegen einen "
                               "signierten Vorgang."),
    ClaimStatus("recovery_open", "Recovery open", "recovery", "info",
                description="Settled, with a recovery being pursued against a third party.",
                label_de="Regress offen",
                description_de="Abgerechnet; gegenüber einem Dritten wird Regress geführt."),
    ClaimStatus("declined", "Declined", "close", "stop", terminal=True,
                description="Declined by a named person, with the reason on the file.",
                label_de="Abgelehnt",
                description_de="Von einem benannten Mitarbeiter abgelehnt, mit Begründung "
                               "im Akt."),
    ClaimStatus("closed_without_payment", "Closed — nothing payable", "close", "neutral",
                terminal=True,
                description="Settled at nil: the assessed amount did not exceed the excess.",
                label_de="Abgeschlossen — keine Zahlung",
                description_de="Mit Null erledigt: der ermittelte Betrag übersteigt den "
                               "Selbstbehalt nicht."),
    ClaimStatus("closed", "Closed", "close", "neutral", terminal=True,
                description="The file is closed.",
                label_de="Abgeschlossen",
                description_de="Der Akt ist geschlossen."),
)

STATUS_BY_KEY: dict[str, ClaimStatus] = {s.key: s for s in STATUSES}


def status_meta(key: str | None) -> dict[str, Any]:
    status = STATUS_BY_KEY.get(key or "")
    if status is None:
        fallback = (key or "unknown").replace("_", " ")
        return {"key": key or "unknown", "label": fallback, "label_de": fallback,
                "stage": None, "tone": "neutral", "terminal": False, "description": "",
                "description_de": ""}
    return {
        "key": status.key, "label": status.label, "stage": status.stage,
        "tone": status.tone, "terminal": status.terminal,
        "description": status.description,
        "label_de": status.label_de or status.label,
        "description_de": status.description_de or status.description,
    }
