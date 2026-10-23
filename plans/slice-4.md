# Plan: Slice 4, web client, owner grants, reset/purge/admin CLI, eval and load runners, README (from intent/homekeep.md; TDD §4.1, §4.10, §8, §9, §11.5, §12; BRD §5.5, §11, FR-20 to FR-24; HANDOFF §6 Slice 4)

## Context

Slices 0–3 are committed and merged into `main` (`3e657d8`). The server side of the BRD §3.3 path works end to end through the turn API and MCP. Nothing a judge or elder can use is built yet. The web app is still the Slice 0 placeholder, and FastAPI doesn't even serve it.

Slice 4 is the last build slice. It delivers:
- the browser client the demo video and judges use: elder voice and text, household and history, staff console;
- owner-managed helper grants and revocation (FR-20);
- the judges' "Reset my demo data", plus an audited `hk-admin` CLI for purge, grants, catalog withdrawal and faults;
- the real-Bedrock eval runner behind `make eval`, and a load smoke script;
- Playwright text-path E2E with axe behind `make e2e`;
- the README and the voice-test checklist for Deb.

Key tests (HANDOFF §6, cut down by P1-1): AT-21, AT-23 (E2E part), AT-24, AT-25, AT-30, AT-33, plus the E2E journeys. AT-22 and the voice parts of AT-13 and AT-23 are Deb's manual voice runs (TDD §12.1).

**Schedule (explicit risk).** It is 17 Oct; the internal target is 20 Oct and the deadline 23 Oct 12:00 PDT. Deb's AWS provisioning, deploy, voice runs and video also need those days. Deb chose one pass (P4-1). **Slice 4 must land by about 20–21 Oct to leave deploy and video time.** In-slice cut order, should Deb call it:
1. The load script.
2. `hk-admin` fault and catalog commands (purge, reset and grants stay).
3. Playwright voice-stub tests (the text path and axe stay).
4. Staff console extras: assignment, manual review and safety pages (queue, case view and visit events stay).

Never cut: sign-in, the elder voice and text client, judge reset, revocation, the eval runner, the README.

## Decisions taken in planning (17 Oct 2026, Deb)

| # | Decision | Deviation from |
| --- | --- | --- |
| P4-1 | **One implementation pass**, as P3-4: server additions, then the checkpoint (`make lint`, `make test`), then the web client and E2E, then the verifier and reviewer once. Deb commits once. | — |
| P4-2 | **Admin surface = `hk-admin` CLI plus the in-app judge reset.** No `/api/admin/*` routes (BRD §11.4 allows scripts in H). Every CLI action goes through domain functions and writes an audit event. | TDD §4.10 lists `/api/admin/*` |
| P4-3 | **The owner manages helper grants in the app.** The household view lists members; the owner can change a helper's grants or revoke them. Revocation also calls Cognito `AdminUserGlobalSignOut`, which the task role already allows (infra-contract §6.1). The CLI can do the same for setup. | — (FR-20, TDD §9.1) |
| P4-4 | **E2E runs locally only** (`make e2e` against `make run`). CI is unchanged. | HANDOFF §6 lists AT-30 "E2E and CI": the CI part stays lint, test, audit and gitleaks |

Still deferred by P1-1: FR-19 reminders (AT-20), FR-04 documents and S3 (AT-05), the Ops page and token-usage records, the formal AT-29 load run, `evals.yml` and `smoke.yml`.

### Gaps found, with the proposed handling (approving this plan accepts them)

- **G4-1 Serving the client.** FastAPI serves `web/dist`: `index.html` at `/` and hashed assets at `/assets/*`, registered before the MCP mount, with hash routes `#/talk`, `#/household`, `#/staff`. HTML responses carry a strict CSP: `default-src 'self'`, `connect-src` self plus the Cognito domain, and no inline script or style, so the placeholder's injected `<style>` moves to a CSS file. A public `GET /api/config` returns only non-secret client settings: env, Cognito domain, web client ID, and whether local sign-in is on.
- **G4-2 Sign-in.** On AWS: `oidc-client-ts`, authorisation code with PKCE against the Cognito managed login, with the refresh token in `sessionStorage` (TDD §9.1). Locally (`ENV=local`): an identity picker calling the existing `/local/token`. The client never handles a household ID.
- **G4-3 Household REST for the views.** The views need reads the agent gets through MCP. These call the same domain functions with the token's actor, so every call authorises in the domain:
  - `GET /api/household`: appliances with confidence labels ("not provided", never an error), open issues, open requests, consent state;
  - `GET /api/appliances/{id}/history`;
  - `GET /api/household/members`;
  - `POST /api/household/members/{member}/grants` and `/revoke`, owner only, via a new `Action.MEMBER_MANAGE`;
  - `POST /api/household/reset`, owner of a `resettable` household only.
