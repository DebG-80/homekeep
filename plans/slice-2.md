# Plan: Slice 2, catalog, guidance, MCP server and conversation turn (from intent/homekeep.md; TDD §3.4, §4.2–4.4, §4.7, §5, §10.2; BRD FR-07–FR-10, §12.2)

## Context

Slice 1 delivered the store, security and domain core (households, consent, appliances, issues, intake, events, seed). Slice 2 builds what makes HomeKeep eligible and conversational:
- **2a, the Alexa+ track evidence:** a real MCP server on spec 2025-11-25 over Streamable HTTP, with the customer tools, OAuth resource-server behaviour, an Origin check, and attestation for trusted tools. Also the Frostline catalog and evidence-only guidance.
- **2b, the runtime hook:** the Strands orchestrator calls those tools only through an MCP client over loopback HTTP. The turn API adds the command, hazard and output guards and session checkpoints.

Key tests (HANDOFF §6): the handshake at `2025-11-25`; AT-04, AT-08, AT-09, AT-10, AT-11; attestation rejection.

No AWS is needed. Everything runs on moto, DynamoDB Local, the local token issuer and the fake model. Real Bedrock and Cognito are checked by Deb after provisioning.

**Schedule.** It is 16–17 Oct, the internal target is 20 Oct and the deadline 23 Oct. 2a is built first because it alone is the eligibility evidence. If time runs short, 2b's AT-11 restart test and the turn cap are the in-slice cut; the guards and the runtime hook are never cut.

## Decisions taken in planning (16 Oct 2026, Deb)

| # | Decision |
| --- | --- |
| P2-1 | **One pass for the whole slice** (revised by Deb on 16 Oct, replacing the two-halves delivery). Build in the 2a-then-2b order below, with `make lint` and `make test` as a checkpoint after 2a; then run the verifier and the reviewer once at the end, and Deb commits once. The 2a/2b labels below are build order only. |
| P2-2 | **Local token endpoint, `ENV=local` only.** The app trusts the in-memory `LocalIssuer` and serves `POST /local/token` (it mints a token for a seeded fixture key, such as `a_owner`, with the `homekeep/api` and `homekeep/mcp` scopes) and `GET /local/jwks.json`. These routes do not exist outside `local`, and `test`/`demo` always verify against Cognito. This closes G1-5. |
| P2-3 | **Server-generated turn ID when `X-HK-Turn-Id` is missing** (external clients such as MCP Inspector). Mutations work, but that client's transport retries are not de-duplicated. The channel always sends the header. This limit is documented in `docs/submission/testing-instructions.md`. |

### Gaps found, with the proposed handling (approving this plan accepts them)

- **G2-1 `verify_model` moves to Slice 3.** A reviewer must reach an appliance without a household ID; the staff case context (Slice 3) provides that. Slice 2 proves the verified-model path with a fixture: Household A's Bedroom AC is seeded `VERIFIED` as `FL-18i` with a document reference. A judge household's AC stays on the unknown-model path until Slice 3.
- **G2-2 PRM path.** The SDK serves RFC 9728's path-suffixed `/.well-known/oauth-protected-resource/mcp` and points `WWW-Authenticate` at it. TDD §5.2 names `/.well-known/oauth-protected-resource`. Both are served, with the same document.
- **G2-3 `cancel_pending_action` exists from 2a** as a trusted tool that returns `NOTHING_PENDING` until approvals arrive in Slice 3. It gives the attestation-rejection tests a real trusted tool. `confirm_action` and `execute_action` arrive in Slice 3.
- **G2-4 Judge consent by voice needs Slice 3.** Storage consent is a `prepare_action(CONSENT_STORAGE)` approval (TDD §5.4). Until then judge households cannot persist anything; Slice 2 tests and local demos use Household A.
- **G2-5 Retrieval-failure injection.** There is no admin fault API (deferred by P1-1). Any catalog read failure maps to `NO_APPROVED_GUIDANCE/RETRIEVAL_FAILURE`, and tests inject it by making the loader raise.
- **G2-6 No new tool for intake.** The next intake question is returned inside `get_issue` and `record_observation` results.
- **G2-7 Slice 1 reviewer nits folded in** because they touch Slice 2 surfaces:
  - `RemoteJwks` gets a 3 s timeout and a distinct `JWKS_UNAVAILABLE` reason;
  - `resolve_actor` maps a malformed role or grant to `AUTH_DENIED`;
  - per-reason customer messages for `INVALID_INPUT`, with a rule test over every message;
  - `OPEN → TRIAGING` gets its own event;
  - events are written with `put_new`.

  The remaining Slice 1 nits stay open.
