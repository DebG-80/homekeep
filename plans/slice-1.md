# Plan: Slice 1, store, security, domain core and seed (from intent/homekeep.md; TDD §4.1, §4.5, §5.5, §6, §7, §9; BRD §4, §7, §8, §12.1)

## Context

Slice 0 is merged to `main` (dd23533): the infra contract, the scaffold, CI and the submission kit. HANDOFF §6 Slice 1 builds the layers that every MCP tool (Slice 2) and the booking flow (Slice 3) stand on:
- `store/`: keys, conditional and transaction helpers, operation keys.
- `security/`: JWT verification with a local test issuer, membership, grants, `authorize`.
- `domain/` core: household and consent, appliances, issues, observations, events, clock, state maps.
- Seed fixtures.

The key tests are AT-01, AT-02, AT-03, AT-06 and AT-07 at domain level, plus cross-tenant denial.

**Schedule.** Today is 16 Oct; the internal target is 20 Oct and the deadline 23 Oct 12:00 PDT. Slice 1 has to land by about 17 Oct to leave room for Slices 2–4. If it runs long, the in-slice cut is the service-request and appointment state maps (§7.2): they move to Slice 3, where they are first used.

## Decisions taken in planning (16 Oct 2026, Deb)

| # | Decision | Deviation from |
| --- | --- | --- |
| P1-1 | **Scope for Slices 1–4 is the BRD §3.3 minimum coherent release.** That path is: register → report → guide or escalate → approved demo booking → resume → change → completion → customer confirms → history, plus the unknown-model and verified-model paths. Every integrity and authorisation control stays. Deferred unless time remains: FR-19 reminders, FR-04 documents and the S3 flow, the Ops page, the formal AT-29 load run, `evals.yml` and `smoke.yml`. Slice 1 keeps its full domain core. | HANDOFF decision 1 (full H scope) and §6 Slice 4 content |
| P1-2 | **All seeding lands in Slice 1:** fixture data, local table creation plus a loader for DynamoDB Local (`make seed`), and `scripts/seed.py --target aws` for Deb. The AWS target creates the Cognito users and then their memberships. It is tested with moto only. | TDD §11.5 step 3 timing (implied Slice 4) |
| P1-3 | **`CLOCK_OVERRIDE` is allowed when `ENV` is `local` or `test`**, and still refused in `demo` (fail-fast at startup is kept). Clock-dependent E2E (AT-13 expiry, AT-34 rollover) then runs against `make run`. This closes Slice 0 open item 4. | TDD §4.5 ("only when `ENV=test`"); Slice 0 G-3; CLAUDE.md invariant 10 wording |

These go into `docs/HANDOFF.md` §1 as rows 16–18, into contract §9 and §16, and into CLAUDE.md invariant 10 (the text becomes "only when `ENV` is local or test; never in demo"). The TDD stays read-only.

### Gaps found, with the proposed handling (approving this plan accepts them)

- **G1-1 Judge passwords.** TDD §9.2 says "temporary passwords". A temporary Cognito password forces a password change at the first sign-in, which is friction for judges. Proposal: judge and staff demo accounts get a **random permanent password** (`AdminSetUserPassword Permanent=true`), printed once to the operator's terminal and never written to a file (HANDOFF §4). QA identities on `test` work the same way. A re-run keeps existing passwords unless `--reset-passwords` is passed.
- **G1-2 Judge households start empty.** J1–J3 are seeded with an owner and **no storage consent and no appliances**, so a judge walks the §3.3 path from consent onwards. Household A (BRD §12.1: two ACs, a fridge and a TV) is seeded with storage consent recorded. Household B has its own consent and a different appliance.
- **G1-3 Model verification waits for the catalog.** FR-03 verification needs a published catalog model (TDD §4.5), so `verify_model` lands in Slice 2. Slice 1 stores model and brand claims as `USER_REPORTED`, with per-field provenance and conflicts kept.
- **G1-4 Nickname clash code.** A duplicate nickname returns `INVALID_INPUT` with reason `DUPLICATE_NICKNAME` and the existing appliance's reference, so the agent can ask for a clarified name. `RECORD_CONFLICT` stays reserved for version and idempotency conflicts.
- **G1-5 Local issuer is test-only in this slice.** `security/local_issuer.py` (RSA key, JWKS, minting) is used by tests now. Wiring it into HTTP for `ENV=local` happens in Slice 2, behind a hard refusal in `demo`.
- **G1-6 `make run` seeds itself.** `make run` runs the local seed after `compose up --wait`, so the stack comes up with its table and fixtures. Table creation is not done in the app lifespan, which would break `test_healthz_returns_ok_without_aws_calls`.
- **G1-7 Domain layer is synchronous.** It uses boto3 directly. Slice 2 tools will call it through `anyio.to_thread` (TDD §4.4 and §11.3: blocking calls run in the thread pool).

