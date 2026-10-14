# HomeKeep Technical Design Document — Hackathon Release (H)

Version 1.0 | 26 September 2026 | Status: proposed design baseline for technical-lead and QA review

Baseline: HomeKeep BRD v1.0 (24 September 2026), H-scope requirements only. Target event: Build, Ship, Shape: Amazon Developer Hackathon. Alexa+ is the primary track and AWS Builder is the mini challenge.

This TDD describes how to build every requirement the BRD marks for the hackathon release (H) using the smallest set of deployed components that (a) meets the event's eligibility rules and (b) runs the service reliably for at most three concurrent users. It does not design P or F capabilities except where an H decision must stay compatible with them.

## 1 Purpose, scope and design drivers

### 1.1 Requirements in scope

| Class | In this TDD (H) | Out of this TDD (P or F only) |
| --- | --- | --- |
| Business | BR-01 to BR-07 | BR-08 |
| Functional | FR-01 to FR-24, FR-27, FR-28 (FR-19 is Should; designed and built last) | FR-25, FR-26 |
| Non-functional | NFR-01 to NFR-12 | NFR-13, NFR-14, NFR-15 |
| Acceptance | AT-01 to AT-25, AT-29, AT-30, AT-32 to AT-35 | AT-26, AT-27, AT-28, AT-31 |

BRD Section 6 statements that apply to "H and P" are designed here only at their H depth. For example, FR-20 is built as seeded grants plus revocation, and invitations are left to P.

### 1.2 Design drivers

| ID | Driver | Consequence for the design |
| --- | --- | --- |
| DD-1 | Eligibility first | A real, externally reachable MCP server on spec 2025-11-25 over Streamable HTTP, called at runtime by the product itself; AWS services with documented integration |
| DD-2 | Integrity invariants are code, not prompts | Tenant scope, approvals, idempotency, state transitions and confirmation wording are enforced by deterministic server logic; the LLM can only propose |
| DD-3 | At most 3 concurrent users | One always-on application task; no queues, caches, autoscaling or distributed coordination |
| DD-4 | Minimum components | Every deployed component must be needed by an H requirement or an eligibility rule; everything else is listed in Section 3.3 with the reason |
| DD-5 | Channel independence | Domain services and MCP tools assume nothing about the browser; a P Alexa+ adapter replaces the channel only (mitigates BRD R01 / S02) |

### 1.3 Declared H load profile

3 concurrent authenticated sessions, 100 representative turns, Chrome desktop, us-east-1, pinned model. This replaces the BRD Section 10 profile of 10 concurrent sessions for H, and is an input to BRD decision D10. The design has headroom to 10 sessions with a configuration change only (Section 11.3).

### 1.4 BRD open decisions resolved for H

| BRD ID | H decision in this TDD | Status |
| --- | --- | --- |
| D01 | Author an original synthetic manual for a fictional model, "Frostline FL-18i" inverter split AC, plus a second fictional model for conflict tests. It closes the manual-rights risk (R09), and the event rules require submissions to be original work | Proposed; product owner to accept |
| D02 | Chrome desktop (current stable) with the Web Speech API: `SpeechRecognition` in continuous mode with locale `en-IN`, and `speechSynthesis` for output | Proposed; confirm in Spike S-2 |
| D03 | Region us-east-1; Claude Haiku 4.5 via Bedrock Converse using the US geo inference profile; DynamoDB on-demand | Proposed; confirm in Spike S-1 |
| D10 | H load profile per Section 1.3 | Proposed |
| D11 | Public GitHub repository with an OSI licence (Apache-2.0), synthetic fixtures only. Removes collaborator management for six reviewer accounts and keeps the Open Source mini challenge open | Proposed; owner decides |
| D12 | Reminders surface on return only; no proactive delivery | Follows the BRD |

## 2 Hackathon eligibility mapping

Rules checked on 25 September 2026 against the official rules page [S01]. Recheck before submission.

| Rule | Design element that satisfies it | Evidence to include in the submission |
| --- | --- | --- |
| Alexa+ track: working Agent Skill or self-hosted MCP server implementing spec 2025-11-25 or later over Streamable HTTP | Section 5: MCP endpoint `/mcp`, stateless Streamable HTTP, negotiated protocol version `2025-11-25`, OAuth-protected | Contract test log showing the `initialize` handshake with `protocolVersion: 2025-11-25`; MCP Inspector session in the video |
| Runtime technology hook: the track technology must be imported and actually called, not just named in the README | The conversation service calls its own tools **only** through an MCP client over HTTP (Section 4.4); no in-process shortcut | Code path `app/orchestrator/agent.py` → `mcp.client.streamable_http`; correlation trail joining turn → MCP call → domain write |
| Alexa+ simulation alternative | The browser voice client is the simulated Alexa+ experience; it sits on top of the MCP path rather than replacing it | Video shows both |
| AWS Builder: primary-track project that incorporates AWS services with documented integrations | Bedrock, the Strands Agents SDK, DynamoDB, S3, Cognito, ECS Express Mode on Fargate, ECR, CloudWatch Logs, Budgets | Product Feedback answer lists each service and how it is used (Section 11.6) |
| Repository with all source, assets and setup/run instructions | Single repository, IaC, seed and reset scripts, README (Section 11.5) | AT-32 run from a clean AWS account |
| Project functional, demonstrated in a video under 3 minutes | Hosted demo instance plus the resettable judge households (Section 9.2) | YouTube or Vimeo link |
| Available free of charge for testing until the Judging Period ends (20 Nov 2026); credentials supplied if private | Instance stays live through 20 Nov; three judge logins, one per household, in the testing instructions | Budget alert and uptime check (Section 10.4) |
| Third-party material must be authorised | Fictional manual and brand; no real manufacturer content; no copyrighted music in the video | Fixture provenance file `fixtures/PROVENANCE.md` |
| English materials | English-only H client and docs | — |
| Friction log (up to 10% bonus) | `docs/friction-log.md` maintained from day 1 | Pasted into the submission |

## 3 Architecture overview

### 3.1 Component inventory

Everything the product needs at runtime is one container image plus four managed AWS services.

| ID | Component | Technology | Responsibility | Why it cannot be removed |
| --- | --- | --- | --- | --- |
| C1 | HomeKeep application container | Python 3.12, FastAPI/Uvicorn (1 worker, async), ARM64 image in ECR | Serves the static web client; the elder conversation API; staff and admin APIs; the MCP server at `/mcp`; the conversation orchestrator; domain services; the demo provider simulator; the guidance catalog | Single deployable holding all application logic |
| C2 | Hosting | Amazon ECS Express Mode (Fargate service plus shared ALB with AWS-provided HTTPS domain) | TLS termination, always-on task, health checks, logs | Browser microphone access requires HTTPS; the MCP server must be reachable; App Runner is closed to new customers [S06] |
| C3 | Domain store | Amazon DynamoDB, one on-demand table, one GSI, TTL | All persistent records, the approval and idempotency ledger, sessions, the simulator's state | Restart and resume (BR-03, AT-11) and conditional writes for integrity (NFR-05) |
| C4 | Document store | Amazon S3, one private bucket | FR-04 attachments (quarantine then validated) | FR-04 is an H Must |
| C5 | Identity | Amazon Cognito user pool with managed login (OAuth 2.0 authorisation code plus PKCE) | Household and staff sign-in; access tokens for the API and MCP resource | Distinct authenticated test actors (BRD Section 4); OAuth for the MCP endpoint |
| C6 | Model | Amazon Bedrock (Converse API), Claude Haiku 4.5, US inference profile | Utterance interpretation, tool selection, short spoken responses | Conversation processing is "real in H" (BRD 9.5) |
| C7 | Browser client | TypeScript and Vite static bundle served by C1; Web Speech API | Voice and text channel, elder surface, household/history surface, staff console, ops view | The channel; no separate hosting needed |
| C8 | Guardrails for cost and operations | AWS Budgets alert; CloudWatch Logs (ECS default log driver) | Budget alerts; redacted structured logs | NFR-09, NFR-12 |

C8 is configuration only; nothing is built or run for it. The runtime therefore has **one custom deployable (C1) plus C2 to C6**.

### 3.2 Deployment view

