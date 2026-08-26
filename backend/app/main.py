"""Agentic Motor Claims Platform — API.

Zero-trust agentic claims for Allianz Austria, built on Google ADK.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, TENANT_NAME, model_mode
from app.db import SessionLocal, init_db
from app.models import Claim
from app.routers import claims, insights, platform, review, security

# ADK logs a full traceback for a model error and then re-raises it. The orchestrator
# catches that error and reports it in words an operator can act on, so the duplicate
# stack traces are noise — silence them and keep the explained failure.
for _noisy in (
    "google_adk", "google.adk", "google_adk.google.adk.models.google_llm",
    "google_adk.google.adk.workflow._node_runner",
    "google_adk.google.adk.runners",
    "google_genai", "google.genai",
):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL)

app = FastAPI(
    title="Agentic Motor Claims Platform",
    description=(
        "Nine Google ADK agents grounded on a governed semantic layer, wrapped in three "
        "zero-trust pillars. Agents recommend, deterministic services decide, people "
        f"approve. {TENANT_NAME} demonstration build."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS + ["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (platform.router, claims.router, review.router, security.router, insights.router):
    app.include_router(r)


@app.on_event("startup")
def startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(Claim).count() == 0:
            from app.seed import seed

            counts = seed(db, reset=False)
            logging.info("Seeded demo data: %s", counts)
    finally:
        db.close()
    logging.info("Agentic Motor Claims Platform ready — model mode: %s", model_mode())


@app.get("/")
def root() -> dict[str, str]:
    return {
        "platform": "Agentic Motor Claims Platform",
        "tenant": TENANT_NAME,
        "model_mode": model_mode(),
        "docs": "/docs",
    }