## Prerequisites (Deb)

1. `git checkout -b slice-1` from `main`.
2. Save this plan as `plans/slice-1.md` and commit it before any code (Claude saves the file after approval; Deb commits).

## Requirements covered

- **FR-01** consent gate (AC1, AC2)
- **FR-02** registration (AC1, AC2)
- **FR-03** resolve, aliases, clarification, provenance (AC1; AC2 partial per G1-3)
- **FR-05** (AC1, AC2)
- **FR-06** domain level (AC1, AC2)
- **FR-20-AC1**; revocation enforced on the next request (the domain half of AC2)
- **FR-28** partial: an event on every mutation, typed errors
- **NFR-04**, **NFR-05**
- **AT-01, AT-02, AT-03, AT-06, AT-07** (domain level); cross-tenant denial
- **Invariants** 1, 4, 5, 8 (state map), 9, 10

## Files that change

**Store** (`app/store/`)
- `keys.py`: key builders for every TDD §6.1 item used in this slice (`HH#`, `META`, `MEMBER#`, `USER#`, `CONSENT#`, `APPL#`, `NICK#`, `ISSUE#…#OBS#`, `OP#`, `EVT#`), plus GSI1 helpers.
- `table.py`: a thin DynamoDB client wrapper:
  - `TypeSerializer`/`TypeDeserializer`;
  - `get`, `query_prefix`, `put_new` (`attribute_not_exists`), `update_versioned` (`version = :expected`);
  - `transact(items)`, which maps `ConditionalCheckFailed` and `TransactionCanceledException` reasons to a conflict.
  - It takes `endpoint_url` from `DYNAMODB_ENDPOINT_URL` (local only).
- `schema.py`: table definition taken from contract §3 (PK/SK strings, GSI1 with projection ALL, TTL `ttl`, on-demand). `ensure_table()` is used only for local and moto, never on AWS.
- `ops.py`:
  - `canonical_json`;
  - `operation_key(household, turn_id, action, args)` = `sha256(household|turn_id|action|canonical_json(args))` (TDD §5.5);
  - `OP#` items with the payload hash and a stored result, TTL 14 days;
  - replay returns the stored result; the same key with a different payload returns `RECORD_CONFLICT`.

**Security** (`app/security/`)
- `tokens.py`: `AccessTokenVerifier`:
  - RS256 only;
  - checks `iss`, `token_use=access`, `client_id` ∈ allowed, required scope, `exp`;
  - JWKS comes from an injectable source with a cache (Cognito URL from `Settings.cognito_jwks_url`).
- `local_issuer.py`: RSA key pair, JWKS document and `mint(sub, scopes, client_id, groups, …)`, for tests (G1-5).
- `actor.py`: `Actor`: `sub`, kind (household or staff), `household_id`, role (OWNER or HELPER), grants (`view`, `edit`, `book`, `updates`), staff groups, status.
- `membership.py`: `resolve_actor(claims)`:
  - reads `USER#{sub}` → `HH#{hh}`, then `MEMBER#{sub}`, **on every call**;
  - a revoked or missing membership with no staff group gives `AUTH_DENIED`;
  - more than one household gives `AUTH_DENIED`.
