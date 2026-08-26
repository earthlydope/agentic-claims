# Agentic Motor Claims Platform

Nine Google ADK agents grounded on a governed semantic layer, wrapped in three zero-trust
pillars. A working demonstration of the Allianz Austria target architecture.

> **Agents recommend. Deterministic services decide. People approve.**
> Nothing an agent produces reaches a core system directly.

Everything in this build is synthetic. The policyholders, vehicles, VINs, plates, policy
numbers and the policy wording itself were written for this demonstration and correspond
to no real person or document.

---

## Running it

```bash
make install     # venv + both dependency sets
./start.sh       # API on :8099, console on :5173
```

Then open <http://localhost:5173>.

To put real Gemini behind the agents, drop a key into `backend/.env`:

```bash
cp backend/.env.example backend/.env
# set GOOGLE_API_KEY=…
```

`backend/.env` is gitignored. Without a key the platform still runs: the ADK runtime, the
tools, the plugin controls, the sessions and the event stream are all real, and only the
reasoning turn is served by a deterministic provider instead of a model.

---

## Three ways to run a claim

Pick the reasoning mode per run, from the control beside the **Run the agents** button.
Every control below the model is identical in all three — that is the point.

| Mode | What reasons on a model | Why you would choose it |
|---|---|---|
| **Hybrid** (default) | 7 of 9 agents | The model reasons where there is judgement. The itemised estimate is arithmetic over an approved catalogue, and creating a review task is bookkeeping — neither has judgement in it, so neither pays for a model. |
| **Live** | All 9 agents | To show the whole loop on a real model. Needs roughly 18 requests per claim, so it needs quota to match. |
| **Deterministic** | None | Fast, free and repeatable. This is the mode the evaluation suite runs in, because an eval whose expected values move with model sampling is not an eval. |

The platform stays inside whatever quota it has been given: `MODEL_MAX_RPM` (default 15,
the free Gemini tier) drives a sliding-window limiter, and a refusal is retried after the
delay the provider itself asks for. If the quota runs out anyway the run stops cleanly,
says so in plain words, and writes nothing partial.

---

## What there is to look at

| Page | What it shows |
|---|---|
| **Overview** | The five measures a claims leader should be able to read on a Monday morning, each computed from claim rows rather than asserted. |
| **File a claim** | The customer journey. The prompt firewall and the evidence preflight both run *before* a claim record exists. Presets let you try an attack, or hide an instruction inside a PDF. |
| **Claims → a claim** | The run console: fifteen steps, streamed live, with every tool call, every control and every signature. Then the evidence, the assessment, the guard, the customer message and the audit trail. |
| **Review queues** | Human authority. Approve, amend, reject or ask for more — through the same signed write path an autonomous decision takes. |
| **Zero trust** | The three pillars, the append-only ledger, the drills, and a 37-case regression suite. |
| **Agents & data** | The nine agents with their tool scopes and their actual instructions; the six semantic models; the clause corpus; a query playground. |
| **Observability** | Traces, tokens, cost per claim, agent topology, and the golden-case evaluations. |

---

## The five personas

Deliberately few. Each one exercises a different path.

| Claim | Policyholder | Cover | What it demonstrates |
|---|---|---|---|
| `AT-2026-004417` | Lena Hofer, Wien | Vollkasko | **Straight through.** Clean evidence, EUR 1,442.30 inside the ceiling. Approved with no human touch, one signed write. |
| `AT-2026-004418` | Markus Berger, Graz | Vollkasko | **Ceiling and severity.** EUR 9,506.64 with a structural A-pillar. PG-01 and PG-02 both fire; a supervisor must approve. An adjuster who tries is refused before anything is signed. |
| `AT-2026-004419` | Sofia Novak, Linz | Haftpflicht | **An honest "not covered".** Liability-only cover, claiming own-vehicle damage. Excluded on `AKB-§7.2`, with the clause quoted to the customer. |
| `AT-2026-004420` | Daniel Weiss, Salzburg | Teilkasko | **Fraud signals.** Third claim in eight months, a phone shared with a party under investigation, all three routed through one flagged repairer. Autonomy frozen, SIU opened — never declined on a signal. |
| `AT-2026-004421` | Amira Haddad, Innsbruck | Vollkasko | **Injury, and a poisoned file.** Neck pain stops financial automation outright. The repair quote PDF carries a hidden `SYSTEM:` block, which is stripped in transit while the file is kept verbatim as evidence. A blurred photo produces one specific re-ask. |

Staff: Klaus Reiter (adjuster, EUR 5,000), Ingrid Mayer (supervisor, EUR 25,000),
Thomas Gruber (SIU, no settlement authority by design), Eva Pichler (compliance, read-only).

---

## The three pillars

### Pillar 1 — Semantic gateway and policy guard
Nothing reaches the model unchecked, and nothing leaves it unchecked.

**Inbound** — eight named attack classes, plus a ninth rule for instruction-shaped markup
smuggled inside retrieved content. A customer attacking the platform is blocked. A *file*
carrying a payload is stripped and quarantined, and the claim keeps moving on the inert
remainder — the difference matters, because a poisoned document should not cost a customer
their claim.