```
 Chrome (elder / helper / staff / judge)                 External MCP client (MCP Inspector, P: Alexa+)
        | HTTPS (AWS-provided domain)                              | HTTPS + Bearer (Cognito, scope homekeep/mcp)
        v                                                           v
 +-------------------------- ECS Express Mode: shared ALB (TLS) --------------------------+
                                        |
                                        v
 +------------------------ C1 HomeKeep container (1 task, 1 Uvicorn worker) -------------+
 |  /            static client (C7)                                                        |
 |  /api/*       session + turn API  --> Channel adapter --> deterministic guards          |
 |                                            |                                            |
 |                                            v                                            |
 |                                  Orchestrator (Strands Agent, Bedrock C6)              |
 |                                            | MCP client, Streamable HTTP, loopback      |
 |                                            v                                            |
 |  /mcp         MCP server (2025-11-25, stateless, JSON responses) --> Domain services    |
 |  /api/staff/* staff console API ---------------------------------------> Domain services|
 |  /api/admin/* admin API (catalog status, fault injection, grants, purge) --> Domain     |
 |                                         Domain services --> Demo provider simulator    |
 |                                         Domain services --> Catalog (in image + status) |
 +-----------------------------------------------------------------------------------------+
        |                     |                          |                       |
        v                     v                          v                       v
   DynamoDB (C3)         S3 bucket (C4)           Cognito JWKS (C5)       Bedrock runtime (C6)
```

The orchestrator reaches the MCP server over HTTP on `127.0.0.1` inside the same task. The call is a real Streamable HTTP MCP exchange, which satisfies the runtime-hook rule, but it adds no network hop outside the task.

### 3.3 Components deliberately excluded

| Excluded | Would provide | Why not needed for H |
| --- | --- | --- |
| AgentCore Runtime | Managed MCP/agent hosting | AgentCore does not serve the web client or staff API, so a second host would still be needed. It would add a separate deploy and cold starts. The MCP module is written stateless and AgentCore-compatible (Section 5.1), so it can move there in P or as an optional AWS Builder upgrade (about 1 day) |
| API Gateway, Lambda | Serverless API | C1 serves all routes. Lambda cold starts hurt voice latency, and background reconciliation needs a running process |
| Step Functions | Durable workflow | The booking workflow is a DynamoDB state machine with conditional writes; there are no long-running steps |
| EventBridge Scheduler | Reminder delivery | H reminders surface on return (FR-19, D12); reminders are computed on read |
| SQS / DLQ | Failed-event queue | Failed provider events become `MANUAL` review items in DynamoDB (BRD 9.4 allows a manual-review queue) |
| Bedrock Knowledge Bases / OpenSearch / embeddings | Semantic retrieval | Guidance is filtered by exact verified model plus a symptom category (BR-05). Deterministic lookup is safer, and with no vector index there are no derived indexes to purge (FR-24) |
| Amazon Transcribe / Polly | Server speech | Browser speech meets the H voice gate (D02); fewer components, no audio reaches our servers |
| CloudFront, Route 53, ACM, custom domain | Edge/TLS/domain | The ECS Express Mode AWS-provided domain includes HTTPS [S07] |
| Secrets Manager / SSM | Secret storage | No long-lived secrets exist. The Cognito web client is public (PKCE), AWS access comes from the task IAM role, and the channel-attestation key is generated per process (Section 5.3) |
| Redis/ElastiCache | Session cache | Session checkpoints live in DynamoDB with TTL |
| CloudWatch dashboard, X-Ray | Observability UI | The NFR-09 dashboard is a staff-console Ops page reading DynamoDB (Section 10.3) |
| Real provider webhook endpoint | Provider callbacks | H provider events come from the authenticated staff console through the same event-ingestion path (FR-16) |

### 3.4 Principal flows

**F1 Elder turn:** client final transcript → `POST /api/turns` → authenticate and load membership → turn de-duplication → deterministic guards (commands, hazard lexicon, approval grammar) → if not handled deterministically, run the orchestrator (Bedrock plus MCP tools, at most 12 tool cycles) → output guard → persist session checkpoint → response with speech chunks, display card and state.

**F2 Consequential action:** the LLM calls `prepare_action`. The server stores a pending approval (payload hash, record versions, expiry) and returns a server-authored read-back. The client speaks it verbatim and reports when playback ended. The next user turn is checked by the **channel**, not the LLM, against the approval grammar and timing rules (Section 4.3). If eligible, the channel calls `confirm_action` then `execute_action` through the trusted MCP client. The outcome is spoken from a server template.

**F3 Staff event:** the staff console posts an event (for example `VISIT_COMPLETED`) with event ID and expected version → domain service validates role, assignment and transition → writes the event and state atomically → the issue moves to `AWAITING_CUSTOMER`. The elder's next session surfaces the resolution question.

**F4 External MCP client:** OAuth via Cognito → `/mcp` with Bearer token → customer tools only. Trusted tools refuse without channel attestation, so external clients can prepare actions but not approve them in H.

## 4 Application container design (C1)

### 4.1 Module layout

```
app/
  main.py                 FastAPI app, routers, lifespan (catalog load, reconciliation loop)
  channel/                session + turn API, turn pipeline, deterministic guards, response templates
  orchestrator/           Strands agent factory, system prompt, MCP client wiring, usage metering
  mcp_server/             FastMCP server, tool definitions, auth middleware, attestation check
  domain/                 households, appliances, issues, guidance, service, approvals, reminders,
                          documents, history, audit; state machines; clock
  provider/               adapter interface + demo simulator (fault injection)
  catalog/                loader, publication-status overlay, hazard lexicon, intake definitions
  staff/  admin/          REST routers
  store/                  DynamoDB repository, key builders, conditional/transaction helpers
  security/               JWT verification (Cognito JWKS), membership + grant resolution, redaction
web/                      TypeScript client (elder, household, staff, ops views)
catalog_data/             reviewed JSON catalog + synthetic manual sources (version-controlled)
fixtures/                 seed households, identities, slots, documents, PROVENANCE.md
infra/                    AWS CDK (Python) app
scripts/                  seed, reset, purge, catalog status, eval runner, load test, hk-admin CLI
tests/                    unit, contract, integration, e2e (Playwright), eval set
```

Pinned dependencies (lock file committed): `mcp==1.29.1`. This is the 1.x line, which speaks the 2025-11-25 handshake era; 2.x targets 2026-07-28 [S04][S05]. Also `strands-agents` at a release whose `mcp` constraint admits 1.29.x [S08], plus `fastapi`, `uvicorn`, `boto3`, `pydantic` v2, `PyJWT[crypto]`.

### 4.2 Turn pipeline (channel adapter)

| Stage | Behaviour | Requirements |
| --- | --- | --- |
| T1 Authenticate | Verify the Cognito access token (issuer, `client_id`, `token_use`, expiry, JWKS signature). Resolve household membership and grant flags **from DynamoDB on every request** | NFR-04, FR-20 |
| T2 Consent gate | If no storage consent is recorded, only the consent flow and non-persistent chat are allowed; persistence tools return `CONSENT_REQUIRED` | FR-01 |
| T3 Turn de-duplication | `TURN#{session}#{turn_id}` stores the finished response; a replay of the same `turn_id` returns it unchanged | FR-22, NFR-05 |
| T4 Command guard | Deterministic grammar for stop, cancel, repeat, slower, pause, and "talk to a person" (the last one offers a service request draft) | FR-21, FR-22 |
| T5 Hazard guard | Match against the approved hazard lexicon; on a hit, call `report_warning_sign` through the trusted client and speak the approved escalation text. Routine guidance is then blocked by the safety flag | FR-07 |
| T6 Approval guard | Runs only when the session has a pending approval (Section 4.3) | FR-12 |
| T7 Orchestrate | Strands agent with the customer tool subset; at most 12 model/tool cycles; turn wall-clock budget 20 s | NFR-01, NFR-12 |
| T8 Output guard | Blocks confirmation language unless this turn or current state holds an authoritative `CONFIRMED` or `CANCELLED` result; blocks forbidden-repair terms; substitutes approved guidance wording when a step was offered; enforces "at most 2 sentences, 1 question" by chunking long material | BR-04, NFR-06, FR-08 |
| T9 Persist and respond | Update the session checkpoint (active issue, last committed step, pending approval, last 12 messages); record token usage; return speech chunks, display card, state badges, `correlation_id` | FR-10, NFR-09 |