- `authz.py`: `authorize(actor, action, resource)`, a rules table taken from the BRD §4 matrix and the grant flags. It covers the actions in this slice: household read, consent record (owner only), appliance read/register/update, issue report/read, observation record and event read.

**Domain** (`app/domain/`)
- `errors.py`: `DomainError` with codes from TDD §5.5 plus `CONSENT_REQUIRED`, a reason, a customer-safe message and the correlation ID.
- `context.py`: `OperationContext` (actor, correlation_id, turn_id, session_id, clock) and the result envelope (`status`, `correlation_id`, `version`, `data` | `error`), per the `mcp-tool-contract` skill.
- `clock.py`: `Clock` protocol, `SystemClock`, `FixedClock`, `clock_from_settings` (P1-3), and Asia/Kolkata helpers (`local_date`, the next local midnight).
- `ids.py`: opaque random IDs.
- `state.py`:
  - the issue map `from × event → (to, guard)` from BRD §7.1 (`VISIT_COMPLETED` → `AWAITING_CUSTOMER`; only a customer answer gives `RESOLVED`);
  - the service-request and appointment maps from §7.2, as data (the in-slice cut if time runs short);
  - an undefined transition raises `INVALID_INPUT`.
- `household.py`:
  - `get_household`;
  - `record_consent(purpose STORAGE|SHARING, decision, version)`; declining `SHARING` creates no grant;
  - the storage-consent gate: `META.storage_consent` is denormalised and checked with a `ConditionCheck` inside each persistence transaction.
- `appliances.py`:
  - `register_appliance` is one transaction: `APPL` + `NICK#` sentinel + `OP` + `EVT` + consent check.
  - `resolve_appliance` matches nickname, aliases (`fridge`, `TV`) and room, and returns 0, 1 or many matches without mutating.
  - `update_appliance_fact` sets `{value, status, provenance}`, keeps conflicts and checks `expected_version`.
- `issues.py`:
  - `report_issue` keeps the original wording and the summary. If an active issue exists it returns `NEEDS_CHOICE` unless `continue_issue_id` or `confirmed_distinct` is given. It is idempotent through `ops`.
  - `get_issue`.
  - `transition` goes through `state.py`.
  - The `safety_flag` field is orthogonal to status.
- `observations.py`:
  - `record_observation(field, value | UNKNOWN, expected_version)` validates the field against the intake definition;
  - `next_intake_question(issue)` skips answered and skipped fields (AT-07).
- `events.py`: builds the `EVT#{appliance or -}#{ts}#{id}` item (correlation ID, actor, role, action, result, prior and new version, provenance label). It is appended in the same transaction as every mutation. Also `list_events(appliance)`.

**Catalog content**
- `catalog_data/intake/ac.json`: AC intake fields (onset, airflow, displayed code, and so on), each with an approved question written under the `elder-voice-copy` rules (at most two sentences and one question; "not sure" is accepted). Hazard handling stays in Slice 2 (`hazards.json`).

**Fixtures and seed**
- `fixtures/households.json`:
  - Household A per BRD §12.1: two ACs in different rooms, a fridge and a TV; owner, view-only helper, booking helper and revoked helper.
  - Household B.
  - J1–J3 (`resettable`), per G1-2.
- `fixtures/identities.json`: fixture keys mapped to role, groups and household. Staff: assigned technician, unassigned technician, coordinator, catalog reviewer, admin.
- `fixtures/PROVENANCE.md`: all data is synthetic.
- `scripts/__init__.py`, `scripts/seed.py`:
  - `--target local`: `ensure_table` on DynamoDB Local, then fixtures with deterministic local subs.
  - `--target aws --env test|demo`:
    1. look up or create the Cognito users;
    2. add them to groups;
    3. read each `sub`;
    4. write the DynamoDB items idempotently;
    5. print the credentials once (G1-1).
  - The AWS target refuses to run without an explicit `--env`. **Claude never runs the AWS target; Deb does.**
- `Makefile`: new `seed` target (local); `run` calls it after `compose up --wait` (G1-6).