**Outbound** — ten deterministic checks, in versioned code outside the prompt:

| | Check | |
|---|---|---|
| PG-01 | Financial ceiling | An approval above the configured limit is downgraded. |
| PG-02 | Severity coherence | Complex or structural damage can never auto-approve. |
| PG-03 | Arithmetic integrity | Parts + labour + VAT must reconcile to the cent. |
| PG-04 | Coverage certainty | Uncertain, excluded or lapsed coverage goes to a coverage adjuster. |
| PG-05 | Evidence completeness | Missing evidence means request information, never decide. |
| PG-06 | Citation rule | A material policy answer with no authoritative citation is refused. |
| PG-07 | Injury stop | An injury claim reaches a person whatever the agent proposed. |
| PG-08 | Fraud threshold | A score above the threshold freezes autonomous progression. |
| PG-09 | Adverse decision review | A decline is never issued autonomously. |
| PG-10 | Model restatement integrity | A model that misreports a figure it is recommending is caught. |

A violation never simply fails. The decision is downgraded to *Review Required*, the
agent's original recommendation is preserved, and every violation is recorded on the claim
so the adjuster sees exactly why it arrived.

There is also an **outbound guard on customer communication**: internal rule identifiers,
guard reasoning, queue names, investigation status and any figure above the approved
settlement are all withheld. A customer is never told a claim is under investigation.

### Pillar 2 — Managed sandbox and kernel isolation
A tool cannot reach anything it was not given. Typed business tools everywhere; no generic
SQL, no shell, no unrestricted HTTP. Where a calculation genuinely needs generated code it
runs against a scrubbed scope with no environment, no filesystem and no network library,
behind an AST inspector that blocks 29 modules, the dangerous built-ins and the reflection
escapes. Every execution emits proof of its own isolation rather than an assertion of it.

The inspector is a cheap pre-filter. In production the gVisor container profile on Cloud
Run is the actual boundary.

### Pillar 3 — Signed actions and a tamper-evident ledger
Every sensitive action is canonicalised and signed, carrying claim, run and step, agent and
service identity, user and tenant, the action, the policy version, the approval reference,
a monotonic nonce, a timestamp, the payload hash and the previous entry's hash.

Signing is HMAC-SHA256 here so the build is self-contained, written against a provider
interface — swapping in Cloud KMS asymmetric signing through workload identity is
configuration (`CLOUD_KMS_KEY_NAME`), not a rewrite. The private key never enters the agent
container either way.

The **Secure Write Gateway** is the only door into a core system. Six checks per write:
signature, scope, idempotency, approval, nonce, timestamp — in that order, because a retry
after a timeout has to be recognised as already-committed rather than rejected as a replay.

Two auditors read the ledger: a **chain verifier** (nonce order, signature validity, chain
continuity) and a **database integrity auditor** that reconciles live rows against the last
signed entry for each claim and sorts them into verified, tampered and untracked.

---

## Proving it rather than asserting it

```bash
make test    # 64 unit tests over all three pillars
make suite   # 37-case security regression suite (must be 100%)
make evals   # 5 golden cases, 36 assertions, replayed against the live platform
```

Nothing in the evaluations is mocked — each golden case actually runs the claim and asserts
the outcome, the routing, the exact set of policy checks that should have failed,
groundedness, the amount written to the claim, and the tool trajectory.

Two destructive drills live on the **Zero trust → Drills** page and belong in
non-production only:

- **Silent database edit.** A raw `UPDATE` changes an approved settlement, bypassing the
  application entirely. The ledger still verifies — the row was changed, not the ledger —
  and the auditor names the exact field, the signed value and the database value. A
  *Restore from ledger* button rolls it back to its last signed state.
- **Attack replay.** The whole attack library against the gateway in one pass, including
  the legitimate messages that must *not* be blocked.

There are also live playgrounds for the firewall, the sandbox, the outbound comms guard and
the Semantic Query API, so any of it can be tried against your own input.

---

## Architecture

```
Customer / adjuster
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Pillar 1 · prompt firewall  →  agents  →  policy guard              │
└─────────────────────────────────────────────────────────────────────┘
        │                        │                     │
        │              ┌─────────┴──────────┐          │
        │              │  Pillar 2 sandbox  │          │
        │              └────────────────────┘          │
        ▼                                              ▼
Semantic Query API                            Human review
(the only route to                            (scoped approval:
 business data)                                claim · action · limit · expiry)
        │                                              │
        └──────────────────┬───────────────────────────┘
                           ▼
        ┌──────────────────────────────────────────┐
        │ Pillar 3 · sign → Secure Write Gateway   │
        │            → claims core → hash-chained  │
        │            ledger → integrity auditor    │
        └──────────────────────────────────────────┘
```

**ADK composition**, exactly as the code builds it:

```
SequentialAgent[
  DocumentUnderstanding → IntakeOrchestrator
  → ParallelAgent[Coverage ∥ DamageAssessment ∥ RepairEstimate ∥ FraudRisk]
  → Decision
]  then HitlCoordinator, then CustomerCommunication
```