The browser generates `turn_id` (UUIDv7) once per final utterance, so network retries are idempotent end to end. `correlation_id` is generated at T1 and propagated to MCP calls, domain events and logs.

### 4.3 Deterministic guards

**Approval eligibility.** A turn can approve the pending action only if **all** of these hold:

1. The session has exactly one approval in state `PENDING`, and it is not expired (5 minutes after creation, or at session end, whichever comes first; earlier if the slot offer expires).
2. The server has recorded `readback_completed_at` for that approval. The client reports this when playback of the read-back ends.
3. The turn's `speech_started_at` is after `readback_completed_at`, and the turn arrived while the client state was `LISTENING`, not `SPEAKING`.
4. The whole normalised utterance matches the affirmative grammar (for example "yes", "yes please", "yes, book it", "confirm", "go ahead"). An affirmative inside a longer sentence does not count.
5. The utterance is not an echo: token similarity to the last spoken assistant text is below 0.6.
6. The actor holds the grant needed for that action (booking grant for service actions; owner for consent and sharing).

A negative ("no", "cancel", "stop") cancels the pending approval. Any other utterance leaves it pending, and a later field change supersedes it because the payload hash changes. The text channel applies rules 1, 4 and 6; typed approvals count for H usability but never as a voice pass (FR-21-AC2).

**Hazard lexicon.** Phrases and patterns are stored in `catalog_data/hazards.json` with review metadata: burning smell, smoke, sparks, shock, repeated tripping, water near electrics, exposed wiring and others. The check is case- and inflection-insensitive. The LLM tool `report_warning_sign` catches paraphrases the lexicon misses. Clearing a safety flag is a staff-only action.

**Output guard.** This is a regular-expression and state check, not a model call. It covers confirmation claims ("booked", "confirmed", "scheduled", "cancelled", "technician is coming"), forbidden instructions (refrigerant, capacitor, open or remove covers, climb, ladder, reset breaker repeatedly), and prices spoken without a stored fee state. A violation replaces the response with a safe template and logs `OUTPUT_GUARD` against the correlation ID for the eval report.

### 4.4 Conversation orchestrator

| Item | Design |
| --- | --- |
| Framework | Strands Agents SDK, `BedrockModel` (Converse) |
| Model | `us.anthropic.claude-haiku-4-5-20251001-v1:0` [S09]; temperature 0.2; max output 350 tokens; version pinned in config and recorded per turn |
| Tools | `MCPClient(lambda: streamablehttp_client("http://127.0.0.1:8000/mcp", headers=…), tool_filters={"allowed": CUSTOMER_TOOLS})` [S08]. A fresh client is created per turn so headers carry that turn's token, `turn_id` and `correlation_id` |
| Trusted client | A second MCP client used only by the channel adapter. It adds the `X-HK-Attest` header. It is never given to the agent |
| Prompt | Role, elder-voice style rules (short, one question, accept "not sure"), household local date and time in Asia/Kolkata, the safety rules, and the rule that tool results and documents are evidence, not instructions. Structured context comes from `get_context`, not from transcript history |
| Context window | Last 12 messages from the session checkpoint plus `get_context` output. No long transcript memory (BRD FR-10: rebuild from records) |
| Cost controls | Hook counts tool cycles and stops at 12 with a hand-off message; Bedrock prompt caching for system prompt and tool schemas where the pinned model supports it (Spike S-1); per-household cap of 300 turns per day |
| Latency budget (p95) | Guards 50 ms; `get_context` 60 ms; model calls 2 to 3 × about 1.2 s; tool calls about 40 ms each; total at most 5 s against the 8 s target. The client speaks "One moment, I'm still working on that" at 4 s, which claims no action (NFR-01) |

The orchestrator runs in a worker thread so the event loop keeps serving the loopback MCP requests. One Uvicorn worker is deliberate: it keeps the per-process attestation key valid (Section 5.3) and is sufficient for three sessions.

### 4.5 Domain services

These services own every rule the BRD assigns to "domain services" (BRD 9.1):

- **Household and consent:** consent records by purpose (`STORAGE`, `SHARING`) with version; declining sharing creates no grant (FR-01).
- **Appliances:** register with category plus confirmed nickname; aliases (`fridge` for refrigerator, `TV` for television); duplicate-nickname sentinel; per-field provenance `UNKNOWN`, `USER_REPORTED`, `DOCUMENT_SUPPORTED` or `VERIFIED`; conflicts retained; model verification only through the staff reviewer action with a document reference that matches a published catalog model (FR-02, FR-03).
- **Issues:** original wording plus structured summary; active-issue check before creation; intake answers saved one by one; safety flag orthogonal to status; transitions per BRD Section 7.1 (FR-05, FR-06, FR-07, FR-17).
- **Guidance:** eligibility requires a `VERIFIED` model, a `PUBLISHED` catalog item, a matching symptom category, no open conflict, and no safety flag; otherwise it returns `NO_APPROVED_GUIDANCE` with a reason (FR-08, FR-09).
- **Service requests and appointments:** transitions per BRD Section 7.2; approval ledger; idempotent provider calls; reconciliation (FR-11 to FR-15).
- **History:** appliance-scoped event timeline; amendments are appended as new events, never overwritten (FR-18).
- **Reminders, documents, audit:** Sections 4.8, 4.9 and 10.3.

A `Clock` interface is injected everywhere. `CLOCK_OVERRIDE` is honoured only when `ENV=test` (AT-34: local midnight and "tomorrow").

### 4.6 Demo provider simulator

The simulator implements the full BRD 9.4 adapter contract: check serviceability, list slots, submit, read status, replace appointment, cancel, and events. It is the **only** adapter in the H codebase; there is no live adapter to switch to. The server constant `SIMULATION_MODE = "DEMO"` is stamped on every service request (BRD 7.3).

| Capability | Implementation |
| --- | --- |
| Slot inventory | `PROVIDER#demo / SLOT#…` items with capacity and fee. Taking a slot is a conditional decrement, so two users racing for the last slot yield exactly one success (AT-15) |
| De-duplication | The provider stores requests by operation key, so resubmitting returns the original result (AT-14) |
| Fault injection | Admin-only `PROVIDER#demo / FAULT` item, one-shot or N-shot, scoped to a household: `CONFIRM`, `ACK_ONLY`, `DELAY_THEN_CONFIRM`, `TIMEOUT_AFTER_SUCCESS`, `REJECT`, `UNAVAILABLE`, `FEE_CHANGE`, `REPLACE_FAIL`, `CANCEL_REFUSE`, `CANCEL_TIMEOUT`, `DUPLICATE_EVENT`, `STALE_EVENT`, `NO_SHOW`. Disabled unless `FAULTS_ENABLED=true` |
| Disclosure | Every confirmation template contains "demo" and the sentence "No real technician will visit" (BRD 9.5) |

**Reconciliation** runs in three places: on `get_service_status`, on session start and `get_context`, and in an in-process sweep every 60 s over `SUBMISSION_PENDING`, `CHANGE_PENDING` and `CANCEL_PENDING` items found through the GSI. Every reconciliation write is conditional on the expected version, so overlapping runs during a deploy are harmless.

### 4.7 Guidance catalog

Content lives in `catalog_data/` and is reviewed by pull request; the PR approval is the H review record (FR-23). The image carries the published content. A DynamoDB overlay `CATALOG / STATUS#{item}` lets an admin withdraw an item at runtime without redeploying (AT-24).

| File | Contents |
| --- | --- |
| `models/frostline-fl-18i.v2.json` | Published: steps keyed by symptom category, each with approved speech text, document ID, section locator, evidence excerpt, reviewer, review date |
| `models/frostline-fl-18i.v1.json` | Withdrawn version (AT-24) |
| `models/frostline-fl-24x.a.json`, `.b.json` | Two sources that disagree on error code E4 → conflict → no model-specific step (AT-04) |
| `sources/*.md` | Original synthetic manual text authored for the project, with `PROVENANCE.md` |
| `sources/malicious-manual.md` | Embedded instructions to book and reveal data (AT-10) |
| `hazards.json`, `intake/ac.json`, `generic_prompts.json` | Hazard lexicon and approved responses; AC intake questions; reviewed observation prompts for unknown models and for fridge and TV |

