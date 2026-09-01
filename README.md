# Agentic Motor Claims Platform

Five roles, one platform, in English or German. Eleven agents on a LangGraph orchestration,
grounded on a governed semantic layer, wrapped in three zero-trust pillars — with an
assistant docked on every screen. A working demonstration of the Allianz Austria target
architecture.

> **Automation recommends. Deterministic services decide. People approve.**
> Nothing a model produces reaches a core system directly.

**Nobody presses "run".** A claim is analysed the moment it is notified, and a file nobody
has worked yet works itself when it is opened. The orchestration, the runtimes and the
frameworks are not in the interface, because none of them are a user's concern.

The policyholders, vehicles, VINs, plates and policy numbers are synthetic and correspond to
no real person. The **policy conditions are not** — the clause corpus and the five policy
schedules in `policy-documents/` are built from the published Austrian standard-form
conditions (AKKB 2023, AKHB 2023, and the VAV AKKB variant), so a coverage answer rests on
wording that actually exists. They remain a demonstration corpus, not any one insurer's
contract.

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

`backend/.env` is gitignored. Without a key the platform still runs end to end: LangGraph
still orchestrates, the tools still execute, the contracts are still validated and the
controls still fire — only the reasoning turn is served deterministically.

---

## Trying it

Sign in as **Policy Holder**. Two things are worth doing first.

**Open a policy.** *My policies* shows the vehicle rather than the policy number, because
that is how a customer knows which policy they mean — what they are covered for with a tick,
what they are not with a cross, and the actual schedule to view or download. Those five PDFs
in `policy-documents/` are generated from the real Austrian conditions, one per policyholder.

**Report a claim.** Three steps: pick the car, say what happened, attach anything you have.
At step two you choose between **answering a few questions** and **filling in a form** —
both routes end at the same intake, and you can switch between them without losing what you
have said. The guided route asks one question at a time, chosen from what is genuinely still
missing; it opens with "what happened?" without consulting a model, because that is the
question everyone gets asked first. Four answers is typical. Then press submit once, and
nothing else: the message says *we are reading your documents* and the analysis is already
running.

### The pack of test documents

Six synthetic documents in **`test-documents/`**, served by the API and loadable in one click
at step three. They are read for real — text extracted,
panels found from the line items, each value scored for confidence — so the claim routes on
what the *files* say rather than on what was typed.

| File | Exercises |
|---|---|
| `01_…_Donaustadt_clean.pdf` | Two panels, €1,442.30 inside the ceiling → straight through |
| `02_Polizeianzeige_….pdf` | Third party at fault → the recovery path |
| `03_repair_quote_alpin_POISONED.pdf` | A hidden `SYSTEM:` block **and** an injury note → both caught |
| `04_…_SKS_Nord_total_loss.pdf` | Four structural panels at 77% of value → total loss |
| `05_photo_bumper_front_clear.jpg` | Quality **0.98** → accepted |
| `06_photo_tailgate_blurred.jpg` | Quality **0.34** → escalated, with a specific re-ask |

Confidence is earned rather than assumed: a plate is short and unverifiable, so each
character OCR routinely confuses costs it confidence — `I-2O4 AH` (letter O, not zero) lands
at **0.78** and is confirmed with the customer instead of promoted. A VIN carries a check
digit a real system would verify, so it is penalised far less. Photo quality is the variance
of the edge response plus exposure and resolution, because a sharp photo taken in the dark is
just as unusable as a soft one.

`test-documents/README.md` has the worked scenarios. **`USER-GUIDE.md`** is the
plain-English guide, one section per role.

---

## Five roles, five small products

Everything used to be shown to everybody. It is not one console with seven tabs any more.
Each role sees one to four views, and switching role changes what the platform will *do*,
not just what it displays.

These are roles, not people. There are no invented staff names anywhere in the platform:
what is being demonstrated is a separation of duties, and attaching a name to it only
invites the question of who that person is. Each role carries a rendered 3D object rather
than initials, because a role is not a person with a monogram.

