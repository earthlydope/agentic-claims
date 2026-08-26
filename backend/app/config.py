"""Platform configuration.

Everything a claims leader is allowed to tune lives here as configuration, never as
code, mirroring the "autonomy thresholds are configuration" rule in the architecture.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Load a local .env without adding a dependency.

    Values already present in the real environment always win, so a deployment can
    override anything the file says. The file itself is gitignored — a live key belongs
    on the machine, not in the repository.
    """
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# --- Tenancy / locale -------------------------------------------------------
TENANT = os.environ.get("TENANT", "allianz-at")
TENANT_NAME = "Allianz Austria"
REGION = os.environ.get("REGION", "europe-west4")  # EU data residency
CURRENCY = "EUR"
SUPPORTED_LANGUAGES = ("de", "en")

# --- Model provider --------------------------------------------------------
# When a Google API key (AI Studio) or Vertex ADC is present the agents run against
# real Gemini. Otherwise the platform falls back to a deterministic scripted model so
# the full ADK runtime — tools, plugins, sessions, event stream — still executes.
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
USE_VERTEX = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")

# Model routing. The platform owns the routing; the project owns the values, because
# which tiers are usable depends on the quota the Google Cloud project actually holds.
# Raise MODEL_CAPABLE to a Pro tier wherever Pro quota exists.
MODEL_FAST = os.environ.get("MODEL_FAST", "gemini-3.1-flash-lite")
MODEL_CAPABLE = os.environ.get("MODEL_CAPABLE", "gemini-3.1-flash-lite")


# Thinking budget for the reasoning turns. Zero keeps latency predictable, which is what
# a claims queue needs; raise it for the harder agents if accuracy matters more than the
# SLA on a given step. None leaves the model's own default in place.
_raw_budget = os.environ.get("MODEL_THINKING_BUDGET", "0").strip()
MODEL_THINKING_BUDGET: int | None = (
    None if _raw_budget.lower() in ("", "none", "default") else int(_raw_budget)
)

# How many times a transient model error is retried before the run fails cleanly. A hung
# run is worse than a failed one — the trace must always come back.
MODEL_RETRY_ATTEMPTS = int(os.environ.get("MODEL_RETRY_ATTEMPTS", "3"))

# Requests per minute the platform will make of the model provider. Set this to the quota
# the project actually holds: the free Gemini tier allows 15, a paid project far more. The
# limiter keeps the platform inside it rather than discovering the limit through failures.
MODEL_MAX_RPM = int(os.environ.get("MODEL_MAX_RPM", "15"))

# What "auto" means. Hybrid is the default because it is the better architecture, not a
# concession: a model earns its place where there is judgement to exercise, and an
# itemised estimate over an approved catalogue has none. Set to "live" to put every agent
# on the model, or "deterministic" to take the model out of the loop entirely.
DEFAULT_RUN_MODE = os.environ.get("DEFAULT_RUN_MODE", "hybrid").strip().lower()

# Which agents reason on a model in hybrid mode. The rest are deterministic because there
# is no judgement in them: an itemised estimate is arithmetic over an approved catalogue,
# and creating a review task is bookkeeping. Paying a model to add up numbers buys nothing
# and spends both quota and latency.
HYBRID_LIVE_AGENTS: tuple[str, ...] = (
    "document_understanding",
    "intake_orchestrator",
    "coverage",
    "damage_assessment",
    "fraud_risk",
    "decision",
    "customer_communication",
)


def live_model_available() -> bool:
    """True when the agents can reach a real Gemini endpoint."""
    return bool(GOOGLE_API_KEY) or bool(USE_VERTEX and GOOGLE_CLOUD_PROJECT)


def model_mode() -> str:
    return "live-gemini" if live_model_available() else "scripted-deterministic"


# --- Autonomy thresholds (Pillar 1 policy guard) ---------------------------
@dataclass
class AutonomyThresholds:
    """Per-product, per-jurisdiction limits. Allianz owns the values; the platform
    owns the enforcement."""

    auto_approval_ceiling_eur: float = float(
        os.environ.get("AUTO_APPROVAL_CEILING_EUR", "2500.00")
    )
    complex_damage_auto_approve_allowed: bool = False
    require_citation_for_policy_answers: bool = True
    injury_blocks_financial_automation: bool = True
    max_fraud_score_for_autonomy: float = 0.55
    arithmetic_tolerance_eur: float = 0.01
    min_extraction_confidence: float = 0.75
    policy_version: str = "AT-MOTOR-2026.08"