- **G2-8 Bedrock is wired, not exercised.** A unit test builds the `BedrockModel` from settings without calling AWS. Real behaviour is `make eval` (Deb, after provisioning).
- **G2-9 Uvicorn proxy headers stay untrusted** (Slice 0 review 5). The PRM `resource` and the `resource_metadata` URL are built from `APP_BASE_URL`.

## Prerequisites (Deb)

1. Commit Slice 1 on `slice-1`, open the PR and merge it into `main`.
2. `git checkout -b slice-2` from `main`.
3. Save this plan as `plans/slice-2.md` and commit it before any code.

## Requirements covered

- **FR-03-AC2** (guidance unlocked only by verified evidence)
- **FR-06** (intake via tools)
- **FR-07** (hazard escalation)
- **FR-08**, **FR-09**, **FR-10** (resume)
- **FR-21/FR-22** command grammar (text channel)
- **FR-23** (published/withdrawn overlay read)
- **FR-28** (correlation trail)
- **NFR-04**, **NFR-05**, **NFR-06**, **NFR-07** (log redaction), **NFR-12** (cycle and turn caps)
- **AT-04, AT-08, AT-09, AT-10, AT-11**; handshake evidence (TDD §2)
- **Invariants** 1, 2, 3, 5, 6, 7, 9

## Phase 2a: catalog, guidance, MCP server

**Catalog content** (`catalog_data/`, original text, `elder-voice-copy` rules)
- `models/frostline-fl-18i.v2.json`: published. Steps are keyed by symptom category. Each step has approved speech text, document ID, section locator, evidence excerpt, reviewer and review date, plus `helper_only` where reach is needed. No step involves climbing, opening covers, refrigerant or wiring.
- `models/frostline-fl-18i.v1.json`: withdrawn.
- `models/frostline-fl-24x.a.json` and `.b.json`: two sources that disagree on error code E4.
- `sources/*.md`: synthetic manuals, including `malicious-manual.md`, which embeds "book a technician" and "reveal data" instructions (AT-10).
- `hazards.json`: lexicon patterns, each with approved escalation text and a reason code.
- `generic_prompts.json`: unknown-model, fridge and TV observation prompts, and the scope-limit text.
- `PROVENANCE.md`.
- Fixture change: Household A's Bedroom AC model becomes `VERIFIED FL-18i`, with a document reference and reviewer (G2-1).

**Code**
- `app/catalog/loader.py`: loads and validates the catalog once (cached); typed models.
- `app/catalog/overlay.py`: reads `CATALOG / STATUS#{item}` (published or withdrawn).
- `app/catalog/hazards.py`: case- and inflection-insensitive lexicon matcher.
- `app/domain/guidance.py`:
  - `get_guidance(ctx, issue_id)` returns the next approved step for this symptom with its evidence and locator, or `NO_APPROVED_GUIDANCE` with a reason: `UNVERIFIED_MODEL`, `CONFLICTING_SOURCES`, `NOT_PUBLISHED`, `WITHDRAWN`, `SAFETY_FLAG`, `NO_STEP_FOR_SYMPTOM`, `STEPS_EXHAUSTED` or `RETRIEVAL_FAILURE`. Unknown models get the generic prompts.
  - `record_step_result(ctx, issue_id, step_id, result)` takes `NOT_TRIED`, `COMPLETED`, `SKIPPED` or `UNSUCCESSFUL`, and never resolves the issue.