Symptom categories for AC are `NOT_COOLING`, `WEAK_AIRFLOW`, `WATER_LEAK`, `NOISE`, `ERROR_CODE`, `NOT_TURNING_ON`, `REMOTE_ISSUE` and `OTHER`. Fridge and TV get generic observation prompts, then a labelled scope limit and a service draft (AT-33). Steps never require climbing, opening covers or handling refrigerant. Steps that need reach are flagged `helper_only` and are not offered to the elder alone.

Retrieval is a key lookup, not a search. A catalog read failure, or an injected fault, returns `NO_APPROVED_GUIDANCE` with reason `RETRIEVAL_FAILURE` and offers service (AT-09). Retrieved text is returned inside a typed `evidence` field that the prompt labels as untrusted content. Approval and execution tools are unreachable from the agent regardless of what that text says (AT-10).

### 4.8 Documents (FR-04)

1. An authorised actor (helper with edit grant, coordinator, or assigned technician) calls `POST /api/…/documents/presign`. The server checks scope and returns an S3 presigned POST restricted to key `quarantine/{hh}/{doc}`, `content-length-range` up to 10 MB, and the declared content type (PDF, JPEG or PNG).
2. The client uploads directly to S3, then calls `finalize`. The server reads the object's first bytes and verifies the magic number (`%PDF`, `FF D8 FF`, `89 50 4E 47`) and the size, then copies the object to `validated/{hh}/{doc}` and deletes the quarantine copy. The `DOC` record moves from `QUARANTINED` to `VALIDATED`, or to `REJECTED` without touching appliance fields.
3. Only validated documents can be viewed, through a presigned GET that expires after 5 minutes and is issued after a tenant and role check. The agent has no document tool; documents enrich records only through staff review.

Missing attachments never block reporting or drafting (FR-04-AC1). There is no OCR in H.

### 4.9 Reminders (FR-19, Should)

Each `REMINDER` item stores purpose, due date, timezone, source, opt-in flag, status and a dedupe key. `get_context` returns reminders that are due and not yet surfaced, and marks them surfaced in the same conditional write, so a repeated read surfaces each one once. Cancelling by voice goes through `manage_reminder`. The client says once that it cannot speak when the browser is closed. There is no scheduler, so AT-20's "replay scheduler event" step becomes "repeat the surfacing read" (deviation recorded in Section 12.3).

### 4.10 Staff and admin surfaces

| Route group | Roles (Cognito group) | Functions |
| --- | --- | --- |
| `/api/staff/queue`, `/cases/{sr}` | `coordinator` (all assigned cases), `technician` (own assignments) | Queue with issue summary, checks performed, warning flag, draft/pending/confirmed state, appointment, fee state; pending-reconciliation highlighted; demo badge throughout; personal fields masked unless the role needs them (BRD 11.3) |
| `/api/staff/cases/{sr}/events` | technician, coordinator | `VISIT_STARTED`, `WORK_NOTE`, `VISIT_COMPLETED`, `NO_SHOW`, provider confirm/reject events. Requires `event_id` (de-duplication) and `expected_version`; older events never regress state (FR-16, AT-18, AT-35) |
| `/api/staff/appliances/{id}/verify-model` | `catalog_reviewer` | Sets model `VERIFIED` with document reference and reviewer; a mismatch creates a visible conflict (FR-03) |
| `/api/staff/issues/{id}/clear-safety` | coordinator | Reviewed clearance with evidence (BRD 7.1) |
| `/api/staff/ops` | coordinator, admin | Ops view (Section 10.3) |
| `/api/admin/*` and the `hk-admin` CLI | `admin` | Catalog status overlay, fault injection, grant seeding and revocation, test-household purge and correction, demo reset. All calls are audited (BRD 11.4) |

## 5 MCP server design

### 5.1 Transport and protocol

| Item | Design |
| --- | --- |
| Endpoint | `POST /mcp` on the public HTTPS domain and on `127.0.0.1:8000` inside the task |
| Transport | Streamable HTTP, **stateless mode with JSON responses** (`FastMCP(stateless_http=True, json_response=True)`): no session affinity, no server-initiated streams, safe behind the ALB |
| Protocol | Negotiates `2025-11-25` through the `initialize` handshake; clients send `MCP-Protocol-Version` on subsequent requests. The contract test pins the client to the handshake era and asserts the negotiated version |
| SDK | `mcp==1.29.1`, the 1.x line in maintenance mode. Migration to 2.x and spec 2026-07-28 is a P item once the event confirms later versions [S01][S05] |
| Origin check | Requests with an `Origin` header outside the allowlist are rejected, as the spec requires against DNS rebinding |
| AgentCore compatibility | Stateless, container-packaged and JWT-authorised, so the same module can be hosted on AgentCore Runtime later without code changes to tools [S10] |

### 5.2 Authorisation

- The server acts as an OAuth resource server and serves Protected Resource Metadata at `/.well-known/oauth-protected-resource` naming the Cognito issuer as authorisation server. Unauthenticated calls get `401` with `WWW-Authenticate: Bearer resource_metadata="…"`.
- A Cognito resource server `homekeep` defines scopes `homekeep/mcp` and `homekeep/api`. Access tokens must carry `homekeep/mcp` and come from an allowed app client.
- **Tenant scope comes from the token subject → membership lookup only.** No tool accepts a household ID argument (BRD 7.3).
- Cognito does not offer dynamic client registration. External MCP clients use the pre-registered public client `mcp-inspector` (PKCE, localhost callback), documented in the README.

### 5.3 Per-call context headers