THRESHOLDS = AutonomyThresholds()

# --- Human authority matrix ------------------------------------------------
AUTHORITY_LIMITS_EUR = {
    "adjuster": 5_000.0,
    "supervisor": 25_000.0,
    "siu": 0.0,        # investigates, never settles
    "compliance": 0.0,  # read-only governance
}

APPROVAL_TOKEN_TTL_SECONDS = int(os.environ.get("APPROVAL_TOKEN_TTL_SECONDS", "900"))

# --- Pillar 2 sandbox ------------------------------------------------------
SANDBOX_TIMEOUT_SECONDS = float(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "3.0"))
SANDBOX_MAX_MEMORY_MB = int(os.environ.get("SANDBOX_MAX_MEMORY_MB", "128"))
SANDBOX_RUNTIME_ENV = os.environ.get("SANDBOX_RUNTIME_ENV", "gvisor-cloud-run")

SANDBOX_BLOCKED_MODULES: list[str] = [
    "os", "sys", "subprocess", "socket", "urllib", "requests", "httpx", "http",
    "shutil", "importlib", "ctypes", "builtins", "pty", "posix", "nt", "pickle",
    "shelve", "dbm", "multiprocessing", "threading", "asyncio", "pathlib", "io",
    "tempfile", "glob", "webbrowser", "ftplib", "smtplib", "telnetlib",
]

# --- Pillar 3 signing ------------------------------------------------------
ZERO_TRUST_SECRET_KEY = os.environ.get(
    "ZERO_TRUST_SECRET_KEY", "zt-agent-root-secret-key-32bytes-secure-demo-2026"
)
CLOUD_KMS_KEY_NAME = os.environ.get("CLOUD_KMS_KEY_NAME", "")
USE_CLOUD_KMS = bool(CLOUD_KMS_KEY_NAME)

# --- Agent harness budgets -------------------------------------------------
@dataclass
class RunBudgets:
    max_steps: int = 40
    max_tool_calls: int = 60
    max_tokens: int = 250_000
    max_cost_eur: float = 1.50
    max_loops_per_agent: int = 3
    wall_clock_seconds: float = 180.0


BUDGETS = RunBudgets()

# --- FinOps ----------------------------------------------------------------
# Illustrative blended EUR per 1M tokens, used for the cost-per-claim metric.
# Rate card, EUR per million tokens. These are illustrative and configurable — the
# cost-per-claim metric is only as accurate as the card, so replace it with Allianz's
# negotiated rates before anyone quotes the figure.
MODEL_PRICING_EUR_PER_MTOK = {
    "gemini-3.7-flash": {"in": 0.28, "out": 2.30},
    "gemini-3.6-flash": {"in": 0.28, "out": 2.30},
    "gemini-3.5-flash": {"in": 0.26, "out": 2.10},
    "gemini-3.1-flash-lite": {"in": 0.09, "out": 0.36},
    "gemini-3.1-pro-preview": {"in": 1.15, "out": 9.20},
    "gemini-2.5-flash": {"in": 0.28, "out": 2.30},
    "gemini-2.5-pro": {"in": 1.15, "out": 9.20},
    # Scripted mode is priced at the fast-tier rate so the cost-per-claim metric is a
    # meaningful modelled figure rather than a flat zero. Surfaced as basis="modelled".
    "scripted-deterministic": {"in": 0.28, "out": 2.30},
}

COST_BASIS_NOTE = (
    "Live mode meters real Gemini usage. Scripted mode meters the same token counts "
    "priced at the fast-tier card rate, and is reported as a modelled cost."
)

# --- Storage ---------------------------------------------------------------
DB_PATH = os.environ.get("DB_PATH", "claims.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")


@dataclass
class PostureSnapshot:
    """Shape returned by the security posture API."""

    pillars: dict = field(default_factory=dict)