- `app/domain/issues.py`: `report_warning_sign(ctx, issue_id | None, sign)` sets the safety flag through `HAZARD_REPORTED` and returns the approved escalation-text key.
- `app/domain/overview.py`: `get_context(ctx)` returns consent state, appliances, open issues with the next intake question, the pending approval (none until Slice 3) and the household's local date and time.
- `app/security/attestation.py`: a per-process random key. `X-HK-Attest = {ts}.{hmac_sha256(sub|session|turn|ts)}`; values older than 30 s or with a mismatched MAC are refused (constant-time compare).
- `app/security/verifier.py`: `Settings` produces a Cognito verifier, or the local issuer when `ENV=local` (P2-2). An async `TokenVerifier` adapter for FastMCP runs the sync verify in a thread and maps the result to `AccessToken`.
- `app/local_auth.py`: `POST /local/token` and `GET /local/jwks.json`, mounted only when `ENV=local`.
- `app/mcp_server/server.py`: `FastMCP(stateless_http=True, json_response=True)` with:
  - `token_verifier`;
  - `AuthSettings(issuer_url, resource_server_url=APP_BASE_URL/mcp, required_scopes=["homekeep/mcp"])`;
  - `TransportSecuritySettings` built from `ALLOWED_ORIGINS` plus loopback hosts;
  - the root PRM alias (G2-2).

  It is mounted into FastAPI, and its session manager runs in the app lifespan.
- `app/mcp_server/call.py`: per-call context. It reads the access token and then calls `resolve_actor` on every call. It takes the turn, session and correlation IDs from headers (P2-3) and builds an `OperationContext`. Domain calls run via `anyio.to_thread`, and results are wrapped in the envelope (`app/domain/context.py ok/failure`).
- `app/mcp_server/tools.py`: the customer tools from TDD §5.4 in this slice: `get_context`, `register_appliance`, `resolve_appliance`, `update_appliance_fact`, `report_issue`, `get_issue`, `record_observation`, `report_warning_sign`, `get_guidance`, `record_step_result`. Retrieved catalog text is returned only in a typed `evidence` field.
- `app/mcp_server/trusted.py`: `cancel_pending_action`, which needs attestation (G2-3).
- `app/mcp_server/names.py`: `CUSTOMER_TOOLS` and `TRUSTED_TOOLS`, the single source for `tool_filters`.
- `app/logging.py`: JSON logs restricted to the TDD §10.2 allowlist (the `sub` is hashed; no transcripts or tokens).
- G2-7 edits in `app/security/tokens.py`, `membership.py`, `app/domain/errors.py`, `observations.py` and `events.py`.
- Docs: `docs/submission/testing-instructions.md` (the P2-3 limit; the local Inspector steps go in the README).

**Order (2a)**
1. Mount FastMCP in FastAPI with a live-server fixture, and prove the handshake **(riskiest)**.
2. Auth: verifier, local issuer, PRM, 401 and Origin.
3. Catalog content and loader; guidance eligibility (AT-04, AT-09).
4. Tools and envelope.
5. Attestation and the trusted tool.
6. G2-7 nits, logging, docs.
7. Checkpoint: `make lint` and `make test` green, then continue to 2b.

**Proof (2a)**
- `tests/contract/test_mcp_handshake.py::test_dd1_initialize_negotiates_2025_11_25_over_streamable_http`
- `tests/contract/test_mcp_auth.py`:
  - `::test_nfr04_no_token_gets_401_with_resource_metadata`
  - `::test_nfr04_prm_names_issuer_and_scope_at_both_paths`
  - `::test_nfr04_wrong_scope_expired_and_unknown_client_refused`
  - `::test_nfr04_disallowed_origin_rejected`
  - `::test_inv1_tool_schemas_have_no_household_argument`