The zero-trust control plane is a single ADK `BasePlugin` installed on the Runner, so every
agent inherits the controls the day it is created:

| ADK callback | Control |
|---|---|
| `on_user_message_callback` | Pillar 1 inbound firewall |
| `before_agent_callback` | Step accounting, budgets, circuit breakers |
| `before_tool_callback` | Tool scope, risk class, per-call provenance |
| `after_tool_callback` | Retrieved-content isolation, context budget |
| `after_model_callback` | Outbound screening, token accounting |
| `after_agent_callback` | Structured output capture |

### The nine agents

| | Agent | Tool scope | Cannot |
|---|---|---|---|
| 1 | Intake Orchestrator | `get_claim_360`, `get_claim_timeline`, `get_outstanding_evidence` | change the claim, decide coverage |
| 2 | Document Understanding | `get_extractions` | promote extracted to validated |
| 3 | Coverage | `get_policy_coverage`, `get_endorsements`, `search_policy_wording` | approve, write to the policy system |
| 4 | Damage Assessment | `get_photo_findings`, `lookup_part_price` | price a repair, settle |
| 5 | Repair Estimate | `get_labour_rate`, `calculate_repair_estimate`, `get_reasonableness_band` | invent a price, approve its own figure |
| 6 | Fraud & Risk | `get_risk_signals`, `graph_neighbours` | decline, act on a signal alone |
| 7 | Decision | `assemble_decision_inputs` | write to the claims core, issue a payment |
| 8 | HITL Coordinator | `create_review_task`, `get_queue_state` | approve for a person, raise its own authority |
| 9 | Customer Communication | `get_template` | send without the outbound guard |

An agent that requests a tool outside its scope is refused at the boundary by the plugin,
not left to its instructions to avoid.

### The governed semantic layer

An agent never sees a table and never writes SQL. Every read is a named query against one
of six semantic models — `sm_claim_360`, `sm_coverage`, `sm_damage_estimate`,
`sm_risk_signals`, `sm_review_queue`, `sm_customer_comms` — and every response carries its
own provenance. An unknown query name is refused, not guessed at.

The claim under work comes from the run context, never from the model's arguments, so an
agent cannot reach a different claim by asking for one.

**Grounding.** Policy wordings are chunked one clause per chunk, filtered by product
*during* retrieval rather than afterwards, and returned with a clause reference, section and
page. An empty result is a real answer: it means the agent abstains. PG-06 makes that
non-optional.

---

## Where this differs from the target architecture

Deliberately, to keep the demonstration self-contained. Each is a configuration boundary
rather than a rewrite.

| Target | Here |
|---|---|
| BigQuery Bronze/Silver/Gold, Spanner, Spanner Graph | SQLite with the same canonical model and a graph edge table |
| Vertex AI embeddings + hybrid vector search | Clause-level lexical retrieval with term expansion, same filtering and same abstention |
| Document AI | Pre-extracted fields carrying real per-field confidences and the same accept / confirm / re-ask / escalate rules |
| Cloud KMS asymmetric signing | HMAC-SHA256 behind a provider interface; set `CLOUD_KMS_KEY_NAME` to switch |
| gVisor on Cloud Run | The same AST inspector and scrubbed scope, with the isolation telemetry the container would emit |
| Append-only BigQuery ledger with CMEK | Append-only table, same envelope and same chain |
| Apigee, Cloud Armor, Model Armor | The gateway's own rate limits, scope checks and rule pack |

What is **not** simplified: the ADK runtime, the agent composition, the tool scoping, the
plugin control plane, all ten policy checks, the signing envelope, the six gateway checks,
both auditors, and the evaluation suite.

---

## Layout

```
backend/
  app/
    agents/        harness, tool catalog, the nine agents, throttle, orchestrator
    semantic/      six semantic models, the query API, the clause corpus
    zero_trust/    semantic_gateway · sandbox · crypto_guard · write_gateway · adk_plugin
    services/      preflight · ledger · review · metrics · evals · security_ops
    routers/       platform · claims · review · security · insights
    models.py      canonical claim model
    personas.py    five customers, four staff, five scenarios
    seed.py        synthetic data
  tests/           64 zero-trust tests
frontend/
  src/views/       overview · file a claim · claims · workbench · review · zero trust · agents · observability
```

## Configuration

Everything a claims leader may tune is configuration, never code. See
`backend/.env.example`; the notable ones:

| Variable | Default | |
|---|---|---|
| `AUTO_APPROVAL_CEILING_EUR` | `2500.00` | The autonomous limit PG-01 enforces |
| `DEFAULT_RUN_MODE` | `hybrid` | What "auto" resolves to |
| `MODEL_MAX_RPM` | `15` | Requests per minute the limiter allows |
| `MODEL_THINKING_BUDGET` | `0` | Bounded so a step cannot quietly take a minute |
| `CLOUD_KMS_KEY_NAME` | *(empty)* | Set to sign through Cloud KMS instead of HMAC |