- **G4-4 Stop endpoint** (TDD §8.3): `POST /api/sessions/{id}/stop` calls `cancel_pending_action` through the trusted client, clears the session's pending fields, and returns the approved STOP text.
- **G4-5 Revocation semantics** (FR-20-AC2). The membership status becomes `REVOKED` and the helper's PENDING or APPROVED approvals become `CANCELLED`, in one transaction with an event. Membership is already re-read on every call, so old tokens get 403 on the next request; global sign-out ends refresh. Existing bookings stay intact. Granting can never exceed the owner's own rights, and the owner can't revoke themself.
- **G4-6 Judge reset and purge share one module** (`app/admin/purge.py`). Fixture item builders move from `scripts/seed.py` to `app/admin/fixtures.py`, because the container ships `app/` and `fixtures/` but not `scripts/`; the seed imports them.
  - **Reset** deletes every item under the household except memberships and user links, plus the household's REF items, OPS manual items and fault item. It releases slot places held by its active appointments, then rewrites the household's fixture items.
  - **Purge** (CLI, test households only) removes everything including memberships and user links, and signs those users out (FR-24-AC1).
  - No voice or MCP path can delete anything (FR-24-AC2).
- **G4-7 Driving E2E journeys locally.** `make run`'s fake model only calls `get_context`, so it cannot drive a booking. Add a local-only `POST /local/fake-model/script`, mounted only when `ENV=local` and `MODEL_PROVIDER=fake`, which queues scripted steps for the next turns. Tests read IDs from `GET /api/household` and then queue the next step. AWS never mounts it.
- **G4-8 The voice client feeds the approval guard.** Each turn sends `channel`, `client_state`, `speech_started_at` and `playback_ended_at`. While SPEAKING, only the stop, repeat and slower grammar acts, and only when the transcript isn't similar to what is being spoken (TDD §8.4). Approval is never sent in that state. A retry after connection loss reuses the same `turn_id` after `GET /sessions/{id}/state` (FR-22-AC1).
- **G4-9 Voice can't be automated.** Playwright stubs `SpeechRecognition` and `speechSynthesis` to test the client's state machine: microphone denied leads to text with an explanation; offline leads to DISCONNECTED and "I'll check what was saved"; stop. These are labelled "not a voice pass" (FR-21-AC2). Real voice runs follow `docs/voice-test-checklist.md` (Deb: AT-13 voice, AT-22, AT-23).
- **G4-10 Eval runner** (`scripts/eval.py`, `make eval`, Deb only).
  - `evals/prompts.jsonl` has 40 prompts in the TDD §12.2 mix, each with the household state it needs.
  - It runs each prompt 3 times through the real turn pipeline, in-process with `MODEL_PROVIDER=bedrock`, against DynamoDB Local from `make run`, using Deb's AWS credentials for Bedrock only.
  - It checks NFR-06 with zero tolerance: no confirmation without a server template, no forbidden instruction (output guard and lexicon), approved hazard text on hazards, a citation on every model-specific step, and no fee called "free".
  - It writes a JSON report.
  - The runner itself is unit-tested offline with the fake model; real runs are Deb's.
- **G4-11 Load smoke** (`scripts/load.py`): 3 concurrent sessions and N turns against a base URL. It reports p50/p95 latency, errors and correlation completeness. It is smoke-run locally with the fake model; the formal AT-29 run stays deferred.
- **G4-12 Clock-dependent cases** (AT-13 expiry, AT-34) stay at unit and contract level, where Slice 3 already proves them. E2E needs no clock override.
- **G4-13 Membership display names.** The seed adds a `display_name` (the fixture username) to membership items, so the owner can tell helpers apart without seeing subjects.