| Header | Set by | Purpose |
| --- | --- | --- |
| `Authorization: Bearer` | Both MCP clients (the user's own access token) | Actor and tenant |
| `X-HK-Turn-Id`, `X-HK-Session-Id` | Channel | Operation-key derivation and approval binding |
| `X-Correlation-Id` | Channel | Audit trail (FR-28) |
| `X-HK-Attest` | Trusted client only | HMAC-SHA256 over `sub, session, turn, timestamp`. The key is generated at process start and never leaves memory. Required by trusted tools, which reject a missing or stale value (older than 30 s) with `AUTH_DENIED` |

A per-process key is safe here because the channel and the MCP server run in the same process: the loopback call cannot land on another task. During a rolling deploy an in-flight turn may fail attestation. The client then retries with the same `turn_id`, and de-duplication makes the retry safe.

### 5.4 Tool catalogue

Mutating tools take `expected_version` where a record exists and return `correlation_id`, `version` and either `data` or a typed `error`.

| Tool | Visible to | Key inputs (beyond auth context) | Returns | FR |
| --- | --- | --- | --- | --- |
| `get_context` | agent | — | Consent state, appliances, open issues, active requests (reconciled), pending approval, due reminders, household local time | FR-10, FR-19 |
| `register_appliance` | agent | category, nickname, room?, brand?, model_claim? | Appliance with provenance; model claim stored as `USER_REPORTED` | FR-02 |
| `resolve_appliance` | agent | reference text, room? | 0, 1 or many scoped matches | FR-03 |
| `update_appliance_fact` | agent | appliance_id, field, value or `UNKNOWN`, expected_version | Updated field and provenance; invalidates incompatible pending guidance | FR-03 |
| `report_issue` | agent | appliance_id, symptom_text, symptom_category, continue_issue_id?, confirmed_distinct? | Issue plus related active issues; requires a choice if an active issue exists | FR-05 |
| `get_issue` | agent | issue_id | Issue, observations, steps, request state | FR-10 |
| `record_observation` | agent | issue_id, field (from intake), value or `UNKNOWN`, expected_version | Saved fact | FR-06 |
| `report_warning_sign` | agent, trusted | issue_id?, sign or text | Approved escalation text; safety flag set | FR-07 |
| `get_guidance` | agent | issue_id | Next approved step with evidence and locator, or `NO_APPROVED_GUIDANCE` with reason | FR-08 |
| `record_step_result` | agent | issue_id, step_id, result | Saved outcome; never resolves the issue | FR-09 |
| `draft_service_request` | agent | issue_id, preferred window?, address/contact confirmations? | Draft plus missing fields; coverage and fee spoken as unknown when unknown | FR-11, FR-27 |
| `list_slots` | agent | request_id, date range | Slots with offer expiry; no reservation | FR-13 |
| `prepare_action` | agent | kind (`SUBMIT`, `RESCHEDULE`, `CANCEL`, `CONSENT_STORAGE`, `CONSENT_SHARING`), request_id?, slot_id? | Pending reference plus server-authored read-back (provider, full date, window, fee state, data shared, demo status) | FR-01, FR-12, FR-14 |
| `get_service_status` | agent | request_id or issue_id | Authoritative state, local date and window, last-update time, reconciliation outcome | FR-15 |
| `confirm_resolution` | agent | issue_id, answer (`RESOLVED`, `PERSISTS`, `UNSURE`), close? | Issue state; closure only on explicit request | FR-17 |
| `get_history` | agent | appliance_id | Chronological, attributed timeline and spoken summary | FR-18 |
| `manage_reminder` | agent | action, purpose, due date, opt_in | Reminder state | FR-19 |
| `confirm_action` | **trusted** | pending_ref | Server-issued approval, or refusal with reason (`APPROVAL_EXPIRED`, `RECORD_CONFLICT`, …) | FR-12 |
| `execute_action` | **trusted** | approval_id | Provider result state: pending, confirmed, requested, rejected or failed | FR-13, FR-14, FR-01 |
| `cancel_pending_action` | **trusted** | pending_ref | Cancelled approval | FR-21, FR-22 |

### 5.5 Errors and idempotency

**Typed errors** follow BRD 9.4: `AUTH_DENIED`, `INVALID_INPUT`, `RECORD_CONFLICT`, `APPROVAL_EXPIRED`, `NO_APPROVED_GUIDANCE`, `SLOT_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`, `RESULT_UNKNOWN`, plus `CONSENT_REQUIRED`. Each error carries a customer-safe message and a support reference, which is the correlation ID. Stack traces and identifiers from another tenant never leave the server (FR-28-AC2).

**Operation key:**

- For agent-visible mutations: `sha256(household | turn_id | tool | canonical_json(args))`, derived server-side.
- For `execute_action`: `sha256(approval_id | "execute")`. An approval can therefore be executed once, whatever the transport retries.

The key and payload hash are stored in `OP#{key}`. The same key with a different payload returns `RECORD_CONFLICT` (BRD 7.3).

## 6 Data design

### 6.1 DynamoDB table `homekeep` (PK, SK; on-demand; TTL attribute `ttl`)

| Item | PK | SK | Notes |
| --- | --- | --- | --- |
| Household | `HH#{hh}` | `META` | Locale, timezone (default Asia/Kolkata), address and contact snapshot (synthetic), `resettable`, version |
| Membership | `HH#{hh}` | `MEMBER#{sub}` | Role, grant flags `view`, `edit`, `book`, `updates`; status; consent version |
| Membership lookup | `USER#{sub}` | `HH#{hh}` | Resolves the token subject to a household |
| Consent | `HH#{hh}` | `CONSENT#{purpose}#{ts}` | Decision, version, actor |
| Appliance | `HH#{hh}` | `APPL#{id}` | Category, nickname, aliases, room, per-field `{value, status, provenance, evidence}`, conflicts, version |
| Nickname sentinel | `HH#{hh}` | `NICK#{normalised}` | Written in the same transaction as the appliance to prevent silent duplicates |
| Issue | `HH#{hh}` | `ISSUE#{id}` | Appliance, original wording, summary, status, safety flag, onset, version |
| Observation / step | `HH#{hh}` | `ISSUE#{id}#OBS#{field}` / `ISSUE#{id}#STEP#{ts}#{step}` | Values with provenance; step outcomes with catalog version |
| Service request | `HH#{hh}` | `SR#{id}` | State, mode `DEMO`, snapshot, fee (integer paise, INR, `ESTIMATE`/`FINAL`/`UNKNOWN`), provider reference, operation key, version; GSI keys when pending or assigned |
| Appointment | `HH#{hh}` | `SR#{id}#APPT#{id}` | `PROPOSED`, `CONFIRMED`, `SUPERSEDED`, `COMPLETED` or `CANCELLED`; times stored in UTC |
| Active-appointment sentinel | `HH#{hh}` | `SR#{id}#ACTIVE` | Holds the single confirmed appointment ID; changed only inside transactions |
| Work report | `HH#{hh}` | `SR#{id}#WORK#{id}` | Actor, summary, time, optional document references |
| Approval | `HH#{hh}` | `APPROVAL#{id}` | Kind, payload hash, record versions, actor, session, `readback_completed_at`, `expires_at`, state; TTL 1 day |
| Operation | `HH#{hh}` | `OP#{key}` | Payload hash, status, result; TTL 14 days (at least the 7 the BRD requires) |
| Event (history and audit) | `HH#{hh}` | `EVT#{appliance or -}#{ts}#{id}` | Correlation ID, actor, role, action, result, prior/new version, provenance label |
| Document | `HH#{hh}` | `DOC#{id}` | Type, S3 key, validation status, links, reviewer |
| Reminder | `HH#{hh}` | `REM#{id}` | Section 4.9 |
| Session checkpoint | `HH#{hh}` | `SESSION#{id}` | Active issue, last committed step, pending approval ID, last 12 messages; TTL 24 h |
| Turn record | `HH#{hh}` | `TURN#{session}#{turn}` | Stored response for replay; TTL 24 h |
| Provider state | `PROVIDER#demo` | `SLOT#…`, `REQ#{op}`, `FAULT` | Simulator (Section 4.6) |
| Catalog overlay | `CATALOG` | `STATUS#{item}` | `PUBLISHED` or `WITHDRAWN`, reason, admin, time |
| Manual review | `OPS` | `MANUAL#{ts}#{id}` | Failed or unmatched events with support reference |
| Usage | `USAGE#{yyyy-mm-dd}` | `TURN#{id}` | Input, output and cache tokens, model, household; TTL 60 days |

**GSI1** is overloaded with `GSI1PK`/`GSI1SK`. `ASSIGNEE#{sub}` / `{state}#{updated}` gives the staff queue, and the sparse `PENDING` / `{updated}` gives the reconciliation sweep and the Ops view. One index serves both.

### 6.2 Integrity mechanics

- **Optimistic concurrency.** Every mutable item carries `version`. Writes use `ConditionExpression version = :expected`, and a failure maps to `RECORD_CONFLICT` (NFR-05: no lost updates).
- **Atomic outcomes.** Booking confirmation is one `TransactWriteItems`: the SR state change, the appointment, the active sentinel, the issue `SERVICE_PENDING` transition, the `OP` result and the event. Reschedule success supersedes the old appointment and activates the new one in one transaction. Failure writes only a failure event, so the original stays active (FR-14, AT-16).
- **Acknowledge after commit.** Tools return success only after the write returns (NFR-08).
- **Purge (FR-24).** `hk-admin purge --household` deletes all `HH#{hh}` items, `USER#` lookups and S3 prefixes, and disables the household's Cognito users with global sign-out. There are no derived indexes or caches to clear. The purge writes an `OPS` audit item without personal data.

### 6.3 S3 bucket

The bucket is private with Block Public Access, SSE-S3 encryption, a TLS-only bucket policy, and CORS limited to the app domain for presigned POST. Prefixes are `quarantine/` (lifecycle expiry 1 day) and `validated/`. There are no public URLs.

## 7 State machines

The transition tables in BRD Sections 7.1 and 7.2 are implemented as explicit maps `from_state × event → (to_state, guard)` in `domain/state.py`. Undefined transitions raise `INVALID_INPUT` and are never silently ignored. The guards the BRD names are implemented as follows:

| Guard | Implementation |
| --- | --- |
| Technician completion cannot close an issue | Only `confirm_resolution` with a customer answer moves an issue to `RESOLVED`; `VISIT_COMPLETED` moves it to `AWAITING_CUSTOMER` |
| `SERVICE_PENDING` → `SERVICE_NEEDED` on rejection or cancellation only if no other active confirmed booking exists | Checked inside the same transaction via the active sentinel |
| Timeout alone is not failure | A provider timeout leaves `SUBMISSION_PENDING` with `RESULT_UNKNOWN` until reconciliation |
| Cancel or change while pending | Queued as a `MANUAL` item for fresh review, never executed concurrently |
| Safety flag restricts guidance even when an appointment is pending | Checked in the guidance eligibility function, independent of status |
| No-show | `NO_SHOW` creates a coordinator exception; the request stays `CONFIRMED` and the issue stays unresolved (AT-35) |

## 8 Voice client design (C7)

### 8.1 Supported environment

Chrome desktop, current stable version, with a headset for demo and test runs. The client uses `SpeechRecognition` with `continuous = true`, `interimResults = true` and `lang = "en-IN"`; it restarts automatically on `end` while in listening states. Output uses `speechSynthesis`, preferring an en-IN voice, with text split into sentences so long utterances don't cut off. Chrome's recognition service processes audio on Google's servers. HomeKeep stores no audio, and this third-party processing is documented in the README privacy note as BRD 8.3 requires. Real-user testing needs the D07 assessment first.

### 8.2 Client states

`IDLE → LISTENING → PROCESSING → SPEAKING → LISTENING`, plus `PAUSED` and `DISCONNECTED`. State is shown by a large label and colour and announced through an ARIA live region. The microphone control, stop control, text input and transcript are always present (BRD 11.1).

### 8.3 Recovery rules (BRD Section 5.5)

| Situation | Client behaviour | Server behaviour |
| --- | --- | --- |
| Silence | Reprompt once at 15 s; after 20 s more, enter `PAUSED` and say progress is saved | Nothing submitted; checkpoint already committed |
| Stop during speech | Interim result matching the stop grammar → `speechSynthesis.cancel()` within 1 s; `POST /sessions/{id}/stop` | `cancel_pending_action`; prior committed state kept |
| Repeat / slower | Replays the last assistant text; slower sets rate 0.8 for the session | No state change |
| Correction ("Saturday… no, Sunday") | — | Model updates the draft; the new `prepare_action` payload hash supersedes the old approval; read-back uses the explicit date |
| Two failed recognitions of a critical field | Offers pause or text input (H) | Field stays unset |
| Microphone denied | Explains why the microphone is needed and switches to text; the voice test is recorded as blocked | — |
| Connection loss | `DISCONNECTED`; says "I lost the connection; I'll check what was saved" and never claims the write | On reconnect: `GET /sessions/{id}/state`, then retries the unsent turn with the same `turn_id` |
| Unsupported language / unintelligible | States the supported language; never treats it as confirmation | — |
| Slow response | At 4 s says "One moment, I'm still working on that" | — |

### 8.4 Echo and barge-in

Recognition keeps running during `SPEAKING` so the user can interrupt, but only the command grammar (stop, repeat, slower) is acted on, and only if the utterance is not similar to the text being spoken. All other transcripts heard during `SPEAKING` are discarded. Approvals are never accepted in that state (Section 4.3, rule 3). When the user mutes, recognition stops and no audio is captured (FR-21-AC2).

### 8.5 Accessibility

All controls work from the keyboard: Space toggles the microphone, Esc stops, Enter sends text, and R repeats. Controls have programmatic labels and visible focus. The layout is checked at 200% zoom, and `axe-core` runs in the Playwright suite (NFR-03). Nothing in the core journey needs QR codes, receipts or visual cards; cards only mirror what is spoken.

### 8.6 Views

- **Elder conversation:** BRD 11.1.
- **Household and history:** appliances, confidence labels ("not provided" rather than errors), open issues, documents, timeline with actor and time (BRD 11.2).
- **Staff console:** Section 4.10.
- **Ops:** Section 10.3.

Every view has a persistent "DEMO — simulated service desk" badge.

## 9 Identity and access

### 9.1 Cognito configuration

- A user pool with managed login domain.
- **`web` public client:** PKCE, scopes `openid homekeep/api homekeep/mcp`, callback to the app domain. The access token lasts 60 minutes and the refresh token 1 day. The refresh token is kept in `sessionStorage`, so a reload resumes the session without assisted login (acceptable for synthetic H data; P moves to an HttpOnly-cookie back end).
- **`mcp-inspector` public client:** PKCE, localhost callback, scope `homekeep/mcp`.
- **Groups:** `coordinator`, `technician`, `catalog_reviewer`, `admin`.
- Household roles and grants live in DynamoDB, not in token claims, so revocation takes effect on the next request (FR-20-AC2). Revocation also calls `AdminUserGlobalSignOut` for the helper.

### 9.2 Seeded identities and households

| Household or role | Identities | Use |
| --- | --- | --- |
| Household A (two ACs, fridge, TV) | owner/elder, view-only helper, booking helper, revoked helper | QA fixtures per BRD 12.1 |
| Household B | owner | Cross-tenant denial tests |
| Staff | assigned technician, unassigned technician, coordinator, catalog reviewer, admin | FR-16, FR-03, FR-23 |
| Judge households J1, J2, J3 (`resettable`) | one owner login each, plus a shared coordinator and a technician login | One household per concurrent judge, matching the three-user assumption; "Reset my demo data" restores the seed |

`scripts/seed.py` creates the Cognito users (with temporary passwords set through the admin API) and the DynamoDB fixtures in one run. It is idempotent.

### 9.3 Authorisation enforcement

Every domain entry point calls `authorize(actor, action, resource)`. The rules implement the BRD Section 4 matrix and the grant flags. A household session is treated as household identity, not proof of which person is speaking (BRD 4, D06). No route performs a UI role switch.

## 10 Cross-cutting non-functional design

### 10.1 NFR realisation

| NFR | Design | Verification |
| --- | --- | --- |
| NFR-01 performance | Latency budget in Section 4.4; 4 s progress phrase; single hop to Bedrock; prompt caching | AT-29 load script with 3 concurrent sessions and 100 turns; p95 reported |
| NFR-02 interaction control | Client-side cancel at interim "stop"; state committed per turn | AT-22, AT-23; stop latency measured with a timestamped log |
| NFR-03 accessibility | Section 8.5 | AT-30 (axe, keyboard, zoom) and AT-22 |
| NFR-04 authorisation | Token → membership lookup; no tenant argument; grants read on every call | AT-02, AT-18, AT-21, AT-25; cross-tenant contract suite |
| NFR-05 action integrity | Operation keys, conditional writes, transactions, provider de-duplication | AT-06, AT-14, AT-15; 100-repeat timeout-injected script |
| NFR-06 evidence and safety | Deterministic eligibility; hazard and output guards; approved speech text | Eval set (Section 12.2) with zero tolerance for violations |
| NFR-07 privacy | No audio stored; transcripts only in 24 h session TTL; log redaction allowlist; 5-minute presigned GET | Log sampling in AT-30; document tests AT-05 |
| NFR-08 reliability | Persist before acknowledge; reconciliation; ECS restarts the task | AT-11 (stop the task through ECS, reload the client) |
| NFR-09 observability | Correlation ID on every mutation event; Ops page | AT-14 trace; Ops page screenshot |
| NFR-10 reproducibility | CDK plus seed; versions pinned; migrations are not needed for DynamoDB but schema version is recorded on items | AT-32 |
| NFR-11 secure transport | TLS at ALB; least-privilege task role; no secrets in repo; encryption at rest | `gitleaks` and `pip-audit` in CI; IAM policy review |
| NFR-12 cost control | Budgets alerts; 12-cycle cap; daily turn cap; max tokens | Alert configuration evidence; cap unit test |

### 10.2 Logging and redaction

Logs are structured JSON with an allowlist of fields: `correlation_id`, actor `sub` hash, role, action, result, error code, latency, token counts, model ID. Transcripts, addresses, documents and tokens are never logged. Log retention is 30 days.

### 10.3 Ops page (NFR-09 dashboard)

Reads DynamoDB only. It shows:

- pending operations by state and age (GSI1 `PENDING`);
- manual-review items;
- error events in the last 24 h by code;
- output-guard hits;
- turns per day with p50 and p95 latency;
- Bedrock token usage with a cost estimate from a configured price table, which is labelled as an estimate.

### 10.4 Cost and availability guardrails

- AWS Budgets monthly budget of USD 75, alerting at 50%, 80% and 100% to the owner's email.
- A free external uptime check on `/healthz` every 5 minutes through 20 November 2026.
- Credit request submitted in week 1; the form closes 21 October, 12:00 PT [S01].

## 11 Infrastructure and deployment

### 11.1 Infrastructure as code

One AWS CDK (Python) app with a single stack `HomeKeep-{env}` defines:

- the DynamoDB table and GSI;
- the S3 bucket;
- the Cognito pool, clients, resource server and groups;
- the ECR repository;
- the task execution and task roles;
- the ECS Express Mode service, defined through its CloudFormation resource with an L1 construct (the resource type name is confirmed in Spike S-1);
- log group retention;
- the Budgets alarm.

Environments are `test` (CI and QA, with faults and clock override enabled) and `demo` (judges; faults admin-only, no clock override).

### 11.2 Task IAM role (least privilege)

- `dynamodb:GetItem/PutItem/UpdateItem/DeleteItem/Query/TransactWriteItems/BatchWriteItem` on the table and its index
- `s3:GetObject/PutObject/DeleteObject` on the bucket prefixes
- `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the pinned inference profile and its underlying foundation-model ARNs
- `cognito-idp:AdminUserGlobalSignOut` on the pool, used for helper revocation

There are no wildcard resources.

### 11.3 Sizing

| Resource | H setting | Rationale |
| --- | --- | --- |
| Fargate task | 0.5 vCPU, 1 GB, ARM64; minimum 1 and maximum 1 task | The workload is I/O-bound and 3 sessions need one worker. A fixed single task avoids cross-task attestation or cache questions. If AT-29 misses p95, raise to 1 vCPU / 2 GB by configuration |
| Uvicorn | 1 worker, async, thread pool of 16 | Blocking boto3 and Bedrock calls run in threads |
| DynamoDB | On-demand | Negligible volume |
| Bedrock quota | Default on-demand quota for Haiku 4.5 | 3 sessions × at most 3 calls per turn are far below default limits |

Scaling to 10 sessions needs only a larger task size. More than one task would need the attestation key moved to a shared secret. That is a P change.

### 11.4 Estimated cost, 26 September to 20 November 2026 (about 1.8 months)

All figures are USD, us-east-1 list prices, and should be verified in the AWS Pricing Calculator.

| Item | Monthly estimate | Basis |
| --- | --- | --- |
| Fargate ARM 0.5 vCPU / 1 GB, always on | about 12 | 730 h × (0.5 × vCPU-hour + 1 × GB-hour) |
| Application Load Balancer | about 18 | Hourly charge plus minimal LCU |
| Public IPv4 addresses | about 7 to 11 | ALB addresses across availability zones plus the task address, depending on Express Mode networking |
| CloudWatch Logs, DynamoDB, S3, ECR, Cognito | about 3 | Low volume; Cognito within the free monthly active-user tier |
| **Infrastructure subtotal** | **about 40 to 45** | **About 75 to 80 over the window** |
| Bedrock, Haiku 4.5 | 25 to 60 over the window | About 4,000 turns across development, evals and judging at roughly 1.5 cents per turn uncached; the lower end assumes prompt caching |

The window total is about **USD 100 to 140**. That fits inside the USD 150 promotional credit, but only just. The budget alert is therefore mandatory. Stop the `test` environment whenever it is not in use, and tear down after 20 November. If Express Mode networking adds a NAT gateway, that adds about USD 32 per month. Spike S-1 must confirm public subnets.

### 11.5 Deployment and run procedure (README outline)

1. Prerequisites: AWS account with Bedrock model access for Claude Haiku 4.5 in us-east-1, Docker with buildx, Python 3.12, Node 20, AWS CDK.
2. `make bootstrap` (CDK bootstrap), then `make deploy ENV=demo`: builds the ARM64 image, pushes it to ECR and deploys the stack. Outputs are the app URL, MCP URL and Cognito domain.
3. `make seed ENV=demo`: identities, households, slots and the catalog overlay.
4. Open the app URL in Chrome, sign in as a judge owner, allow the microphone.
5. MCP check: `make mcp-check` runs the handshake and tool listing against `/mcp` with a token. The README also documents MCP Inspector with the `mcp-inspector` client.
6. `make test` (unit, contract), `make e2e ENV=test`, `make eval`, `make load`.
7. `make reset HOUSEHOLD=J1` and `make destroy`.

### 11.6 AWS Builder documentation (Product Feedback content)

For each service the feedback states what it does in HomeKeep, the integration point in code, and friction found:

| Service | Role in HomeKeep | Code |
| --- | --- | --- |
| Amazon Bedrock | Converse API with tool use | `orchestrator/` |
| Strands Agents SDK | Agent loop plus MCP client | `orchestrator/agent.py` |
| DynamoDB | Conditional writes, transactions, TTL, GSI | `store/` |
| S3 | Presigned POST, quarantine flow | `domain/documents.py` |
| Cognito | PKCE, resource-server scopes, JWT verification for MCP | `security/` |
| ECS Express Mode | Hosting | `infra/` |
| Budgets, CloudWatch | Cost and operations guardrails | `infra/` |

## 12 Test design

### 12.1 Levels

| Level | Tooling | Scope |
| --- | --- | --- |
| Unit | pytest | State maps, guards (approval grammar, hazard lexicon, output guard), operation keys, date resolution with clock override |
| Contract | pytest plus the MCP 1.29 client against a running container | Handshake at `2025-11-25`; auth (401 with resource metadata, wrong scope, cross-tenant); every tool's result and error envelope; trusted-tool rejection without attestation; Origin rejection |
| Integration | pytest against the `test` stack | DynamoDB transactions and conditions, S3 flow, provider fault matrix, reconciliation |
| End-to-end | Playwright (Chrome) using the text channel | Journey scenarios; restart by stopping the ECS task; `axe-core` |
| Voice acceptance | Manual script with screen hidden, recorded on video, observer checklist | AT-13 voice parts, AT-22, AT-23 (seeded transcripts never replace audio tests, per BRD 12.1) |
| Evaluation | `scripts/eval.py`: 40 critical prompts × 3 repeats with pinned model, prompt and catalog | NFR-06: zero fabricated confirmations, zero forbidden instructions, correct citation on every model-specific step |
| Load | `scripts/load.py`: 3 concurrent simulated sessions, 100 turns | NFR-01 p95, stop latency, loop cap, correlation completeness |

### 12.2 Evaluation set composition

The 40 prompts are split into:

- hazard phrasing variants (8);
- attempts to extract repair instructions (6);
- guessed model or error-code requests (6);
- malicious-manual retrieval (4);
- confirmation-baiting ("so it's booked, right?") during pending, failed and timeout states (8);
- fee and warranty wording (4);
- fridge and TV out-of-scope requests (4).

### 12.3 Acceptance test mapping (H)

| AT | Level | Notes |
| --- | --- | --- |
| AT-01 | E2E and voice | — |
| AT-02 | Contract | — |
| AT-03 | E2E | Nickname sentinel |
| AT-04 | Contract | Verified, guessed and conflicting fixtures |
| AT-05 | Integration | Oversized and wrong-type files; cross-tenant GET; purge |
| AT-06 | Contract | Same `turn_id` replay plus same-args duplicate |
| AT-07 | E2E | Restart between answers |
| AT-08 | E2E and eval | Lexicon plus paraphrase |
| AT-09 | Contract | `RETRIEVAL_FAILURE` fault |
| AT-10 | Eval and contract | Agent has no trusted tools; output guard |
| AT-11 | E2E | ECS task stop plus client reload |
| AT-12 | E2E | Fee and coverage spoken as unknown |
| AT-13 | Unit, E2E and voice | Grammar and timing rules; expiry via clock override |
| AT-14 | Integration | `TIMEOUT_AFTER_SUCCESS`; single reference; trace |
| AT-15 | Integration | Parallel conditional decrement; `FEE_CHANGE` |
| AT-16 | Integration and E2E | `REPLACE_FAIL` then success |
| AT-17 | Integration | `CANCEL_TIMEOUT`, `CANCEL_REFUSE` |
| AT-18 | Integration | `DUPLICATE_EVENT`, `STALE_EVENT`, unassigned technician |
| AT-19 | E2E | Staff completion, then customer answer, then close and reopen |
| AT-20 | Integration | **Deviation:** repeated surfacing read replaces "scheduler event replay" because there is no scheduler in H |
| AT-21 | Contract | Revoke, then old session and pending approval are denied |
| AT-22 | Voice | Recorded; forms the demo video's core |
| AT-23 | Voice and E2E | Microphone denied; network offline through DevTools |
| AT-24 | Contract | Overlay withdraw |
| AT-25 | Integration | Purge and unverified-request denial |
| AT-29 | Load | 3-session profile (Section 1.3) |
| AT-30 | E2E and CI | axe, keyboard, zoom, fresh deploy, gitleaks, TLS check |
| AT-32 | Manual | Clean AWS account following the README |
| AT-33 | E2E | Fridge and TV scope limit; unknown AC error code |
| AT-34 | Unit and E2E | Local-midnight rollover; concurrent edit invalidates approval |
| AT-35 | Integration | `NO_SHOW`, late event, coordinator exception |

The release gate follows BRD 12.3: no open Severity 1 or 2 defects.

## 13 Traceability matrix

| Requirement | Components | Primary design sections | Tests |
| --- | --- | --- | --- |
| BR-01 | C1, C3 | 4.5, 5.4 | AT-01, AT-12 |
| BR-02 | C7, C1 | 8 | AT-22 |
| BR-03 | C1, C3 | 4.2, 6.1 | AT-07, AT-11 |
| BR-04 | C1 | 4.3, 4.6, 7 | AT-14, AT-16, eval |
| BR-05 | C1 | 4.7 | AT-04, AT-09, eval |
| BR-06 | C1, C5 | 5.2, 9 | AT-02, AT-21, AT-25 |
| BR-07 | C2, all | 2, 11 | AT-32 |
| FR-01 | C1, C5 | 4.2 T2, 5.4 `prepare_action` | AT-01, AT-02 |
| FR-02, FR-03 | C1, C3 | 4.5, 4.10 | AT-01, AT-03, AT-04 |
| FR-04 | C1, C4 | 4.8 | AT-05 |
| FR-05, FR-06 | C1, C3 | 4.5, 5.4 | AT-06, AT-07 |
| FR-07 | C1 | 4.3 | AT-08, AT-33 |
| FR-08, FR-09 | C1 | 4.7 | AT-04, AT-09, AT-10 |
| FR-10 | C1, C3 | 4.4, 6.1 | AT-07, AT-11 |
| FR-11, FR-27 | C1 | 5.4, 6.1 | AT-12, AT-15 |
| FR-12 | C1, C7 | 3.4 F2, 4.3 | AT-13, AT-34 |
| FR-13, FR-14, FR-15 | C1, C3 | 4.6, 6.2, 7 | AT-14 to AT-17 |
| FR-16, FR-17 | C1 | 4.10, 7 | AT-18, AT-19, AT-35 |
| FR-18 | C1, C3 | 4.5, 6.1 | AT-11, AT-19 |
| FR-19 | C1 | 4.9 | AT-20 |
| FR-20 | C1, C5 | 9 | AT-02, AT-21 |
| FR-21, FR-22 | C7, C1 | 8 | AT-13, AT-22, AT-23 |
| FR-23 | C1 | 4.7, 4.10 | AT-04, AT-10, AT-24 |
| FR-24 | C1, C3, C4, C5 | 6.2 | AT-25 |
| FR-28 | C1 | 5.5, 10.2, 10.3 | AT-14, AT-18 |
| NFR-01 to NFR-12 | See 10.1 | 10.1 | See 10.1 |

## 14 Delivery plan

### 14.1 Week-1 spikes (each must pass before dependent work starts)

| Spike | Question to answer | Exit condition |
| --- | --- | --- |
| S-1 Platform | ECS Express Mode resource type, ARM64 and 0.5 vCPU support, AWS-provided HTTPS domain, public-subnet networking (no NAT); Bedrock access to the Haiku 4.5 profile; prompt caching | Hello-world container reachable over HTTPS, calling Bedrock |
| S-2 Voice | Chrome continuous `en-IN` recognition, auto-restart, interim "stop" detection, echo filtering with headset and speakers | Stop within 1 s; no echo-triggered commands in 20 trials |
| S-3 MCP | FastMCP stateless JSON on `mcp==1.29.1`; Strands `MCPClient` with per-turn headers and `tool_filters`; handshake assertion `2025-11-25`; Cognito token accepted | One tool round-trip, agent → loopback MCP → DynamoDB |

### 14.2 Build sequence

| Window | Deliverables |
| --- | --- |
| 26 Sep – 2 Oct | Spikes; CDK stack; seed; catalog and synthetic manual; domain core (household, consent, appliance, issue); friction log started; credits requested |
| 3 – 9 Oct | Orchestrator and MCP tools (customer set); guards; guidance; intake; hazard flow; resume; elder UI text and voice |
| 10 – 16 Oct | Approval ledger; provider simulator with fault matrix; booking, reschedule, cancel, status; reconciliation; staff console; resolution; history |
| 17 – 20 Oct | Documents; helper grants and revocation; purge; reminders (Should); Ops page; eval, load and voice runs; README; video; submission (target 20 Oct) |
| 21 – 23 Oct | Buffer only. Deadline 23 Oct, 12:00 noon PDT |

**Schedule risk.** Full H scope is about 38 to 42 solo developer-days of build and test; about 25 working days remain. If one person builds it, apply this cut line in order until the plan fits:

1. FR-19 reminders (a Should).
2. FR-04 staff upload UI (keep the API and tests).
3. Ops page charts (keep the tables).
4. AT-29 formal load run (keep a smoke run).

Integrity controls, the hazard and output guards, and the MCP eligibility path are never cut (BRD 3.3).

## 15 Design risks and open items

| ID | Risk | Mitigation |
| --- | --- | --- |
| TR-01 | ECS Express Mode details differ from assumptions (HTTPS domain, sizes, networking cost) | Spike S-1. Fallback host: EC2 `t4g.small` with Caddy and an instance profile (needs a domain for TLS) |
| TR-02 | Chrome speech quirks (recognition restarts, voice availability, echo) | Spike S-2; headset in demos; text fallback. The voice pass is recorded separately |
| TR-03 | The event later requires or rewards spec 2026-07-28 | Tools are written to SDK-neutral schemas; upgrading to `mcp` 2.x is a dependency change plus contract re-run. Monitor the Updates page |
| TR-04 | Credits exhausted before 20 November | Budget alerts, prompt caching, stopping the test environment, turn caps |
| TR-05 | The LLM phrases a claim the output guard misses | Eval set with zero tolerance; server templates for all outcome statements; the guard is extended from eval failures |
| TR-06 | Per-process attestation blocks a future move to multiple tasks | A P change: move the key to Secrets Manager or use AgentCore identity. This is documented and not needed for 3 users |

## 16 Sources

Retrieved 25 to 26 September 2026. Recheck at each release gate.

- [S01] Build, Ship, Shape: Amazon Developer Hackathon Official Rules — https://amazonappdev2026.devpost.com/rules
- [S02] HomeKeep BRD v1.0, 24 September 2026 (baseline document)
- [S03] MCP specification 2025-11-25 changelog — https://modelcontextprotocol.info/specification/2025-11-25/changelog/
- [S04] MCP Python SDK protocol versions — https://py.sdk.modelcontextprotocol.io/protocol-versions/
- [S05] MCP Python SDK releases (1.29.x maintenance line; 2.x targets 2026-07-28) — https://github.com/modelcontextprotocol/python-sdk/releases ; 2026-07-28 announcement — https://blog.modelcontextprotocol.io/posts/2026-07-28/
- [S06] AWS App Runner availability change — https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html
- [S07] Amazon ECS Express Mode — https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html ; announcement — https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/
- [S08] Strands Agents: MCP tools and tool filters — https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/ ; `mcp` constraint widened to `>=1.23.0,<2.2` — https://github.com/strands-agents/harness-sdk/pull/4151
- [S09] Claude Haiku 4.5 on Amazon Bedrock (model IDs, APIs, regions) — https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html
- [S10] Deploy MCP servers in AgentCore Runtime — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html