| | Role | Sees | Authority | Why the role exists |
|---|---|---|---|---|
| 🚗 | **Policy Holder**<br>*Versicherungsnehmer* | My claims · My policies · Report a claim | — | Reports an accident and follows their own claim. Never sees a stage, a queue or a model. |
| 📁 | **Claim Handler**<br>*Sachbearbeiter Kfz-Schaden* | My work · Recovery | €5,000 | Owns the file: cover, settlement within authority, referrals, recovery. |
| 🧰 | **Motor Assessor**<br>*Kfz-Sachverständiger* | Assessments | none | Judges the damage, the repair scope, and whether the vehicle is worth repairing. Holds no settlement authority — the technical call and the money are separated deliberately. |
| 🔍 | **Special Investigations**<br>*Sonderermittlung* | Referrals | none | Works referrals and the relationships behind them. Reports signals; never decides the money. |
| 🛡 | **Compliance & Operations**<br>*Compliance & Betrieb* | Approvals · Operations · Assurance · Assistant usage | €25,000 | Approves what is above handler authority, and reads the platform rather than the claims. |

A role with zero authority is not an oversight. Separating the technical call from the
settlement, and the investigation from the decision, is the control.

**On the escalated approval.** With five roles rather than six, the approval above handler
authority sits with Compliance & Operations, in its Operations capacity. The two halves stay
visible — Operations owns the escalated approval, Compliance owns assurance — and the
authority refusal is unchanged: a handler attempting €30,000 is refused at the gateway
before anything is signed, and the refusal is what the demonstration is for.

---

## English or German, from the top of the screen

The toggle in the header changes the whole platform, not a label set: navigation, every
view, claim statuses, cover and exclusion wording, routing reasons, money (`€ 1.234,56`) and
dates (`28. Feb. 2027`). An Austrian browser opens in German without being asked.

Business terms carry both languages from the API rather than being translated in the
browser — a status is *Bei einem Mitarbeiter*, not a literal rendering of "with a person" —
because those wordings are settled in the trade and a client-side table would drift from
them.

One deliberate boundary: the **narrative each agent writes** stays English. It is generated
once and stored on the file, so it cannot follow a runtime toggle, and English is the
platform's internal working language. Everything the platform itself renders — including
every word a customer ever reads — follows the toggle. Customer letters are always written
in the customer's own language regardless of who is looking.

---

## An assistant, docked on every screen

Every role has one, bottom-right on every view, with sample questions for a standing start.
It is a panel rather than a page because the question you want to ask is almost always about
what is currently on the screen, and sending someone to a separate view to ask it loses the
thing they were looking at.

It is scoped exactly as the role is. Not a chatbot bolted on the side — another agent
identity, governed like one:

- its question goes through the **same inbound firewall** (ask it to ignore its
  instructions and the gateway stops it, exactly as it would a customer);
- it can only reach **its role's tools** — the handler's assistant cannot walk the fraud
  graph, and the investigator's cannot draft a customer note;
- anything it says to a **customer** goes through the same **outbound guard**;
- every exchange is recorded, with the tools it used and what it cost.

What it will not do is act. It reads, explains, prepares and drafts. Approving, sending,
settling and releasing a freeze stay with the person — those are the things the control
plane exists to keep in human hands, and an assistant that could do them would be a hole
in it.

| Coworker | For | Does |
|---|---|---|
| **Claim Assistant** | Policyholder | Where the claim is, in plain language, and exactly what is still needed. |
| **Desk Assistant** | Claim Handler | What the cover says and on which clause, what stopped a claim, whether there is anyone to recover from. Drafts customer notes; does not send them. |
| **Assessor Assistant** | Motor Assessor | Walks an estimate against the approved catalogue, and works the repair-cost-to-value test. |
| **Investigation Assistant** | Special Investigations | Lays out the signals and walks the network. Reports signals, never findings, and will say when a pattern is likely coincidence. |
| **Assurance Assistant** | Compliance & Operations | Prepares an approval — what was proposed, which checks stopped it, what the exposure is — then reports what is enforced, what it stopped, whether anything changed out of band, and what it cost. |

Every staff assistant can also read a claim **in full**: `incident_detail` returns the report
as it came in, what was extracted from each document and how confident each field is, the
reporting delay, and the reasoning every stage left behind. That is the tool a handler uses
to interrogate an automated conclusion rather than accept it.

---

## Fifteen stages, and who owns each

Nobody sees this table in the interface. It is here because it is the architecture; on screen
a role sees only its own work, and the customer sees none of it.

