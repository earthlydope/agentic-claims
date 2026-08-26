"""Canonical claim model.

The Silver layer of the medallion platform: canonical claim, party, vehicle and policy,
with extracted values kept separate from validated ones so the difference is always
visible. JSON columns stand in for the BigQuery / Spanner structures in the target
architecture.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Party(Base):
    """A policyholder or third party."""

    __tablename__ = "parties"

    party_id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    date_of_birth = Column(String)
    email = Column(String)
    phone = Column(String)
    address_line = Column(String)
    postcode = Column(String)
    city = Column(String)
    region = Column(String)          # Bundesland
    country = Column(String, default="AT")
    language = Column(String, default="de")
    customer_since = Column(String)
    segment = Column(String)          # retail / fleet / premium
    persona_note = Column(Text)


class Vehicle(Base):
    __tablename__ = "vehicles"

    vin = Column(String, primary_key=True)
    party_id = Column(String, ForeignKey("parties.party_id"))
    plate = Column(String, index=True)
    make = Column(String)
    model = Column(String)
    year = Column(Integer)
    body_type = Column(String)
    market_value_eur = Column(Float)
    mileage_km = Column(Integer)
    drivetrain = Column(String)


class Policy(Base):
    __tablename__ = "policies"

    policy_number = Column(String, primary_key=True)
    party_id = Column(String, ForeignKey("parties.party_id"))
    vin = Column(String, ForeignKey("vehicles.vin"))
    product = Column(String)          # Vollkasko / Teilkasko / Haftpflicht
    product_label_en = Column(String)
    status = Column(String, default="active")   # active / lapsed / cancelled
    inception_date = Column(String)
    renewal_date = Column(String)
    annual_premium_eur = Column(Float)
    excess_eur = Column(Float)        # Selbstbehalt
    covers = Column(JSON, default=list)
    exclusions = Column(JSON, default=list)
    endorsements = Column(JSON, default=list)
    sum_insured_eur = Column(Float)
    no_claims_years = Column(Integer, default=0)
    protected_ncd = Column(Boolean, default=False)


class Claim(Base):
    __tablename__ = "claims"

    reference = Column(String, primary_key=True)
    policy_number = Column(String, ForeignKey("policies.policy_number"))
    party_id = Column(String, ForeignKey("parties.party_id"))
    vin = Column(String, ForeignKey("vehicles.vin"))

    status = Column(String, default="fnol_received")
    stage = Column(String, default="intake")
    channel = Column(String, default="web")
    language = Column(String, default="de")

    fnol_text = Column(Text)
    incident_date = Column(String)
    reported_at = Column(DateTime, default=_utcnow)
    incident_city = Column(String)
    incident_region = Column(String)
    incident_location = Column(String)
    incident_type = Column(String)
    collision_type = Column(String)

    severity = Column(String)                 # simple / complex
    structural_damage = Column(Boolean, default=False)
    injury_reported = Column(Boolean, default=False)
    third_party_involved = Column(Boolean, default=False)
    police_report_ref = Column(String)

    decision = Column(String)
    settlement_amount_eur = Column(Float, default=0.0)
    assigned_to = Column(String)
    assigned_queue = Column(String)
    sla_due_at = Column(DateTime)
    closed_at = Column(DateTime)

    evidence_completeness = Column(Float, default=0.0)
    fraud_score = Column(Float, default=0.0)
    straight_through = Column(Boolean, default=False)
    human_touches = Column(Integer, default=0)

    scenario_key = Column(String)   # links a seeded claim to its demo narrative
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    documents = relationship("Document", back_populates="claim", cascade="all, delete-orphan")
    estimates = relationship("Estimate", back_populates="claim", cascade="all, delete-orphan")
    signals = relationship("RiskSignal", back_populates="claim", cascade="all, delete-orphan")
    tasks = relationship("ReviewTask", back_populates="claim", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="claim", cascade="all, delete-orphan")


class Document(Base):
    """Evidence, held in the Bronze layer with its preflight verdict attached."""

    __tablename__ = "documents"

    doc_id = Column(String, primary_key=True)
    claim_reference = Column(String, ForeignKey("claims.reference"))
    kind = Column(String)              # photo / pdf / link / chat
    filename = Column(String)
    mime_type = Column(String)
    size_bytes = Column(Integer)
    page_count = Column(Integer, default=1)
    sha256 = Column(String)
    source_url = Column(String)

    scan_verdict = Column(String, default="clean")     # clean / malware / blocked
    preflight_notes = Column(JSON, default=list)
    quarantined = Column(Boolean, default=False)
    duplicate_of = Column(String)

    doc_type = Column(String)          # police_report / repair_quote / photo / invoice
    quality_score = Column(Float)
    ocr_text = Column(Text)
    sanitised = Column(Boolean, default=False)
    injection_findings = Column(JSON, default=list)
    detections = Column(JSON, default=list)   # per-photo panel findings + confidence

    uploaded_at = Column(DateTime, default=_utcnow)
    claim = relationship("Claim", back_populates="documents")
    fields = relationship("ExtractedField", back_populates="document", cascade="all, delete-orphan")


class ExtractedField(Base):
    """Document AI output: every field carries its own confidence, and extracted is
    never silently promoted to validated."""

    __tablename__ = "extracted_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String, ForeignKey("documents.doc_id"))
    field_name = Column(String)
    extracted_value = Column(String)
    validated_value = Column(String)
    confidence = Column(Float)
    recovery_action = Column(String)   # accept / confirm / re_ask / escalate
    page = Column(Integer, default=1)
    bounding_ref = Column(String)

    document = relationship("Document", back_populates="fields")


class CoverageAssessment(Base):
    __tablename__ = "coverage_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_reference = Column(String, ForeignKey("claims.reference"))
    status = Column(String)            # covered / covered_with_excess / excluded / lapsed / unknown
    excess_eur = Column(Float, default=0.0)
    reasoning = Column(Text)
    citations = Column(JSON, default=list)
    clauses_applied = Column(JSON, default=list)
    confidence = Column(Float)
    created_at = Column(DateTime, default=_utcnow)


class Estimate(Base):
    __tablename__ = "estimates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_reference = Column(String, ForeignKey("claims.reference"))
    items = Column(JSON, default=list)
    labour_hours = Column(Float, default=0.0)
    labour_rate_eur = Column(Float, default=0.0)
    total_parts = Column(Float, default=0.0)
    total_labour = Column(Float, default=0.0)
    total_tax = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    source = Column(String, default="RepairEstimateAgent")
    sandbox_telemetry = Column(JSON, default=dict)
    reasonableness_band = Column(String)
    created_at = Column(DateTime, default=_utcnow)

    claim = relationship("Claim", back_populates="estimates")


class RiskSignal(Base):
    __tablename__ = "risk_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_reference = Column(String, ForeignKey("claims.reference"))
    signal_type = Column(String)       # duplicate / pattern / graph_proximity / velocity
    detail = Column(Text)
    weight = Column(Float, default=0.0)
    evidence_ref = Column(String)
    created_at = Column(DateTime, default=_utcnow)

    claim = relationship("Claim", back_populates="signals")


class GraphEdge(Base):
    """Spanner Graph stand-in: party, vehicle, device, address and repairer links."""

    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    src_type = Column(String)
    src_id = Column(String)
    edge = Column(String)
    dst_type = Column(String)
    dst_id = Column(String)
    weight = Column(Float, default=1.0)
    flagged = Column(Boolean, default=False)
    note = Column(String)


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    task_id = Column(String, primary_key=True)
    claim_reference = Column(String, ForeignKey("claims.reference"))
    reason = Column(String)
    reason_detail = Column(Text)
    queue = Column(String)             # adjuster / supervisor / siu / coverage / specialist / security
    authority_required = Column(String)
    authority_limit_eur = Column(Float, default=0.0)
    priority = Column(Integer, default=3)
    status = Column(String, default="open")   # open / in_progress / resolved
    assigned_to = Column(String)
    violations = Column(JSON, default=list)
    proposed_decision = Column(String)
    proposed_amount_eur = Column(Float, default=0.0)
    decision = Column(String)
    decision_note = Column(Text)
    approval_ref = Column(String)
    resolved_by = Column(String)
    sla_due_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow)
    resolved_at = Column(DateTime)

    claim = relationship("Claim", back_populates="tasks")


class Message(Base):
    """Customer-facing communication. The outbound guard always applies."""

    __tablename__ = "messages"

    message_id = Column(String, primary_key=True)
    claim_reference = Column(String, ForeignKey("claims.reference"))
    channel = Column(String, default="portal")
    language = Column(String, default="de")
    template_id = Column(String)
    subject = Column(String)
    body = Column(Text)
    tone = Column(String, default="plain")
    status = Column(String, default="drafted")   # drafted / approved / sent / blocked
    guard_findings = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow)

    claim = relationship("Claim", back_populates="messages")


class LedgerEntry(Base):
    """Append-only, hash-chained. In production an append-only BigQuery table with CMEK
    and a retention policy, exported to Cloud Audit Logs and the SIEM."""

    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nonce = Column(Integer, unique=True, index=True, nullable=False)
    tenant = Column(String, nullable=False)
    claim_id = Column(String, index=True)
    run_id = Column(String, index=True)
    step_id = Column(String)
    agent_id = Column(String)
    service_identity = Column(String)
    user_id = Column(String)
    action = Column(String)
    policy_version = Column(String)
    approval_ref = Column(String)
    timestamp = Column(String, nullable=False)
    payload_hash = Column(String, nullable=False)
    prev_hash = Column(String, nullable=False)
    chain_hash = Column(String, nullable=False)
    signature = Column(String, nullable=False)
    signer = Column(String)
    payload = Column(JSON, default=dict)
    verification_status = Column(String, default="VERIFIED_AUTHENTIC")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String, primary_key=True)
    claim_reference = Column(String, index=True)
    status = Column(String, default="running")   # running / completed / failed / stopped
    outcome = Column(String)
    model_mode = Column(String)
    started_at = Column(DateTime, default=_utcnow)
    ended_at = Column(DateTime)
    duration_ms = Column(Float, default=0.0)
    steps_completed = Column(Integer, default=0)
    tool_calls = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_eur = Column(Float, default=0.0)
    budget_stops = Column(JSON, default=list)
    trace = Column(JSON, default=list)
    trigger = Column(String, default="customer")


class ModelCall(Base):
    """One request to a model provider.

    Recorded so the platform can answer the question every FinOps and capacity
    conversation starts with — what did we actually consume, on which model, and how close
    are we to the limit — rather than discovering the limit through failures.
    """

    __tablename__ = "model_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    at = Column(DateTime, default=_utcnow, index=True)
    model = Column(String, index=True)
    provider = Column(String, default="google-gemini")
    runtime = Column(String)              # pydantic-ai | google-adk | deterministic
    agent = Column(String)
    persona = Column(String)
    purpose = Column(String)              # claim_run | coworker | evaluation | drill
    claim_reference = Column(String, index=True)
    run_id = Column(String, index=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_eur = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    throttle_wait_ms = Column(Float, default=0.0)
    outcome = Column(String, default="ok")   # ok | quota | error | validation_retry
    error = Column(String)


class CoworkerTurn(Base):
    """One exchange with a persona's AI coworker."""

    __tablename__ = "coworker_turns"

    turn_id = Column(String, primary_key=True)
    conversation_id = Column(String, index=True)
    persona = Column(String, index=True)
    user_id = Column(String)
    question = Column(Text)
    answer = Column(Text)
    tools_used = Column(JSON, default=list)
    citations = Column(JSON, default=list)
    blocked = Column(Boolean, default=False)
    block_reason = Column(Text)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_eur = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    model = Column(String)
    trace_id = Column(String)
    created_at = Column(DateTime, default=_utcnow)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    event_id = Column(String, primary_key=True)
    claim_reference = Column(String, index=True)
    run_id = Column(String)
    kind = Column(String)              # injection_blocked / ssrf_blocked / tamper_detected …
    severity = Column(String, default="medium")
    surface = Column(String)
    rule_ids = Column(JSON, default=list)
    detail = Column(Text)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)
