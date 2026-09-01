"""Typed agent contracts.

Every agent's output is a Pydantic model, and the model is the contract — not a
convention, not a docstring. Whichever runtime serves the reasoning turn, the result is
validated against these before anything downstream is allowed to see it, and a Pydantic AI
agent will re-ask the model when validation fails rather than passing a malformed answer on.

This is what lets the policy guard be strict: it is never parsing prose.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Eur = Annotated[float, Field(ge=0.0)]


class Strict(BaseModel):
    """Reject anything the contract does not name.

    Used for whatever a model produces directly, so a hallucinated field is an error
    rather than something that quietly travels downstream.
    """

    model_config = ConfigDict(extra="forbid")


class Lenient(BaseModel):
    """Accept the shape, ignore the surplus.

    Used for the value objects that wrap tool output. Types, enums and ranges are still
    enforced; what is dropped is only the reference detail the tool layer attaches.
    """

    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------
class Citation(BaseModel):
    """A clause an answer rests on.

    Unlike the agent-level contracts this one *ignores* extra keys rather than rejecting
    them: a citation is reference data flowing out of retrieval, and the retrieval layer
    legitimately attaches scoring detail that is not part of the citation itself. What the
    model produces is still held to a strict contract — this is not.
    """

    model_config = ConfigDict(extra="ignore")

    clause_id: str
    title: str = ""
    section: str = ""
    page: int = 0
    quote: str = ""
    document: str = ""
    document_title: str = ""
    version: str = ""
    effective_from: str = ""
    jurisdiction: str = ""


class EvidenceGap(Lenient):
    field_name: str = ""
    read_as: str = ""
    confidence: Confidence = 0.0
    ask: str = Field(description="The one specific question to put to the customer.")


class TriageResult(Strict):
    """Intake Orchestrator — what is missing and what to ask."""

    next_step: Literal[
        "request_information", "re_ask_specific_view",
        "confirm_low_confidence_reads", "proceed_to_assessment",
    ]
    summary: str
    evidence_completeness: Confidence = 0.0
    missing: list[str] = []
    needs_confirmation: list[EvidenceGap] = []
    # A file that could not be read is a different problem from a file that is absent: it
    # needs one specific view re-taken, not a general request for more.
    unreadable: list[EvidenceGap] = []
    customer_questions: list[str] = []
    injury_reported: bool = False
    suspicious_content: list[str] = []


class DocumentRead(Lenient):
    doc_id: str
    doc_type: str = ""
    quality_score: Confidence = 0.0
    low_confidence_fields: list[str] = []


class DocumentUnderstanding(Strict):
    """Document Understanding — what each document is, and what does not add up."""

    documents: list[DocumentRead] = []
    document_count: int = 0
    conflicts: list[str] = []
    quote_total_eur: Eur | None = None
    summary: str
    suspicious_content: list[str] = []


class CoverageView(Strict):
    """Coverage — the policy position, and the clause it rests on."""

    status: Literal["covered", "covered_with_excess", "excluded", "lapsed", "unknown"]
    product: str = ""
    in_force_on_date_of_loss: bool = True
    excess_eur: Eur = 0.0
    reasoning: str
    citations: list[Citation] = []
    clauses_applied: list[str] = []
    confidence: Confidence = 0.0
    abstained: bool = False
    summary: str = ""


class PanelFinding(Lenient):
    panel: str
    action: Literal["repair", "replace"] = "repair"
    paint: bool = False
    structural: bool = False
    confidence: Confidence = 0.0


class DamageAssessment(Strict):
    """Damage Assessment — severity, and what cannot be read."""

    severity: Literal["simple", "complex"]
    severity_basis: str
    structural_damage: bool = False
    panels: list[PanelFinding] = []
    panel_count: int = 0
    missing_views: list[str] = []
    confidence: Confidence = 0.0
    summary: str = ""


class EstimateLine(Lenient):
    part: str
    action: str = "repair"
    part_price_eur: Eur = 0.0
    labour_hours: float = 0.0


class RepairEstimate(Strict):
    """Repair Estimate — the itemised figure, computed in the sandbox."""

    items: list[EstimateLine] = []
    labour_hours: float = 0.0
    labour_rate_eur: Eur = 0.0
    total_parts: Eur = 0.0
    total_labour: Eur = 0.0
    total_tax: Eur = 0.0
    total_cost: Eur = 0.0
    region: str = ""
    within_band: bool = True
    band_verdict: str = ""
    summary: str = ""


class RepairabilityVerdict(Strict):
    """Total Loss — repair cost against replacement value (AKKB Art 5.1.1)."""

    verdict: Literal["economically_repairable", "total_loss", "borderline"]
    repair_cost_eur: Eur = 0.0
    replacement_value_eur: Eur = 0.0
    ratio: float = Field(default=0.0, ge=0.0)
    threshold: float = 0.70
    residual_value_eur: Eur = 0.0
    payable_on_total_loss_eur: Eur = 0.0
    # The vehicle basis and the Neuwertersatz inputs. Carried on the contract because an
    # indemnity that cannot see them silently falls back to the repair estimate — which is
    # how the endorsement stayed inert while appearing to work in deterministic mode.
    on_vehicle_basis_eur: Eur = 0.0
    new_for_old_available: bool = False
    new_price_eur: Eur = 0.0
    total_loss_basis: str = ""
    repair_option_available: bool = False
    reasoning: str
    citations: list[Citation] = []
    summary: str = ""


class RiskSignal(Lenient):
    signal_type: str
    detail: str
    weight: float = 0.0


class RiskPicture(Strict):
    """Fraud & Risk — signals, never findings."""

    score: Confidence = 0.0
    threshold: Confidence = 0.55
    above_threshold: bool = False
    signals: list[RiskSignal] = []
    flagged_relationships: int = 0
    recommendation: Literal["freeze_and_refer_siu", "no_investigation_required"]
    summary: str = ""
    note: str = ""


class DecisionProposal(Strict):
    """Decision — one proposal, on coverage and evidence alone.

    Deliberately does not carry the ceiling, the severity rule, the injury stop or the
    fraud threshold. Those belong to the deterministic guard downstream.
    """

    decision: Literal["Approved", "Declined", "Review Required", "Request Information"]
    settlement_amount_eur: Eur = 0.0
    reasoning: str
    summary: str = ""


class ReviewTaskCreated(Strict):
    """HITL Coordinator — the task, on the right queue at the right authority."""

    task_id: str = ""
    queue: Literal["handler", "coverage", "assessment", "operations", "supervisor",
                   "injury", "siu", "large_loss", "recovery",
                   "security"]
    authority_required: str = ""
    reason: str = ""
    summary: str = ""


class RecoveryAssessment(Strict):
    """Recovery — whether there is a third party worth pursuing (Regress)."""

    recoverable: bool = False
    basis: Literal["third_party_at_fault", "shared_liability", "no_recoverable_party",
                   "uninsured_third_party", "unknown"] = "unknown"
    recoverable_amount_eur: Eur = 0.0
    prospects: Literal["strong", "moderate", "weak", "none"] = "none"
    next_action: str = ""
    reasoning: str
    summary: str = ""


class CustomerMessage(Strict):
    """Customer Communication — approved templates only, and always a route to a person."""

    template_id: str
    language: Literal["de", "en"]
    subject: str
    body: str
    route_to_human_offered: bool = True


AGENT_OUTPUT_TYPES: dict[str, type[BaseModel]] = {
    "document_understanding": DocumentUnderstanding,
    "intake_orchestrator": TriageResult,
    "coverage": CoverageView,
    "damage_assessment": DamageAssessment,
    "repair_estimate": RepairEstimate,
    "total_loss": RepairabilityVerdict,
    "fraud_risk": RiskPicture,
    "decision": DecisionProposal,
    "hitl_coordinator": ReviewTaskCreated,
    "recovery": RecoveryAssessment,
    "customer_communication": CustomerMessage,
}


def schema_for(agent_key: str) -> type[BaseModel] | None:
    return AGENT_OUTPUT_TYPES.get(agent_key)
