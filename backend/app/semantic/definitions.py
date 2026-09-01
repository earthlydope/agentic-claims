"""The governed semantic models — the agent's view of the business.

Six models, each with an entity, a grain, its dimensions and measures, and the typed
tools that may read it. An agent never sees a table and never writes SQL; it asks one of
these models a named question through the Semantic Query API. Access rules are applied
during retrieval, not filtered afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SemanticModel:
    name: str
    entity: str
    grain: str
    description: str
    dimensions: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)
    owner: str = "Claims Data Product"
    source_layer: str = "gold"
    quality: str = "certified"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity": self.entity,
            "grain": self.grain,
            "description": self.description,
            "dimensions": self.dimensions,
            "measures": self.measures,
            "tools": self.tools,
            "used_by": self.used_by,
            "owner": self.owner,
            "source_layer": self.source_layer,
            "quality": self.quality,
        }


SEMANTIC_MODELS: dict[str, SemanticModel] = {
    "sm_claim_360": SemanticModel(
        name="sm_claim_360",
        entity="Claim",
        grain="claim × event",
        description=(
            "The single view of a claim: where it is, how old it is, what stage it is at "
            "and how complete its evidence is."
        ),
        dimensions=["reference", "status", "stage", "channel", "language", "incident_type",
                    "incident_region", "severity", "assigned_queue"],
        measures=["age_hours", "evidence_completeness", "human_touches", "settlement_amount_eur"],
        tools=["get_claim_360", "get_claim_timeline"],
        used_by=["IntakeOrchestratorAgent", "DecisionAgent"],
    ),
    "sm_coverage": SemanticModel(
        name="sm_coverage",
        entity="Policy",
        grain="policy × cover",
        description=(
            "What the policy actually covers on the date of loss: active covers, excess, "
            "exclusions and endorsements."
        ),
        dimensions=["policy_number", "product", "status", "cover_code", "exclusion_code"],
        measures=["excess_eur", "sum_insured_eur", "annual_premium_eur"],
        tools=["get_policy_coverage", "get_endorsements"],
        used_by=["CoverageAgent"],
    ),
    "sm_damage_estimate": SemanticModel(
        name="sm_damage_estimate",
        entity="Estimate",
        grain="estimate × line",
        description=(
            "Approved parts prices, labour rates by region and the reasonableness band "
            "an estimate is expected to fall inside."
        ),
        dimensions=["part_code", "panel", "action", "region", "repairer_tier"],
        measures=["part_price_eur", "labour_rate_eur", "repair_hours", "replace_hours"],
        tools=["lookup_part_price", "get_labour_rate", "get_reasonableness_band"],
        used_by=["DamageAssessmentAgent", "RepairEstimateAgent"],
    ),
    "sm_risk_signals": SemanticModel(
        name="sm_risk_signals",
        entity="Claim",
        grain="claim × signal",
        description=(
            "Duplicate, pattern, velocity and relationship signals, with the graph "
            "neighbourhood that produced them."
        ),
        dimensions=["signal_type", "evidence_ref", "neighbour_type"],
        measures=["weight", "score", "neighbour_distance"],
        tools=["get_risk_signals", "graph_neighbours"],
        used_by=["FraudRiskAgent"],
    ),
    "sm_review_queue": SemanticModel(
        name="sm_review_queue",
        entity="Task",
        grain="review task",
        description=(
            "Human work: why a task exists, which queue owns it, what authority it needs "
            "and how it is ageing against SLA."
        ),
        dimensions=["queue", "reason", "authority_required", "status", "assigned_to"],
        measures=["priority", "authority_limit_eur", "age_minutes", "proposed_amount_eur"],
        tools=["create_review_task", "get_queue_state"],
        used_by=["HitlCoordinatorAgent"],
    ),
    "sm_customer_comms": SemanticModel(
        name="sm_customer_comms",
        entity="Message",
        grain="message",
        description=(
            "Approved templates only, with the tone, channel and language a customer is "
            "allowed to be written to in."
        ),
        dimensions=["template_id", "channel", "language", "tone", "status"],
        measures=["messages_sent"],
        tools=["get_template", "render_status_explanation"],
        used_by=["CustomerCommunicationAgent"],
    ),
}


# --------------------------------------------------------------------------
# Reference data owned by the semantic layer (Gold layer stand-in)
# --------------------------------------------------------------------------

# Approved labour rates per Austrian region, EUR per hour, tier-1 network repairer.
LABOUR_RATES_EUR: dict[str, float] = {
    "Wien": 142.0,
    "Niederösterreich": 128.0,
    "Oberösterreich": 126.0,
    "Steiermark": 124.0,
    "Salzburg": 138.0,
    "Tirol": 134.0,
    "Vorarlberg": 136.0,
    "Kärnten": 118.0,
    "Burgenland": 116.0,
}
DEFAULT_LABOUR_RATE_EUR = 125.0

# Approved panel catalogue: part price and standard hours by panel code.
PANEL_CATALOGUE: dict[str, dict[str, float]] = {
    "bumper_front":      {"part_price_eur": 486.0,  "repair_hours": 2.5, "replace_hours": 3.5, "paint_hours": 2.0},
    "bumper_rear":       {"part_price_eur": 452.0,  "repair_hours": 2.2, "replace_hours": 3.2, "paint_hours": 2.0},
    "door_front_left":   {"part_price_eur": 890.0,  "repair_hours": 3.5, "replace_hours": 4.5, "paint_hours": 2.5},
    "door_front_right":  {"part_price_eur": 890.0,  "repair_hours": 3.5, "replace_hours": 4.5, "paint_hours": 2.5},
    "door_rear_left":    {"part_price_eur": 845.0,  "repair_hours": 3.2, "replace_hours": 4.2, "paint_hours": 2.5},
    "fender_front_left": {"part_price_eur": 615.0,  "repair_hours": 2.8, "replace_hours": 3.8, "paint_hours": 2.2},
    "fender_front_right":{"part_price_eur": 615.0,  "repair_hours": 2.8, "replace_hours": 3.8, "paint_hours": 2.2},
    "bonnet":            {"part_price_eur": 720.0,  "repair_hours": 3.0, "replace_hours": 3.6, "paint_hours": 2.8},
    "tailgate":          {"part_price_eur": 1180.0, "repair_hours": 4.0, "replace_hours": 5.0, "paint_hours": 3.0},
    "windscreen":        {"part_price_eur": 640.0,  "repair_hours": 1.0, "replace_hours": 2.5, "paint_hours": 0.0},
    "side_window_left":  {"part_price_eur": 285.0,  "repair_hours": 0.8, "replace_hours": 1.5, "paint_hours": 0.0},
    "headlamp_left":     {"part_price_eur": 1240.0, "repair_hours": 0.8, "replace_hours": 1.6, "paint_hours": 0.0},
    "headlamp_right":    {"part_price_eur": 1240.0, "repair_hours": 0.8, "replace_hours": 1.6, "paint_hours": 0.0},
    "mirror_left":       {"part_price_eur": 320.0,  "repair_hours": 0.5, "replace_hours": 0.9, "paint_hours": 0.4},
    "wheel_alloy_18":    {"part_price_eur": 540.0,  "repair_hours": 0.6, "replace_hours": 0.9, "paint_hours": 0.8},
    "sill_left":         {"part_price_eur": 760.0,  "repair_hours": 4.5, "replace_hours": 7.5, "paint_hours": 2.6},
    "a_pillar_left":     {"part_price_eur": 1450.0, "repair_hours": 6.0, "replace_hours": 11.0, "paint_hours": 3.2},
    "radiator_support":  {"part_price_eur": 980.0,  "repair_hours": 4.0, "replace_hours": 8.0, "paint_hours": 1.5},
    "airbag_module":     {"part_price_eur": 1680.0, "repair_hours": 0.0, "replace_hours": 3.0, "paint_hours": 0.0},
}

# Structural panels: their presence forces "complex" severity and blocks autonomy.
STRUCTURAL_PANELS = {"a_pillar_left", "sill_left", "radiator_support", "airbag_module"}

AUSTRIAN_VAT_RATE = 0.20

# Reasonableness bands: expected total by severity, used to flag an outlier estimate.
REASONABLENESS_BANDS = {
    "simple":  {"low": 350.0,  "high": 3_200.0},
    "complex": {"low": 2_800.0, "high": 28_000.0},
}

# Approved customer communication templates.
# --------------------------------------------------------------------------
# Peril taxonomy — which cover a claimed incident needs, per AKKB 2023 Art 1
# --------------------------------------------------------------------------
# AKKB Art 1.1 lists the Teilkasko catalogue: Naturgewalten (Sturm ab 60 km/h, Hochwasser,
# Überschwemmung, Hagel, Schneedruck, Lawinen, Steinschlag, Erdrutsch), Brand und Explosion,
# Diebstahl und Raub, and Haarwild. Art 1.2 makes Vollkasko that same catalogue *plus*
# Unfall — "ein unmittelbar von außen plötzlich mit mechanischer Gewalt einwirkendes
# Ereignis" — plus mut- oder böswillige Handlungen betriebsfremder Personen.
#
# So the taxonomy is not a flat list: a peril belongs to a tier, and Vollkasko inherits
# the tier below it. Keying this off the incident type the platform actually produces is
# the point — an earlier version keyed on values nothing emitted, and silently declined
# storm, flood and vandalism claims on policies that covered them.

# Named perils: insured on Teilkasko, and therefore also on Vollkasko.
NAMED_PERILS: dict[str, str] = {
    "hail": "hail",
    "storm_damage": "storm",
    "flood": "flood",
    "glass_breakage": "glass",
    "theft_attempt": "theft",
    "fire": "fire",
    "wild_game": "wild_game",
}

# Unfall and malicious damage: Vollkasko only (AKKB Art 1.2).
COLLISION_PERILS: dict[str, str] = {
    "parking_collision": "collision",
    "junction_collision": "collision",
    "rear_end_collision": "collision",
    "single_vehicle": "collision",
    "vandalism": "vandalism",
}

PERIL_BY_INCIDENT: dict[str, str] = {**NAMED_PERILS, **COLLISION_PERILS}

# How each peril reads to a person, in both languages the platform speaks.
PERIL_LABELS: dict[str, tuple[str, str]] = {
    "hail":        ("hail", "Hagel"),
    "storm":       ("storm", "Sturm"),
    "flood":       ("flood and high water", "Hochwasser und Überschwemmung"),
    "glass":       ("glass breakage", "Glasbruch"),
    "theft":       ("theft and robbery", "Diebstahl und Raub"),
    "fire":        ("fire and explosion", "Brand und Explosion"),
    "wild_game":   ("collision with wild animals", "Wildschaden"),
    "collision":   ("accidental damage", "Unfallschaden"),
    "vandalism":   ("malicious damage by third parties",
                    "mut- oder böswillige Handlungen betriebsfremder Personen"),
}

# The cover tokens each product responds to at all. A peril outside its own product's
# tier is not "unknown" — it is excluded, and the reason can be stated precisely.
PRODUCT_TIERS: dict[str, tuple[str, ...]] = {
    "Teilkasko": tuple(dict.fromkeys(NAMED_PERILS.values())),
    "Vollkasko": tuple(dict.fromkeys(
        list(NAMED_PERILS.values()) + list(COLLISION_PERILS.values()))),
    "Haftpflicht": ("third_party_liability",),
}


def peril_for(incident_type: str | None) -> str | None:
    """The cover a claimed incident needs, or None where the incident is unclassified."""
    return PERIL_BY_INCIDENT.get((incident_type or "").strip().lower())


def peril_label(peril: str | None, language: str = "en") -> str:
    """The peril as a person would say it."""
    row = PERIL_LABELS.get(peril or "")
    if not row:
        return (peril or "the peril claimed").replace("_", " ")
    return row[1] if language == "de" else row[0]


COMMS_TEMPLATES: dict[str, dict[str, str]] = {
    "claim_approved": {
        "de": "Ihr Schaden {reference} ist geprüft und freigegeben.",
        "en": "Your claim {reference} has been assessed and approved.",
    },
    "claim_in_review": {
        "de": "Ihr Schaden {reference} wird derzeit von einer Sachbearbeiterin geprüft.",
        "en": "Your claim {reference} is currently with a claims handler for review.",
    },
    "more_info_needed": {
        "de": "Für Ihren Schaden {reference} benötigen wir noch eine Angabe.",
        "en": "We need one more detail for your claim {reference}.",
    },
    "below_excess": {
        "de": "Der ermittelte Schaden übersteigt Ihren Selbstbehalt nicht, daher kommt es "
              "zu keiner Zahlung.",
        "en": "The assessed amount does not exceed your excess, so no payment arises.",
    },
    "total_loss": {
        "de": "Ihr Fahrzeug gilt als Totalschaden. Wir rechnen auf Basis des "
              "Wiederbeschaffungswertes abzüglich Restwert und Selbstbehalt ab.",
        "en": "Your vehicle is a total loss. We settle on the replacement value less the "
              "salvage value and your excess.",
    },
    "payment_made": {
        "de": "Die Zahlung zu Ihrem Schaden {reference} wurde angewiesen.",
        "en": "The payment on your claim {reference} has been released.",
    },
    "coverage_declined": {
        "de": "Für Ihren Schaden {reference} besteht nach der Polizze kein Deckungsanspruch.",
        "en": "Your policy does not provide cover for claim {reference}.",
    },
    "injury_safety_first": {
        "de": "Bei Ihrem Schaden {reference} steht Ihre Gesundheit im Vordergrund.",
        "en": "For claim {reference}, your wellbeing comes first.",
    },
    "investigation_opened": {
        "de": "Ihr Schaden {reference} wird zur weiteren Prüfung an ein Fachteam übergeben.",
        "en": "Claim {reference} has been passed to a specialist team for further review.",
    },
}
