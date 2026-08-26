"""Platform metadata: who the personas are, what the agents are, what the semantic
layer exposes, and the shape of the fifteen-step flow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.definitions import AGENT_SPECS, INSTRUCTIONS, registry_snapshot
from app.agents.harness import harness_status
from app.agents.orchestrator import STEPS
from app.agents.tools import TOOL_RISK_CLASS, TOOL_SCOPE
from app.config import (
    AUTHORITY_LIMITS_EUR,
    CURRENCY,
    DEFAULT_RUN_MODE,
    HYBRID_LIVE_AGENTS,
    MODEL_MAX_RPM,
    REGION,
    SUPPORTED_LANGUAGES,
    TENANT,
    TENANT_NAME,
    THRESHOLDS,
    model_mode,
)
from app.db import get_db
from app.personas import CUSTOMERS, REPAIRERS, SCENARIOS, STAFF
from app.semantic import knowledge, query_api
from app.semantic.definitions import (
    LABOUR_RATES_EUR,
    PANEL_CATALOGUE,
    REASONABLENESS_BANDS,
    SEMANTIC_MODELS,
    STRUCTURAL_PANELS,
)
from app.services.preflight import RECOVERY_RULES, safe_link_check
from app.zero_trust.semantic_gateway import PromptFirewall
from app.zero_trust.write_gateway import ACTION_SCOPES

router = APIRouter(prefix="/api", tags=["platform"])


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "tenant": TENANT,
        "model_mode": model_mode(),
        "default_run_mode": DEFAULT_RUN_MODE,
        "hybrid_live_agents": len(HYBRID_LIVE_AGENTS),
        "agent_count": len(AGENT_SPECS),
    }


@router.get("/platform")
def platform() -> dict[str, Any]:
    return {
        "tenant": {"id": TENANT, "name": TENANT_NAME, "region": REGION,
                   "currency": CURRENCY, "languages": list(SUPPORTED_LANGUAGES),
                   "data_residency": "EU"},
        "harness": harness_status(),
        "reasoning": {
            "default_run_mode": DEFAULT_RUN_MODE,
            "modes": {
                "live": "Every one of the nine agents reasons on Gemini.",
                "hybrid": (
                    "The model reasons where there is judgement to exercise. The itemised "
                    "estimate and the review-task bookkeeping stay deterministic, because "
                    "arithmetic over an approved catalogue has no judgement in it."
                ),
                "deterministic": (
                    "No model in the loop. The ADK runtime, the tools, the plugin controls "
                    "and the event stream are identical — only the reasoning turn changes."
                ),
            },
            "hybrid_live_agents": list(HYBRID_LIVE_AGENTS),
            "max_requests_per_minute": MODEL_MAX_RPM,
        },
        "thresholds": {
            "auto_approval_ceiling_eur": THRESHOLDS.auto_approval_ceiling_eur,
            "complex_damage_auto_approve_allowed": THRESHOLDS.complex_damage_auto_approve_allowed,
            "require_citation_for_policy_answers": THRESHOLDS.require_citation_for_policy_answers,
            "injury_blocks_financial_automation": THRESHOLDS.injury_blocks_financial_automation,
            "max_fraud_score_for_autonomy": THRESHOLDS.max_fraud_score_for_autonomy,
            "min_extraction_confidence": THRESHOLDS.min_extraction_confidence,
            "policy_version": THRESHOLDS.policy_version,
        },
        "authority_limits_eur": AUTHORITY_LIMITS_EUR,
        "steps": STEPS,
        "recovery_rules": RECOVERY_RULES,
        "firewall_rules": [
            {"rule_id": rid, "attack_class": cls, "detail": detail}
            for rid, cls, _pattern, detail in PromptFirewall.RULES
        ],
        "action_scopes": {k: sorted(v) for k, v in ACTION_SCOPES.items()},
    }


@router.get("/agents")
def agents() -> dict[str, Any]:
    return {
        "agents": registry_snapshot(),
        "tool_risk_classes": TOOL_RISK_CLASS,
        "tool_scope": {k: [f.__name__ for f in v] for k, v in TOOL_SCOPE.items()},
        "composition": (
            "SequentialAgent[DocumentUnderstanding → IntakeOrchestrator → "
            "ParallelAgent[Coverage ∥ DamageAssessment ∥ RepairEstimate ∥ FraudRisk] "
            "→ Decision], then HitlCoordinator and CustomerCommunication"
        ),
    }


@router.get("/agents/{key}")
def agent_detail(key: str) -> dict[str, Any]:
    spec = next((s for s in AGENT_SPECS if s.key == key), None)
    if spec is None:
        raise HTTPException(404, f"No agent '{key}'.")
    return {
        **spec.as_dict(),
        "instruction": INSTRUCTIONS[key].strip(),
        "tools": [
            {"name": f.__name__, "risk_class": TOOL_RISK_CLASS.get(f.__name__, "unclassified"),
             "docstring": (f.__doc__ or "").strip()}
            for f in TOOL_SCOPE[key]
        ],
    }


@router.get("/personas")
def personas() -> dict[str, Any]:
    return {
        "customers": [
            {
                "party_id": c["party_id"],
                "name": f"{c['first_name']} {c['last_name']}",
                "city": c["city"], "region": c["region"], "language": c["language"],
                "customer_since": c["customer_since"], "segment": c["segment"],
                "persona_note": c["persona_note"],
                "vehicle": c["vehicle"], "policy": c["policy"],
            }
            for c in CUSTOMERS
        ],
        "staff": STAFF,
        "repairers": REPAIRERS,
        "scenarios": SCENARIOS,
    }


@router.get("/semantic")
def semantic() -> dict[str, Any]:
    return {
        "models": [m.as_dict() for m in SEMANTIC_MODELS.values()],
        "query_catalogue": query_api.QUERY_CATALOGUE,
        "api_version": query_api.API_VERSION,
        "raw_sql_exposed_to_agents": False,
        "knowledge": knowledge.corpus_summary(),
        "reference_data": {
            "labour_rates_eur": LABOUR_RATES_EUR,
            "panel_catalogue": PANEL_CATALOGUE,
            "structural_panels": sorted(STRUCTURAL_PANELS),
            "reasonableness_bands": REASONABLENESS_BANDS,
        },
    }


@router.get("/semantic/clauses")
def clauses() -> dict[str, Any]:
    return {
        "corpus": knowledge.corpus_summary(),
        "clauses": [
            {
                "clause_id": c.clause_id, "document": c.document,
                "document_title": c.document_title, "section": c.section,
                "page": c.page, "products": list(c.products), "title": c.title,
                "text_de": c.text_de, "text_en": c.text_en,
                "effective_from": c.effective_from, "version": c.version,
            }
            for c in knowledge.CORPUS
        ],
    }


class SearchRequest(BaseModel):
    question: str
    product: str | None = None
    language: str = "en"


@router.post("/semantic/search")
def semantic_search(body: SearchRequest) -> dict[str, Any]:
    """Grounded retrieval, exposed so the abstention behaviour can be tried directly."""
    results = knowledge.retrieve(body.question, product=body.product, language=body.language)
    citations = knowledge.citations_for(results, language=body.language)
    return {
        "question": body.question,
        "product_filter": body.product,
        "found": len(citations),
        "citations": citations,
        "abstain": not citations,
        "abstain_reason": (
            "No authoritative clause matched. The agent abstains rather than answering "
            "from general knowledge — the citation rule refuses a material answer with "
            "no citation."
            if not citations else None
        ),
        "provenance": knowledge.corpus_summary(),
    }


class SemanticQueryRequest(BaseModel):
    query_name: str
    args: dict[str, Any] = {}


@router.post("/semantic/query")
def semantic_query(
    body: SemanticQueryRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """The only route to business data. An unknown query name is refused, not guessed."""
    try:
        return query_api.execute(body.query_name, db=db, **body.args)
    except query_api.SemanticQueryError as exc:
        raise HTTPException(400, str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(400, f"Invalid arguments: {exc}") from exc


class LinkRequest(BaseModel):
    url: str


@router.post("/preflight/link")
def preflight_link(body: LinkRequest) -> dict[str, Any]:
    """The safe-fetch guard, exposed so an SSRF attempt can be tried live."""
    result = safe_link_check(body.url)
    return {"url": body.url, **result.as_dict()}


@router.post("/admin/reset")
def reset(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return the platform to a pristine demo state."""
    from app.seed import seed
    from app.zero_trust.write_gateway import gateway

    counts = seed(db, reset=True)
    gateway.__init__()  # clear nonce watermarks, approvals and idempotency keys
    return {"reset": True, "seeded": counts, "model_mode": model_mode()}