**Config (P1-3)**
- `app/config.py`: the `CLOCK_OVERRIDE` guard becomes "refused only when `ENV=demo`".
- `tests/unit/test_config.py`, deliberately changed by decision P1-3:
  - `test_inv10_clock_override_rejected_outside_test_env` becomes `test_inv10_clock_override_rejected_in_demo_env` (demo is still refused, at load and at startup);
  - add `test_inv10_clock_override_accepted_in_local_env`.

**Docs**
- `docs/infra-contract.md`:
  - §9: the `CLOCK_OVERRIDE` row.
  - §14: judge credentials come from the Slice 1 seed; the operator needs `cognito-idp:AdminCreateUser`, `AdminGetUser`, `AdminSetUserPassword`, `AdminAddUserToGroup` and DynamoDB write access with their own admin credentials, not the task role.
  - §16: the G-3 row is updated by P1-3.
- `docs/HANDOFF.md`: rows 16–18.
- `CLAUDE.md`: invariant 10 wording; add `make seed` to Commands.
- `README.md`: `make seed`, and the AWS seed command for Deb.

**Tests** (moto for DynamoDB and Cognito; no Docker needed): `tests/unit/store/`, `tests/unit/security/`, `tests/unit/domain/`, `tests/unit/test_seed.py`, plus a shared fixture in `tests/conftest.py` that builds a moto table and a seeded store.

## Order of work

1. Decision records (HANDOFF rows, CLAUDE.md invariant 10, contract §9/§16). For P1-3, change the config tests first, see them fail, then change the guard.
2. **`store/` with its tests (riskiest).** Prove `put_new`, `update_versioned`, transaction cancellation mapping and `ops` replay/conflict against moto.
3. `domain/clock.py`, `ids.py`, `errors.py`, `context.py`, `state.py`, with tests.
4. `security/`: tokens and local issuer, membership, authz, with tests.
5. Domain services (household and consent → appliances → issues → observations → events) and `intake/ac.json`. Write the AT tests first.
6. Fixtures and `scripts/seed.py` (local, plus AWS under moto); the Makefile `seed` and `run` changes.
7. Docs: README and contract.
8. `make lint`, `make test`; `make run` (the seed runs on real DynamoDB Local, which exercises real conditions and transactions); `make stop`. Then the `verifier`, then the `reviewer`.

## Risks

- **moto fidelity for conditions and transactions (step 2).** moto may differ from DynamoDB on cancellation reasons. Mitigation: the error mapping reads only `CancellationReasons[].Code`, and `make run` runs the seed against the real DynamoDB Local engine. If they differ, fix the code and add a regression test.
- **Slice size against the schedule.** Cut order inside the slice: §7.2 maps → Slice 3; then `list_events` → Slice 3 (history). AT tests, authz and the consent gate are never cut.
- **The seed script touches real AWS.** Only Deb runs `--target aws`; Claude's tests use moto with dummy credentials. Passwords go to stdout once and never to files or logs (invariant 9).
- **Local issuer misuse.** It is not wired into any route in this slice. Slice 2 must refuse it when `ENV=demo` (G1-5).
- **Changing a Slice 0 Proof test.** This is deliberate under P1-3. The replacement test keeps the `demo` refusal, so G-3's protection of `demo` is unchanged.
- **P1-1 knock-on.** Contract §9 still requires `BUCKET_NAME` in test and demo. If FR-04 is dropped for good, a later plan makes it optional. No change now.

## Proof

`make test` must pass, including:
- **Store**
  - `tests/unit/store/test_keys.py::test_keys_match_tdd_6_1_layout`
  - `tests/unit/store/test_schema.py::test_table_definition_matches_infra_contract` (PK/SK/GSI1/`ttl` parsed from contract §3)
  - `tests/unit/store/test_table.py::test_nfr05_put_new_rejects_existing_item`, `::test_nfr05_stale_version_update_returns_record_conflict` and `::test_nfr05_cancelled_transaction_maps_to_record_conflict`
  - `tests/unit/store/test_ops.py::test_inv5_operation_key_is_server_derived_and_canonical`, `::test_inv5_replay_returns_stored_result` and `::test_inv5_same_key_different_payload_returns_record_conflict`