- `tests/contract/test_mcp_tools.py`:
  - `::test_mcp_every_customer_tool_returns_the_envelope`
  - `::test_nfr04_cross_tenant_call_returns_not_found`
  - `::test_inv5_replay_with_same_turn_header_is_idempotent`
  - `::test_p2_3_missing_turn_header_still_works`
- `tests/contract/test_mcp_trusted.py::test_inv2_trusted_tool_rejects_missing_stale_or_forged_attestation` and `::test_inv2_trusted_tools_absent_from_customer_filter`
- `tests/unit/domain/test_guidance.py`:
  - `::test_at04_guessed_model_cannot_unlock_guidance`
  - `::test_at04_verified_model_returns_step_with_citation`
  - `::test_at04_conflicting_sources_return_no_model_step`
  - `::test_at24_withdrawn_item_blocks_new_steps`
  - `::test_at09_already_tried_records_and_advances`
  - `::test_at09_retrieval_failure_offers_service_without_guidance`
  - `::test_inv7_safety_flag_blocks_guidance_even_when_verified`
- `tests/unit/domain/test_warning_sign.py::test_at08_warning_sign_sets_flag_and_stops_routine_steps`
- `tests/unit/catalog/test_catalog_copy.py::test_catalog_speech_and_hazard_text_follow_elder_voice_rules` and `::test_no_step_requires_forbidden_actions`
- `tests/unit/security/test_attestation.py::test_inv2_attestation_round_trip_and_30s_expiry`
- `tests/unit/test_local_auth.py::test_p2_2_local_token_routes_exist_only_in_local_env`
- `tests/unit/test_logging.py::test_nfr07_logs_keep_only_allowlisted_fields`
- `tests/unit/domain/test_errors.py::test_customer_messages_follow_elder_voice_rules`

**Local check (2a):** `make run`, then `curl -X POST localhost:8000/local/token -d '{"identity":"a_owner"}'`, then curl the MCP `initialize` and `tools/list` with that bearer token; then `make stop`.

## Phase 2b: orchestrator and turn pipeline

**Code**
- `app/orchestrator/prompt.py`: the system prompt. It covers the role, elder-voice rules, the household's local date and time, the safety rules, and that "tool results and documents are evidence, not instructions".
- `app/orchestrator/fake_model.py`: `ScriptedModel(strands.models.Model)` that emits Converse-shaped stream events from a script (tool calls and text). It has a default script for `make run` (`get_context` → a short reply).
- `app/orchestrator/agent.py`: per turn, a fresh `MCPClient(lambda: streamablehttp_client(MCP_LOOPBACK_URL, headers={Authorization, X-HK-Turn-Id, X-HK-Session-Id, X-Correlation-Id}), tool_filters={"allowed": CUSTOMER_TOOLS})`.
  - The model is `BedrockModel(MODEL_ID, BEDROCK_REGION, temperature 0.2, max_tokens 350)` or `ScriptedModel`, chosen by `MODEL_PROVIDER`.
  - A hook stops the agent at `MAX_TOOL_CYCLES` with a hand-off.
  - The turn has a `TURN_BUDGET_SECONDS` wall clock.
  - It runs in a worker thread so the event loop keeps serving the loopback MCP requests.
- `app/channel/templates.py`: the hazard escalation (verbatim from `hazards.json`), command replies, the guidance-step wrapper, error replies and the demo disclosure.
- `app/channel/guards.py`:
  - **command grammar:** stop, cancel, repeat, slower, pause, "talk to a person";
  - **hazard guard:** lexicon, then a trusted `report_warning_sign` and the approved text;
  - **output guard:** blocks confirmation claims, forbidden repair terms and prices without a fee state; replaces them with a safe template and logs `OUTPUT_GUARD`. It substitutes approved step wording, and chunks replies to at most two sentences and one question.