| | Stage | Owner | |
|---|---|---|---|
| 1 | Notify | Policyholder | |
| 2 | Screen | Platform | Pillar 1 |
| 3 | Read the evidence | Platform | Document Understanding |
| 4 | Triage | Claim Handler | Intake Orchestrator |
| 5 | Coverage | Claim Handler | Coverage |
| 6 | Damage assessment | Motor Assessor | Damage Assessment |
| 7 | Repair estimate | Motor Assessor | Pillar 2 · Repair Estimate |
| 8 | **Repairability** | Motor Assessor | **new** — AKKB Art 5.1.1, both limbs (see below) |
| 9 | Risk screening | Special Investigations | Fraud & Risk |
| 10 | Decision | Claim Handler | Decision |
| 11 | Policy guard | Platform | Pillar 1 · ten checks |
| 12 | Human approval | Compliance & Operations | HITL Coordinator |
| 13 | **Settlement** | Claim Handler | **new** — Pillar 3 · the money actually moving |
| 14 | **Recovery** | Claim Handler | **new** — third-party recovery, *Regress* |
| 15 | **Close & learn** | Compliance & Operations | **new** — the file closed, the reason recorded |

---

## The total-loss test, in full

Worth stating because it is the part most easily got wrong, and this build got it wrong
first. **AKKB 2023 Art 5.1.1 sets two rules, and they are different rules.**

> *"…oder die voraussichtlichen Wiederherstellungskosten **zuzüglich der Restwerte** den
> Wiederbeschaffungswert übersteigen. Der Versicherungsnehmer **kann jedoch** die
> Reparaturkosten verlangen, sofern diese voraussichtlich 70 Prozent des
> Wiederbeschaffungswertes nicht übersteigen … **zum Nachweis ist eine Rechnung der
> Fachwerkstätte vorzulegen.**"*

**Rule 1 is the test.** A total loss exists where the vehicle is destroyed or lost, or
where repair cost *plus salvage* exceeds the replacement value — the Wiederbeschaffungs-
aufwand.

**Rule 2 is the policyholder's option.** They may demand the repair cost instead, provided
it is not expected to exceed 70 per cent of the replacement value, that a proper repair at
that figure is genuinely possible, and that a qualified workshop invoice is produced as
proof.

Running rule 2's percentage as though it were rule 1's test inverts it: 70 per cent is the
customer's entitlement threshold to insist on repair, not the insurer's trigger to declare
a write-off. So the platform now reports three outcomes:

| Outcome | When | Indemnity |
|---|---|---|
| `total_loss` · recovery cost exceeds value | repair + salvage > WBW | WBW − salvage − excess |
| `total_loss` · above the repair option | repair > 70% of WBW | WBW − salvage − excess |
| `economically_repairable` | repair ≤ 70% of WBW | repair cost − excess, on an invoice |

Salvage varies with the damage rather than sitting at a constant — an intact drivetrain and
a structurally destroyed shell are not the same fraction of anything — and the provenance
says plainly that it is modelled where a real file uses Restwertbörse bids.

Where the schedule carries **ZB-NEUWERT** and the vehicle is inside the endorsement's
window, the basis is the new price rather than the replacement value.

---

## What was found, and how

The file opens on **What was found** rather than a run console. Each stage shows its
conclusion; the workings sit behind a **?** on the same row, which opens what went in (every
tool called, with its arguments and what came back) and what came out (the typed result).
The split is deliberate — somebody working a file wants the conclusion and needs to be able
to challenge it, but not with a wall of JSON in front of the conclusion.

Next to it is a **★**. It records whether the person who does this job thought the stage got
it right, per claim, per stage, per role. That is not decoration and it is not a like button:
whether the people doing the work trust a given stage is the only honest signal for where
automation is actually earning its place, and a stage marked wrong is a golden case waiting
to be written. A handler and an assessor can disagree on the same stage, and both verdicts
are kept.

---

## How it is orchestrated

**LangGraph owns the orchestration.** The stages are nodes and the exception paths are
conditional edges, which matters for more than tidiness: a claim's route through the
platform is now something you can read, draw and test rather than control flow buried in a
function.

```
START → screen ─(blocked)→ END
          │
        intake → triage ─┬→ coverage ─┐
                         ├→ damage ───┤
                         ├→ estimate ─┤   (estimate also runs repairability)
                         └→ risk ─────┴→ decision → guard
                                                      │
                              ┌───(needs a person)────┴───(clear)───┐
                          approval ──────────────────────────→   settle
                                                                    │
                                              ┌──(third party)──────┴──┐
                                          recovery ──────────────→  comms → close → END
```

The four assessments fan out and the decision waits for all four — as the architecture
draws it. *(A note earned the hard way: LangGraph schedules a fan-in node as soon as any
inbound edge fires, so the repairability stage runs inside the estimate node to keep the
four branches at equal depth. Uneven depth ran the decision twice.)*