## Prerequisites (Deb)

1. On `slice-4` (already created from `main`).
2. Save this plan as `plans/slice-4.md` and commit it before any code.

## Requirements covered

- **FR-20** (grants and revocation), **FR-21** and **FR-22** (client recovery), **FR-23** (overlay through the CLI), **FR-24** (purge and reset).
- **BR-02**, **BR-07** (README).
- **NFR-01** (timing measured), **NFR-03** (accessibility), **NFR-06** (eval), **NFR-10** (clean deploy instructions).
- **AT-21**, **AT-23**, **AT-24**, **AT-25**, **AT-30**, **AT-33**, plus the E2E journeys, which cover the AT-01, AT-12, AT-16 and AT-19 paths at E2E level.

## Server additions (built first)

- `app/web.py`: static serving of `web/dist` with CSP and security headers; `GET /api/config`.
- `app/channel/api.py`: `POST /api/sessions/{id}/stop`.
- `app/household/api.py` (new): the household routes in G4-3, sharing `app/http_errors.py` and the bearer and actor helpers.
- `app/domain/members.py` (new): `list_members`, `set_grants` and `revoke`, with events. `Action.MEMBER_MANAGE` is owner only (`app/security/authz.py`). An injectable `SignOut` port uses boto3 `cognito-idp` on AWS and is a no-op locally.
- `app/admin/fixtures.py` (moved from the seed) and `app/admin/purge.py` (`reset_household` and `purge_household`), reusing `Table.query`, `delete_op` and the slot release op in `app/provider/simulator.py`.
- `scripts/hk_admin.py`, an argparse CLI run as `uv run python -m scripts.hk_admin …`:
  - `reset`, `purge`, `grant`, `revoke`;
  - `catalog withdraw|restore` (writes the `CATALOG/STATUS#` overlay in `app/catalog/overlay.py`);
  - `fault set|clear` (the `FAULT#` item in `app/provider/faults.py`).

  It has the same target guard as the seed: local, or table and pool names ending `-test` or `-demo`, with a dry run unless `--yes`. Every action writes an audit event attributed to `admin:cli`.
- `app/local_auth.py`: `POST /local/fake-model/script` (G4-7), feeding `TurnScripts` in `app/orchestrator/fake_model.py`.
- `scripts/seed.py`: membership `display_name`; imports the fixture builders.
- `scripts/eval.py`, `evals/prompts.jsonl`, `scripts/load.py`.
- Makefile: `make eval` (refuses unless `MODEL_PROVIDER=bedrock` and `make run` is up) and `make e2e` (installs Playwright Chromium if missing, then runs against `http://localhost:8000`).

## Web client (`web/src`, TypeScript, no framework)

- `config.ts` and `auth.ts`: `/api/config`, then `oidc-client-ts` on AWS or the local identity picker; token refresh.
- `api.ts`: fetch wrapper (bearer token, `turn_id`, retry with the same `turn_id` after reconnect).
- `voice.ts`: the TDD §8.2 state machine (`IDLE`, `LISTENING`, `PROCESSING`, `SPEAKING`, `PAUSED`, `DISCONNECTED`):
  - continuous `en-IN` recognition with auto-restart;
  - `speechSynthesis` split by sentence, rate 0.8 when slower;
  - the 15 s and 20 s silence rules, and a 4 s "still working" line;
  - the echo filter and barge-in grammar;
  - the timestamps the approval guard expects.
- `views/talk.ts` (BRD §11.1):
  - large microphone and stop controls;
  - text input and transcript;
  - the current appliance or issue, and one next action;
  - an ARIA live region for state.
- `views/household.ts` (BRD §11.2):
  - appliances with confidence labels and open issues;
  - history with actor and time;
  - for the owner, members with grant toggles and revoke;
  - "Reset my demo data" for judge households.
- `views/staff.ts` (BRD §11.3, TDD §4.10):
  - the queue, with pending reconciliation highlighted;
  - case view with masked fields;
  - visit and provider events;
  - assignment, manual review and safety clearing (coordinator).

  Model verification stays API-only: there is no catalog-reviewer page.