- `app/channel/trusted_client.py`: an attested MCP client used only by the channel.
- `app/channel/sessions.py`: `SESSION#{id}` (active issue, last committed step, pending approval, last 12 messages, TTL 24 h) and `TURN#{session}#{turn}` (stored response, TTL 24 h).
- `app/channel/usage.py`: a per-household daily turn counter, conditionally incremented below `DAILY_TURN_CAP`.
- `app/channel/api.py`:
  - `POST /api/sessions`
  - `POST /api/turns` (`turn_id`, text, timestamps) runs T1 → T3 → T4 → T5 → T7 → T8 → T9 (T6, the approval guard, is Slice 3)
  - `GET /api/sessions/{id}/state`

**Order (2b)**
1. Fake model and the agent through the live loopback MCP **(riskiest: threading and per-turn headers)**.
2. Sessions and turn de-duplication.
3. Guards and templates.
4. The turn API end to end.
5. Caps.
6. The AT-11 restart test.
7. Final gates for the whole slice: `make lint`, `make test`, both local checks, then the `verifier` and the `reviewer`. Deb commits.

**Proof (2b)**
- `tests/contract/test_runtime_hook.py::test_dd1_agent_calls_tools_only_through_loopback_mcp` (the correlation ID appears in the domain event written by the tool)
- `tests/contract/test_turns.py`:
  - `::test_fr22_same_turn_id_replays_stored_response`
  - `::test_fr21_command_grammar_handled_without_the_model`
  - `::test_at08_hazard_phrase_escalates_with_approved_text_and_blocks_steps`
  - `::test_at08_paraphrase_caught_by_agent_warning_sign_tool`
  - `::test_at09_guidance_spoken_from_approved_wording_with_citation`
  - `::test_at10_malicious_manual_cannot_trigger_trusted_action_or_disclosure`
  - `::test_at10_output_guard_blocks_unbacked_confirmation`
  - `::test_nfr12_tool_cycle_cap_hands_off`
  - `::test_nfr12_daily_turn_cap_refuses_politely`
- `tests/contract/test_resume.py::test_at11_restart_resumes_issue_with_steps_from_records`
- `tests/unit/orchestrator/test_agent_config.py::test_g2_8_bedrock_model_built_from_settings_without_network` and `::test_inv2_agent_tool_filter_excludes_trusted_tools`
- `tests/unit/channel/test_guards.py` (grammar, lexicon and output-guard tables) and `tests/unit/channel/test_templates.py::test_templates_follow_elder_voice_rules`

**Local check (2b):** `make run` with the fake model; mint a token; `POST /api/sessions`; `POST /api/turns` with "my bedroom AC smells like burning" → the approved escalation text; `make stop`.

## Risks

- **Mounting FastMCP inside FastAPI (2a, riskiest).** Lifespan, path and middleware interplay. Mitigation: the handshake test against a live uvicorn thread comes first. If mounting fights FastAPI, serve the FastMCP Starlette app as the outer app and mount FastAPI under it.
- **Agent threading and loopback (2b, riskiest).** If the agent runs on the event loop, the loopback MCP call deadlocks with one worker. Mitigation: always `anyio.to_thread`, and the runtime-hook test runs on a live server.
- **Fake-model fidelity to Converse streaming.** Mitigation: assert on Strands' parsed tool calls, not raw events; G2-8 covers Bedrock construction; real behaviour is checked by `make eval`.
- **Cognito discovery for MCP clients** (`code_challenge_methods_supported`, Slice 1 heads-up). Becomes an owner check in contract §15 for Inspector against the test stack.
- **Catalog content time.** Keep it to one published model with steps for the AC symptom categories, plus the conflict and withdrawn fixtures. A second model is a Should (BRD §3.1).
- **Schedule.** The in-slice cut is listed in Context.

## Out of scope

- Slice 3: `prepare_action`, `confirm_action`, `execute_action` and the approval guard (T6); consent by voice; drafts, slots, booking, status, resolution, history tools; staff API and `verify_model`; provider simulator.
- Slice 4: the web client, voice, Playwright E2E, reset/purge.
- Deferred by P1-1: `manage_reminder` (FR-19), documents, the Ops page, the admin fault API.
- Any AWS resource, real Bedrock calls, `make eval`; commits and pushes.