**Three runtimes, one set of controls.** Inside an agent node the reasoning turn is served
by whichever runtime the run asked for. Selectable per run, from the workbench:

| Runtime | |
|---|---|
| **Pydantic AI** (default) | The agent's output type is a Pydantic model, so the result is validated before anything downstream sees it — and the model is re-asked when validation fails rather than a malformed answer travelling on. |
| **Google ADK** | The runtime the target architecture names. Same agents, same tools. |
| **Deterministic** | No model at all. Fixed tool trajectory, answer synthesised from the real tool results. |

The controls do not live in any of them. They live in the graph nodes and the tool wrapper,
so **swapping the model out does not swap the controls out** — which is the property worth
demonstrating. The same five claims reach the same decision and the same queue on all three.

**Typed contracts.** Every agent output is a Pydantic model and the model *is* the contract:
strict on what a model produces, so a hallucinated field is an error rather than something
that quietly travels downstream. This is what lets the policy guard be strict — it is never
parsing prose.

**Tracing.** LangSmith when `LANGSMITH_API_KEY` is set; the same spans kept in process when
it is not. Tracing that only works with a SaaS key is not tracing you can rely on in a
regulated environment.

**Several providers, because one quota is one ceiling.** Gemini direct is the first leg. Any other provider a key
is supplied for — OpenRouter, xAI — joins a Pydantic AI `FallbackModel` behind it, in
`PROVIDER_PREFERENCE` order, so a refusal on one **continues** on the next instead of ending
the run. Each provider gets its own sliding-window limiter, because sharing one would
throttle the healthy provider while another is busy, and a refusal is retried after the
delay the provider itself asks for (Gemini puts it in `retryDelay`; OpenRouter puts
`retry_after_seconds` in the error body).

A key in the environment is not the same as a provider you can call. A team without credits,
a model closed to new projects and an expired key all look identical from the config and
completely different from the API — so the chain is composed from providers that **answered a
probe**, not from providers that have a key. The probe runs once at startup, is cached for
ten minutes, and is never fatal: an unprobed provider is kept in, because refusing to try is
worse than trying and falling through. A provider that cannot be called is named in
**Model usage** with the reason and the remedy, and rejoins the chain on its own once the
remedy is applied.

Verified by forcing the Gemini leg at a model the key cannot call: the turn was carried by
`minimax/minimax-m3:free`, which called the tools and returned a valid `CoverageView`.

What OpenRouter is and is not good for here, measured rather than assumed:

| | Gemini direct | OpenRouter free |
|---|---|---|
| Latency, one grounded coverage turn | **1.2 – 8 s** | 31 – 76 s |
| Tool calling **and** a typed output contract | reliable | **2 of 5** free models held up |
| What binds you | your project's quota (15 RPM / 500 RPD) | a pool **shared with every other OpenRouter user** — intermittent upstream 429s |
| Context | 250K TPM | up to 1M |
| Cost | free tier | free (`cost: 0` on every response) |

So OpenRouter is not a faster path, and it is not a drop-in replacement — several free models
advertise `tools` and then fail the schema, and the ones that work are an order of magnitude
slower. What it *is* good for is exactly the thing a single-provider deployment cannot do:
keep going when the first provider says no. That is why it is the fallback leg and not the
default, and why the evaluation suite still runs deterministically — an eval whose expected
values move with model sampling is not an eval. (On OpenRouter the same claim reaches the same
`excluded` position, but returns the clause as
`AKHB Art 8.2 (own-vehicle damage excluded)` rather than the bare `AKHB Art 8.2` the golden case
asserts.)

Set `MODEL_PROVIDER` to `google`, `openrouter` or `fallback` to pin it; `auto` picks `fallback`
whenever both keys are present. `RUN_WALL_CLOCK_SECONDS` defaults to 900 so a run routed
through the slower provider is not killed for working slowly.

---

## Model usage

Because an agentic platform that cannot answer *what did this cost and how much headroom is
left* is not ready for anyone's production. Every call is recorded, and the page reports peak
usage per model against its limit — a ceiling only means something against the peak; an
average hides the minute you were refused.