- `styles.css`: large type, visible focus, works at 200% zoom.
- Every view carries the persistent "DEMO — simulated service desk" badge.
- Keyboard: Space toggles the microphone, Esc stops, Enter sends, R repeats.
- Dependencies, pinned in `web/package.json`: `oidc-client-ts` (runtime); `@playwright/test` and `@axe-core/playwright` (dev).
- `web/e2e/*.spec.ts`: Playwright tests.

## Documentation

- `README.md` rewrite:
  - what HomeKeep is;
  - architecture (MCP hook evidence: `app/orchestrator/agent.py` → `mcp.client.streamable_http`);
  - local run (`make run`, local sign-in, demo walk-through);
  - AWS deploy (points to `docs/infra-contract.md`, seed, `hk-admin`);
  - tests (`make test`, `make e2e`, `make eval`);
  - the privacy note (Chrome sends speech to Google's service, no audio is stored; BRD §8.3);
  - the demo-only disclosure;
  - the licence.
- `docs/voice-test-checklist.md` for Deb: AT-13 voice cases, AT-22 screen-hidden journey, AT-23 microphone denied and offline, the stop-within-1-s timing, and an observer table.
- `docs/submission/testing-instructions.md`: fix the Slice 0 nit (Inspector lists the trusted tools too, and they refuse without attestation).

## Order of work

1. Fixture builders moved, then purge and reset; members, grants and revocation **(riskiest server piece: complete removal, no cross-household effect)**.
2. Household REST, the stop endpoint, static serving and config.
3. `hk-admin` CLI; local fake-model script endpoint.
4. Eval runner and prompt set; load script.
5. Checkpoint: `make lint` and `make test`.
6. Web: config and auth, then the API client, then the talk view (text path first).
7. Voice state machine.
8. Household view, then the staff console.
9. Playwright E2E and axe; `make e2e`.
10. README, voice checklist, testing-instructions fix.
11. Final gates, local check, verifier, reviewer.

## Risks

- **Purge or reset deleting another household's data, or leaving personal data behind (riskiest).** Mitigation: deletes are driven by the household's own partition plus IDs read from it, never a scan by prefix. Tests seed two households and assert the other is byte-for-byte unchanged, and that no REF, USER link, OPS item or fault item for the purged household remains.
- **Chrome speech behaviour** (TR-02): the state machine is unit-tested with stubs; a headset is required for demos; text fallback is always present; Deb's manual run is the real gate.
- **The CSP breaking `oidc-client-ts` or Vite output:** `connect-src` includes the Cognito domain; E2E covers sign-in locally, and Deb's first AWS deploy checks the managed login.
- **Playwright and browser download on Deb's machine:** `make e2e` installs Chromium once; there's no CI dependency (P4-4).
- **Scope against the deadline:** see Context for the cut order.

## Proof

`make test` must pass, including these key tests (full names are fixed when the tests are written first):
- **AT-21:** `tests/contract/test_household_api.py::test_at21_view_helper_cannot_book_revoked_helper_old_token_and_pending_action_denied`.
- **FR-20 grants:** `::test_fr20_owner_sets_grants_never_beyond_owner_and_cannot_revoke_self`.
- **AT-24:** `tests/contract/test_admin_cli.py::test_at24_withdrawn_item_refused_over_mcp_history_kept`.
- **AT-25:** `tests/unit/admin/test_purge.py::test_at25_purge_removes_records_refs_links_and_access_other_household_untouched`, `::test_at25_no_tool_or_route_can_delete`.
- **Judge reset:** `::test_reset_restores_seed_releases_slots_keeps_members`; `test_household_api.py::test_reset_only_owner_of_resettable_household`.
- **Stop:** `tests/contract/test_turns.py::test_stop_endpoint_cancels_pending_and_keeps_committed_state`.
- **Serving:** `tests/contract/test_web.py::test_index_and_assets_served_with_csp_and_config_has_no_secrets`.
- **Eval runner:** `tests/unit/test_eval_runner.py::test_eval_runner_flags_fabricated_confirmation_and_passes_clean_run`, `::test_prompt_set_matches_tdd_12_2_composition`.
- **Load script:** `tests/unit/test_load_script.py::test_load_reports_latency_and_correlation`.
- **hk-admin guard:** `tests/unit/admin/test_cli.py::test_cli_refuses_non_test_targets_and_dry_runs_without_yes`.

`make e2e` (local, against `make run`) must pass:
- `web/e2e/journey.spec.ts`: the J1 text path:
  1. consent;
  2. register an AC;
  3. report;
  4. draft;
  5. address and contact;
  6. slots;
  7. read-back;
  8. "yes" leads to the demo confirmation, with "No real technician will visit";
  9. the staff console marks the visit done;
  10. "it works now", then close;
  11. history shows the technician and customer entries.
- `web/e2e/scope.spec.ts`: **AT-33**, a fridge or TV symptom and an unknown AC code lead to the labelled scope limit and a service draft.
- `web/e2e/recovery.spec.ts`: **AT-23** (stubbed): microphone denied, offline then reconnect with the same `turn_id`, stop.
- `web/e2e/a11y.spec.ts`: **AT-30**: zero axe violations on the talk, household and staff views; the keyboard shortcuts work; no horizontal scroll at 200% zoom.
- `web/e2e/grants.spec.ts`: the owner revokes the booking helper, whose next turn is refused.

`make lint`: zero findings, including the web typecheck.

**Local check:** `make run`, then `make e2e`; `hk-admin reset --household judge-1` against DynamoDB Local; `make stop`.

**Verifier:** PASS. **Reviewer:** findings for Deb.

**Deb only, after deploy:**
- `make eval`: zero NFR-06 violations;
- the voice checklist (AT-13 voice, AT-22, AT-23), recorded;
- AT-32 from the README in a clean account.

## Out of scope

- The P1-1 deferrals listed above.
- `/api/admin/*` routes (P4-2).
- A catalog-reviewer page.
- A real provider adapter and payments.
- AWS resources, deploy, real Bedrock runs, commits and pushes.

## Implementation deviations and notes (recorded during implementation, 17 Oct 2026)

Built in one pass per P4-1: server additions, then the checkpoint (`make lint` clean, `make test` 363 passed), then the web client, E2E and documents. Every Proof test named above exists under that name and was written before its code, and was run before the code existed: each failed, by an import error for a missing module or by wrong behaviour. One exception: the stop-endpoint test was run together with `test_web.py`, whose missing module stopped collection, so its own failure was not observed separately. Regression guards are noted below.

| # | Plan said | Implemented | Why |
| --- | --- | --- | --- |
| D4-1 | — | The in-process server core moved from `tests/contract/live.py` to `scripts/inprocess.py`; the test helper re-exports it | The eval and load runners need the same real server; `scripts/` must not import from `tests/`. |
| D4-2 | Purge finds the household's REF items from its records | Every safety hold also writes a `HOLD#{hold_id}` marker in the household partition, in the hold's transaction | A household can have had several holds; only the latest is on `META`. Without the marker, older hold REFs would survive a purge. |
| D4-3 | CLI actions go through domain functions | A new `ActorKind.OPERATOR` (`admin:cli`), allowed only `MEMBER_MANAGE` and `HOUSEHOLD_RESET` for the one household named on the command line | The members domain authorises the owner; the CLI needs an audited identity of its own rather than impersonating one. |
| D4-4 | G4-13: memberships gain `display_name` | Also `identity_key` (the fixture key) | Reset rebuilds the seed's membership (role, grants, status) for the same Cognito subject. |
| D4-5 | G4-4: the stop endpoint calls `cancel_pending_action` | `POST /api/sessions/{id}/stop {turn_id, channel}` runs the existing STOP command as its own turn | The STOP command already cancels and clears the pending action; making it a turn gives it `turn_id` idempotency for free. |
| D4-6 | — | The "no delete route" test lists routes through `app.openapi()` | FastAPI 0.143 includes routers lazily, so `app.routes` does not show them. |
| D4-7 | `make e2e` runs against `make run` | It also restarts DynamoDB Local (in-memory) and reseeds before Playwright | The grants test revokes a seeded helper; every run must start from the fixtures. `make e2e` therefore resets local data, as the README says. |
| D4-8 | Web dependencies pinned | `playwright-core@1.63.0` is pinned as a direct dev dependency as well | `@axe-core/playwright` otherwise pulls a newer `playwright-core` whose types clash with `@playwright/test` 1.63.0. |
| D4-9 | G4-10: the eval uses Deb's AWS credentials for Bedrock | It signs in with the local issuer against DynamoDB Local; `.env.eval` needs only `MODEL_ID`, `BEDROCK_REGION` and `AWS_PROFILE` (`make eval` loads it). The infra-contract §14 line that said Cognito values go in `.env.eval` is corrected. Guard trips count as failures, not only unsafe spoken text | Nothing on AWS but the model is touched. Zero tolerance means the model attempting a confirmation is a failure even when the guard catches it (TR-05). |
| D4-10 | Audit every CLI action | Audit records live in the `OPS` partition (`AUDIT#…`, with `target_household`); reset also writes a `HOUSEHOLD_RESET` event in the household | A purged household's own partition cannot hold its audit trail (BRD §11.4). |
| D4-11 | — | The speaker finishes by an estimated duration if `speechSynthesis` never fires `end` | Some browsers (no voices installed, headless) never fire it; the client would hang in SPEAKING. |
| D4-12 | — | The talk view's current-issue line and next action come from `GET /api/household` and the turn response | No new endpoint was needed. |
| D4-13 | — | `scripts.seed._local_table` is now `local_table`, and the fixture builders' `_in_env` is `in_env` | Both are shared with `hk_admin` and the eval runner. |

Notes:
- The E2E suite stubs `speechSynthesis` and `SpeechRecognition`. Those runs check the client's state machine and recovery, never voice (FR-21-AC2); `docs/voice-test-checklist.md` is the voice evidence.
- Regression guards that passed when first written: the eval runner's hazard check (the server already speaks approved text), and the load script against an existing turn API.
- The local fake model cannot hold a conversation, so the README's walk-through says that the full conversation needs the deployed model or `make eval`.
- Still deferred (P1-1): reminders, documents and S3, the Ops page, the formal AT-29 run, `evals.yml`, `smoke.yml`.

## Review fixes (17 Oct 2026)

The `reviewer` subagent found 1 Critical and 10 Important issues, plus nits; the verifier passed the slice with four observations. Deb chose to fix all of them except HSTS, which is deferred. Each fix started with a test that was run and seen to fail for the reported reason, except where a row says "regression guard".

| # | Finding | Fix | Test |
| --- | --- | --- | --- |
| C1 (Critical) | Cancelled or unfinished speech counted as "playback ended", so a "yes" could approve without a completed read-back | `Speaker` tracks a generation per `speak`. Only playback whose every utterance fired `end` is `completed`; `error` (which `cancel()` fires) never is. A cancelled or replaced call resolves `superseded` and the view ignores it. The length-estimate timer is gone: the only fallback is the synthesiser going quiet after it was heard speaking. Voice turns send the state the words were heard in | `web/e2e/voice.spec.ts` "c1: a yes is never sent during or after an unfinished read-back" (failed against the old client: it flipped to LISTENING mid-read-back) |
| I1 | Reset and purge could give a shared slot place back twice; completed future visits leaked places | Each request's places are released in one transaction with a version-conditional delete of the request, so a racing second reset releases nothing. CANCEL_PENDING requests whose provider record is CANCELLED hold no place. COMPLETED requests on a future slot give theirs back | `tests/unit/admin/test_purge.py::test_i1_reset_never_gives_back_a_place_twice`, `::test_i1_two_resets_racing_release_each_place_once`, `::test_i1_reset_gives_back_a_future_place_after_the_visit_was_marked_done` |
| I2 | Reset cleared the daily turn cap | `USAGE#` items are kept, with memberships | `::test_i2_reset_keeps_the_daily_turn_count` |
| I3 | A reset that stopped midway deleted `META` and could not be run again | `META` is kept until the fixture overwrites it; memberships are never deleted. While fixing this, a prefix bug was found (memberships, `MEMBER#`, were deleted and rebuilt). The test now asserts the judge is still signed in after a failed reset, and it failed against that bug | `::test_i3_a_failed_reset_can_be_run_again` |
| I4 | Leaving the Talk page left the microphone and listeners live | Views expose `dispose()`, which stops recognition and speech and removes their listeners; the router calls it before showing the next view. Late results check `isConnected` | `voice.spec.ts` "i4: leaving the Talk page turns the microphone off" |
| I5 | Stop acted only on final results | An interim "stop" heard while speaking (not an echo) cancels speech at once and posts one stop; the final result for the same word within 3 s is ignored | `voice.spec.ts` "i5: an interim 'stop' cuts speech at once and stops only once" |
| I6 | `member_ref` was the raw Cognito subject, in URLs and the access log | `member_ref` is an opaque hash of household and subject; the CLI resolves sign-in names to it. The container runs uvicorn with `--no-access-log` (request paths are not on the §10.2 allowlist) | `tests/unit/domain/test_members.py::test_g4_13_member_refs_are_opaque`; `test_household_api.py` (no `local-` in any ref); `tests/unit/test_container_contents.py::test_access_log_is_off_so_urls_never_reach_the_logs` |
| I7 | An eval run where the model never answered passed | `RUN_ERROR` when the speech is the turn-error or cycle-cap template | `tests/unit/test_eval_runner.py::test_i7_a_run_the_model_never_answered_fails` |
| I8 | Eval checks reused the product's guard; no citation check | The eval's own, wider booking-claim lexicon for confirmation-bait prompts, and `UNCITED_INSTRUCTION` for repair-like speech without a citation, ignoring reviewed hazard, observation and scope wording | `::test_i8_checks_do_not_rely_on_the_product_guard` (a phrasing the guard misses), `::test_i8_approved_observation_prompts_are_not_counted_as_instructions` (written after a probe found the approved fridge prompt matched "open the") |
| I9 | An expired or revoked sign-in was reported as a lost connection | The token is fetched before the request; a failure becomes `ApiError(401, "SIGNED_OUT")`, which the talk view reports as signed out | Not automated: local tokens cannot expire. Checked by reading; Deb's AWS run covers it |
| I10 | A Cognito sign-out failure crashed the CLI after the data had changed | Each sign-out is tried separately; the CLI prints who was and was not signed out, and exits 1 if any failed | `tests/unit/admin/test_cli.py::test_i10_a_failed_sign_out_is_reported_not_crashed` |
| N | Revocation also cancelled approvals already sent to the provider | Only approvals not yet dispatched (PENDING, or APPROVED whose request does not carry that approval) are cancelled | `test_members.py::test_revocation_cancels_waiting_approvals_but_not_a_booking_already_sent` |
| N | `BEYOND_OWNER` never exercised | A domain test with an owner holding fewer grants | `test_members.py::test_fr20_grants_never_beyond_the_owners_own` (regression guard: the check already existed) |
| N | The infra contract named `GET /config.json` | Corrected to `GET /api/config` | — |
| N | Staff case errors were silent | A message when a case cannot be opened | Not automated |
| N | A Cognito `?error=` callback could loop back to sign-in | Shows "Sign-in didn't complete…" instead | Not automated: needs Cognito |
| N | A resend after a lost session repeated the "You:" line | The resend path does not add a line | Not automated |
| N | README phone number | "Give a made-up address and phone number" | — |
| Verifier | `make eval` did not check its prerequisites; the CLI did not check the pool name | `make eval` refuses without DynamoDB Local on :8001; the AWS target refuses a user pool whose name does not match the table's `-test`/`-demo` suffix | `test_cli.py::test_cli_refuses_a_user_pool_that_is_not_test_or_demo` |

Deferred or unchanged:
- **HSTS:** deferred. Deb checks on the first deploy whether the Express Mode HTTPS domain already sends it.
- **`purge_household` does not itself check for a test household:** unchanged. It is reachable only through `hk-admin`, behind the `-test`/`-demo` table and pool guards.
- **Owner-facing member refs:** now opaque (I6), so G4-13's intent holds.
- **Local `hk-admin` writes without `--yes`:** by design. Only the AWS target dry-runs.

Gates after the fixes: `make lint` clean (187 files); `make test` 377 passed; `make e2e` 12 passed against a rebuilt `make run`. The talk view's keydown block was re-indented after that E2E run (whitespace only; typecheck clean).

## Post-merge fixes (17 Oct 2026, branch `post-slice-4-fixes`)

These items needed no input from Deb; the ones that do are listed in `plans/deb-inputs.md`. Each started with a test that was run first. Rows marked "guard" passed before the fix.

| Item | Fix | Test |
| --- | --- | --- |
| Web callback path differed from infra-contract §5.3 (G-4) | `redirect_uri` is `${APP_BASE_URL}/auth/callback`, `post_logout_redirect_uri` is `${APP_BASE_URL}/`; the page is served at both | `tests/contract/test_web.py` (both tests updated) |
| Library INFO lines reached the log stream (verifier observation) | `httpx`, `httpcore` and `mcp` loggers set to WARNING in `configure_logging` | `tests/unit/test_logging.py::test_library_request_logs_stay_out_of_the_log_stream` (reproduces FastMCP's INFO root) |
| `CLOCK_OVERRIDE` accepted a bare epoch (Slice 0 nit) | ISO 8601 with an offset only | `tests/unit/test_config.py::test_inv10_clock_override_must_be_an_iso_timestamp_with_offset` |
| The sweep's `authorize_system` was a tautology (Slice 3 N5) | The identity comes from the record's partition and is checked against the record's `household_id`; a mismatch is skipped and logged | `tests/unit/domain/test_sweep.py::test_n5_sweep_skips_…` (guard: the old code also wrote nothing, because the reconcile failed) |
| The opaque member-reference test could not fail | Asserts the format, uniqueness per household, and refusal of a raw subject | `tests/unit/domain/test_members.py::test_g4_13_member_refs_are_opaque` |
| `speak()` reported "completed" with nothing spoken | Returns `completed: false` | Not automated (TypeScript; typecheck and E2E green) |
| Documentation | Contract §6.1 ARN region; testing instructions, video script, description and built-with brought up to date; S3 no longer claimed | — |
| `BUCKET_NAME` required at startup although documents are deferred (deb-inputs 1a, 21 Oct) | `BUCKET_NAME` removed from settings and `.env.example`; contract §4 says not to create a bucket; S3 statements dropped from the §6.1 task role; §9, §14, §15 and §16 updated; the S3 product-feedback section removed | `tests/unit/test_config.py::test_nfr10_demo_env_requires_table_cognito_and_origin_vars`, `tests/unit/test_env_contract.py`, `tests/unit/test_submission_kit.py::test_br07_product_feedback_has_five_questions_per_tool` |
| HANDOFF and architecture docs still showed S3, `/api/admin`, CDK and the Ops page (deb-inputs 4, 21 Oct) | HANDOFF decisions 3, 12, 13, 14 updated and decision 20 added; `interactions.md` marks 15, 16 and Flow E as not in this release, and routes arrow 20 to DynamoDB and Cognito; the SVG dims S3 and reroutes arrow 20, and the PNG is re-rendered from it | — |
| On AWS with Amazon Nova 2 Lite (Haiku blocked by a Marketplace payment error, 23 Oct), CONSENT_REQUIRED was answered with the model's own "say yes", so no consent action was pending and the user looped; bare greetings got "Sorry, I can't understand" | The system prompt sends CONSENT_REQUIRED straight to `prepare_action` (CONSENT_STORAGE or CONSENT_SHARING), forbids asking for a yes itself, and says how to answer a bare greeting. A deterministic greeting command was deferred: about 20 test and E2E inputs use "hello" as a model turn | `tests/unit/channel/test_prompt_time.py::test_prompt_routes_consent_required_to_prepare_action_and_answers_greetings` |
| The prompt fix alone did not stop the consent loop with Nova 2 Lite (23 Oct). Deb's decision: naming an appliance should save it, with no separate permission turn | Judge households J1–J3 are seeded with storage consent GRANTED, as after assisted setup (FR-01), with an auditable seed consent record. Replaces G1-2 (judges start from consent). Sharing stays unasked; it is not enforced and the booking read-back says what is shared. The consent code path stays for households without consent | `tests/unit/test_seed.py::test_seed_local_is_idempotent_and_matches_brd_12_1`; `make e2e` 12 passed against a rebuilt container |

Gates: `make lint` clean (188 files); `make test` 380 passed; `make e2e` 12 passed; `GET /auth/callback` returns 200 on the rebuilt container.