- **Security**
  - `tests/unit/security/test_tokens.py::test_nfr04_valid_access_token_accepted`, `::test_nfr04_rejects_bad_issuer_expired_id_token_wrong_client_missing_scope` (parametrised) and `::test_nfr04_rejects_none_and_hs256_algorithms`
  - `tests/unit/security/test_membership.py::test_inv1_household_comes_only_from_membership_lookup` and `::test_fr20_revoked_member_denied_on_next_request`
  - `tests/unit/security/test_authz.py::test_fr20_ac1_view_only_helper_cannot_edit_or_book` and `::test_brd4_permission_matrix` (parametrised)
- **Domain**
  - `tests/unit/domain/test_cross_tenant.py::test_nfr04_household_b_cannot_read_or_mutate_household_a` (every domain entry point in this slice)
  - `tests/unit/domain/test_household.py::test_at01_consent_then_nickname_creates_usable_appliance_with_unknown_fields`, `::test_at02_declining_sharing_creates_no_grant_and_use_continues` and `::test_fr01_ac2_no_storage_consent_returns_consent_required`
  - `tests/unit/domain/test_appliances.py::test_at03_fridge_and_tv_aliases_resolve`, `::test_at03_two_acs_require_room_clarification_without_mutation`, `::test_at03_duplicate_nickname_never_overwrites`, `::test_fr02_ac2_replay_returns_same_appliance` and `::test_fr03_user_reported_model_stays_unverified_and_conflicts_kept`
  - `tests/unit/domain/test_issues.py::test_at06_replay_yields_one_issue`, `::test_at06_confirmed_distinct_symptom_creates_second_issue`, `::test_fr05_active_issue_requires_choice`, `::test_inv8_technician_completion_never_resolves` and `::test_undefined_transition_raises_invalid_input`
  - `tests/unit/domain/test_state.py::test_issue_map_matches_brd_7_1` and `::test_service_and_appointment_maps_match_brd_7_2`
  - `tests/unit/domain/test_observations.py::test_at07_skipped_and_answered_fields_not_reasked_after_restart`, `::test_fr06_unknown_answer_recorded_without_invented_value` and `::test_nfr05_stale_expected_version_returns_record_conflict`
  - `tests/unit/domain/test_events.py::test_fr28_every_mutation_appends_one_event_with_correlation_and_versions`
  - `tests/unit/domain/test_clock.py::test_inv10_utc_storage_and_kolkata_midnight_rollover`
  - `tests/unit/domain/test_intake_copy.py::test_intake_questions_follow_elder_voice_rules`
- **Seed**
  - `tests/unit/test_seed.py::test_seed_local_is_idempotent_and_matches_brd_12_1`, `::test_seed_aws_creates_cognito_users_groups_and_memberships` (moto) and `::test_inv9_passwords_printed_once_never_written_and_fixtures_synthetic`
- **Config**
  - `tests/unit/test_config.py::test_inv10_clock_override_rejected_in_demo_env`, `::test_inv10_clock_override_accepted_in_local_env`; every other Slice 0 Proof test unchanged

`make lint`: zero findings.

**Local check:** `make run` (which seeds), then a scripted boto3 query against `localhost:8001` shows Household A's appliances and the membership items. A second `make seed` changes nothing. Then `make stop`.

**Verifier:** PASS. **Reviewer:** findings listed for Deb.

**Manual for Deb** (not a gate): after provisioning the test stack, run `uv run python -m scripts.seed --target aws --env test`, keep the printed credentials in a password manager, and sign in once through Cognito managed login.

## Out of scope

- MCP server, tools, PRM/auth middleware, attestation, orchestrator, fake model, catalog guidance and hazards, `verify_model` (Slice 2).
- Approvals, provider simulator, service requests in use, staff API, resolution and reopen flows, history read API (Slice 3).
- Web client, reset/purge/admin CLI, and the items P1-1 defers (Slice 4 or not at all).
- Logging/redaction helpers (first used in Slice 2).
- Any AWS resource creation; running the seed against AWS; commits and pushes.