Cost is split into **metered** (real provider spend) and **modelled** (what the deterministic
provider's token counts *would* have cost), because presenting the second as the first would
be misleading. Each row also names its **route** and what actually binds it — a project quota
you own is a different problem from a pool you share with strangers, and a page that renders
both as "15/20" would hide that.

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

The guard reads **authoritative** values from the tool outputs and the claim record, never
the numbers a model restated — the injury flag, for instance, comes only from the claim
record. PG-10 exists because a model that misreports the figure it is recommending is not a
model to act on.

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
make evals   # 5 golden cases, 36 assertions, replayed through the LangGraph orchestration
```

The evaluations were the regression net for moving orchestration onto LangGraph: 5/5 cases
and 36/36 assertions before the rewrite, and 5/5 and 36/36 after it.

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

**Where the ADK plugin sits.** ADK remains one of the three runtimes, and its zero-trust
plugin is still how an ADK-served agent inherits the controls:


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

### The eleven agents

| | Agent | Tool scope | Cannot |
|---|---|---|---|
| 1 | Intake Orchestrator | `get_claim_360`, `get_claim_timeline`, `get_outstanding_evidence` | change the claim, decide coverage |
| 2 | Document Understanding | `get_extractions` | promote extracted to validated |
| 3 | Coverage | `get_policy_coverage`, `get_endorsements`, `search_policy_wording` | approve, write to the policy system |
| 4 | Damage Assessment | `get_photo_findings`, `lookup_part_price` | price a repair, settle |
| 5 | Repair Estimate | `get_labour_rate`, `calculate_repair_estimate`, `get_reasonableness_band` | invent a price, approve its own figure |
| 6 | Fraud & Risk | `get_risk_signals`, `graph_neighbours` | decline, act on a signal alone |
| 7 | Decision | `assemble_decision_inputs` | write to the claims core, issue a payment |
| 8 | Repairability | `get_vehicle_valuation`, `check_total_loss_threshold`, `search_policy_wording` | settle, move the threshold |
| 10 | Recovery | `get_liability_position`, `assess_recovery` | pursue a recovery itself, waive the excess |
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
    agents/        graph (LangGraph) · providers (3 runtimes) · coworker · the eleven
                   agents · typed tool catalog · throttle · deterministic services
    semantic/      six semantic models, the query API, the clause corpus
    zero_trust/    semantic_gateway · sandbox · crypto_guard · write_gateway · adk_plugin
    services/      preflight · ledger · review · metrics · evals · security_ops
    routers/       platform · claims · workspace · review · security · insights
    services/      …· ingest (pdf + photo) · questionnaire (the guided notification)
    models.py      canonical claim model, plus per-role stage feedback
    lifecycle.py   the fifteen stages, and every status in both languages
    schemas.py     the typed agent contracts
    personas.py    the five roles, their views and their assistants
    claimants.py   six synthetic claimants and the demo scenarios
    seed.py        synthetic data
  tests/           64 zero-trust tests
frontend/
  src/lib/
    i18n.tsx       the EN/DE dictionary, money and date formatting, the enum vocabulary
  src/components/
    Shell.tsx      sidebar · language toggle · role switcher
    Avatar3D.tsx   the five roles as rendered isometric objects
    CoworkerDock.tsx   the assistant, bottom-right on every screen
    StageResults.tsx   what each stage found, the "?" workings and the "★" verdict
  src/views/       my claims · my policies · report a claim · work queue ·
                   operations · claim file · assurance · assistant usage
policy-documents/  five policy schedules, one per policyholder, from the real conditions
test-documents/    six documents that exercise the upload path
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
| `MODEL_MAX_RPM` | `15` | Requests per minute allowed on the Gemini leg |
| `OPENROUTER_API_KEY` | *(empty)* | Set to add OpenRouter as a fallback leg |
| `MODEL_PROVIDER` | `auto` | `google` · `openrouter` · `xai` · `fallback` · `auto` |
| `OPENROUTER_MAX_RPM` | `20` | Requests per minute allowed on the OpenRouter leg |
| `XAI_API_KEY` | *(empty)* | Set to add an xAI Grok leg |
| `XAI_MAX_RPM` | `60` | Requests per minute allowed on the xAI leg |
| `PROVIDER_PREFERENCE` | `google,xai,openrouter` | Order the chain is tried in |
| `RUN_WALL_CLOCK_SECONDS` | `900` | Room for the slower provider |
| `MODEL_RATE_LIMITS` | *(free tier)* | JSON of the quota the project actually holds |
| `LANGSMITH_API_KEY` | *(empty)* | Set to ship traces to LangSmith instead of keeping them in process |
| `CLOUD_KMS_KEY_NAME` | *(empty)* | Set to sign through Cloud KMS instead of HMAC |