## Implementation deviations and notes (recorded during implementation, 16 Oct 2026)

| # | Plan said | Implemented | Why |
| --- | --- | --- | --- |
| D1-1 | Files listed per module | Added `app/domain/mutations.py` | Every write follows the same steps: server-side operation key, replay lookup, then one transaction that includes the `OP#` record (with a concurrent-duplicate fallback) and the consent ConditionCheck. One helper keeps that identical across services. |
| D1-2 | Shared fixtures in `tests/conftest.py` | Also `tests/unit/domain/conftest.py` and `tests/unit/domain/world.py` | The domain tests share actors, households and per-call contexts. A plain module is importable by tests, which a conftest is not. |
| D1-3 | Issue map from BRD §7.1 | `SERVICE_PENDING` + hazard **stays** `SERVICE_PENDING` (it gains only the safety flag); other unresolved states go to `SERVICE_NEEDED` | The BRD row says "→ SERVICE_NEEDED … preserve any valid booking". Moving a confirmed booking's issue to `SERVICE_NEEDED` would make its later `VISIT_COMPLETED` an undefined transition. TDD §7 ("restricts guidance even when an appointment is pending") supports keeping the status. |
| D1-4 | `events.py` event IDs: opaque random | Event IDs start with the real wall-clock nanoseconds and a process counter, then a random suffix | **Bug found by `test_fr28_…`:** under a fixed clock (`CLOCK_OVERRIDE`, now allowed in local by P1-3) every event shares a timestamp, so history order was random. The tiebreaker ignores the overridden clock. |
| D1-5 | — | `record_observation`'s `expected_version` is the saved answer's own version (`None` for a first answer) | TDD §5.4 does not say whose version it is. Per-answer versions let answers to different questions proceed independently once triage has started. While the issue is still `OPEN`, two concurrent *first* answers both try to move it to `TRIAGING`, so one gets `RECORD_CONFLICT` and is retried (wording corrected after review). The first saved answer also moves the issue `OPEN` → `TRIAGING` in the same transaction (BRD §7.1, "assistant starts approved intake"). |
| D1-6 | — | Store raises `ConflictError`, a subclass of `DomainError` (`RECORD_CONFLICT`) carrying `failed_indexes`; services map an index to a specific error (consent → `CONSENT_REQUIRED`, nickname sentinel → `DUPLICATE_NICKNAME`) | Keeps the store generic while the domain still gives precise errors. |
| D1-7 | Order of work step 5: "Write the AT tests first" | The services were written first, then the AT tests | A process slip. To compensate, every AT test asserts on stored items (scans and snapshots) rather than only on return values. Two tests caught real problems: D1-4, and a wrong expectation of mine (below). |
| D1-8 | `.env.example` not listed | Its `CLOCK_OVERRIDE` comment now says "local or test only" | Keeps it consistent with P1-3. |

Notes:
- **Same turn, different arguments, is a different operation.** TDD §5.5 builds the key from the arguments too, so one turn can register two appliances. A test of mine first expected `RECORD_CONFLICT` there. The test was wrong and was corrected; the code follows the TDD. The "same key, different payload" conflict is covered at store level (`test_ops.py`) and matters for keys that exclude the payload, such as Slice 3's `execute_action`.
- **Demo seed set:** `--env demo` gets J1–J3, one technician (`hk-tech-1`) and one coordinator (TDD §9.2). `--env test` gets every identity.
- **Real-engine check:** `make run` seeded DynamoDB Local (35 items), and a second `make seed` created 0. A scratch script ran against DynamoDB Local and showed the same results as moto, so the moto-fidelity risk is retired: transaction cancellation indexes `(1,)`, `CancellationReasons` present, stale version → `STALE_VERSION`, consent gate → `CONSENT_REQUIRED`, duplicate nickname → `DUPLICATE_NICKNAME`, and intake resuming at `airflow`.
- **Extra tests beyond Proof:** `test_table.py::test_round_trip_keeps_types`, `test_clock.py::test_inv10_clock_override_drives_the_clock`, `test_seed.py::test_local_target_refuses_non_local_endpoints`.
- Contract §14.1 (how to run the AWS seed, and the operator permissions it needs) and a §15 tick box were added under the plan's "§14" item.

## Review fixes (16 Oct 2026)

The `reviewer` subagent found no Critical issues. Deb chose to fix R1–R4 and the seed-target nit now, accept D1-3, and leave the other nits for Slice 2. Each fix started with a regression test that was confirmed to fail for the reported reason.

| # | Finding | Fix | Regression test |
| --- | --- | --- | --- |
| R1 | Repeating a verified (or document-backed) value downgraded it to `USER_REPORTED` | A strong value stands; only a different, known claim is recorded, as a conflict; an equal value or "not sure" changes nothing | `test_appliances.py::test_fr03_repeating_or_unknown_claim_never_downgrades_verified_value` |
| R2 | A retry that read the ledger just before the original committed could trip over the original's own write and give the wrong answer (`DUPLICATE_NICKNAME`, `STALE_VERSION` or `NEEDS_CHOICE`). This affected **every** mutation, not only nicknames | New `mutations.run`: if a service body raises, or returns without committing, it reads the ledger again and replays the original's stored result. All six services now go through it | `test_mutations.py::test_inv5_retry_racing_the_original_commit_replays_for_every_mutation`; `::test_inv5_commit_returns_stored_result_when_a_duplicate_committed_first` covers the commit fallback that was untested |
| R3 | Under a fixed clock, a second consent decision for the same purpose collided on its key and failed with a raw conflict | Consent SK is `CONSENT#{purpose}#{ts}#{ordered_id}` (the TDD §6.1 prefix is unchanged); `ordered_id` moved to `domain/ids.py` and is shared with events; `record_consent` maps conflicts to `RECORD_CONFLICT/STALE_VERSION` | `test_household.py::test_fr01_consent_can_change_twice_at_one_fixed_instant` |
| R4 | The AWS seed printed passwords only after everything succeeded, so a failure lost them; the only recovery rotated every password | Each password is printed the moment Cognito holds it (right after create, before it is made permanent). A preflight checks the table, the pool and the groups before creating anyone. `--reset-passwords [USERNAME ...]` rotates only the named users | `test_seed.py::test_seed_aws_prints_each_password_before_any_later_failure`, `::test_seed_aws_preflight_refuses_before_creating_users`, `::test_seed_aws_resets_only_named_users` |
| Nit (seed target) | The AWS target never showed or confirmed what it would write to | It prints the account, region, pool name and ID, table and env, and writes nothing without `--yes`. It refuses unless the table and pool names end in `-{env}` (contract §2) | `test_seed.py::test_seed_aws_main_shows_target_and_requires_yes_and_env_names` |
| D1-3 | The SERVICE_PENDING + hazard interpretation was not mirrored in HANDOFF | Accepted by Deb; HANDOFF row 19; the state-map test now labels it as an accepted interpretation | — |

Two existing seed tests changed mechanically because the seed API changed: `out=` is passed to `seed_aws` (passwords now print there), and `reset=[]` replaces `reset_passwords=True`. Their assertions are unchanged.

Open for Slice 2 (reviewer nits, not fixed now):
- The first intake answer's `OPEN → TRIAGING` change has no event of its own.
- `RemoteJwks` timeout and outage mapping (use about 3 s; report a distinct reason for connection errors).
- Per-reason customer messages for `INVALID_INPUT` and a rule test for `CUSTOMER_MESSAGES`.
- "Not sure" can wipe an earlier user-reported value.
- Events are written with an unconditional put; `put_new` would enforce append-only at store level.
- The duplicate-issue race in `report_issue` (no active-issue sentinel).
- `resolve_actor` raises `ValueError` rather than `AUTH_DENIED` on a malformed role or grant.
- `test_inv9` only proves "never written" for the working directory.
- Fixture IDs are readable, not opaque.
- A second hazard overwrites `safety_reason`.
