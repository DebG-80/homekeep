# Plan: Slice 3, approvals, demo booking, staff surface, resolution and history (from intent/homekeep.md; TDD §3.4 F2–F3, §4.3, §4.5, §4.6, §4.10, §5.3–5.5, §6.1–6.2, §7; BRD FR-11–FR-18, FR-27, §7.1–7.3)

## Context

Slices 0–2 are committed on `slice-2`. That covers the scaffold, the domain core, the MCP server with customer tools, guidance, the agent and the turn pipeline. Slice 3 delivers the second half of the BRD §3.3 path:
- draft a service request and capture the address and contact route by voice;
- list demo slots;
- a server-authored read-back, and a spoken "yes" checked by **deterministic code**;
- a booking that is confirmed (or honestly pending) only by the provider simulator;
- resume, reschedule and cancel;
- technician completion in the staff API, then the customer's own answer, close and reopen;
- the appliance history.

It also closes the Slice 2 deferrals: consent by voice (G2-4), `verify_model` and staff clearing of safety flags and holds (G2-1, R3), and attestation bound to the tool (a Slice 2 open item).

Key tests (HANDOFF §6): AT-12 to AT-19, AT-34, AT-35.

**Schedule (explicit risk).** It is 16 Oct; the internal target is 20 Oct and the deadline 23 Oct 12:00 PDT. Deb chose the fuller option on all three planning questions: the reconciliation sweep, the full staff surface and voice capture of the address. With them Slice 3 is the largest slice, and Slice 4 (web client, voice, video) still follows. **The 20 Oct internal target is unlikely; the 23 Oct deadline is still achievable only if Slice 3 lands by about 19 Oct.** In-slice cut order, should Deb call it: (1) manual-review resolve endpoint → (2) staff reassignment → (3) the sweep (fall back to reconciling on read). Approvals, the approval guard, booking integrity, outcome templates and AT-19 are never cut.

## Decisions taken in planning (16 Oct 2026, Deb)

| # | Decision | Deviation from |
| --- | --- | --- |
| P3-1 | **Build the 60 s reconciliation sweep** as well as reconcile-on-read (`get_service_status`, `get_context`). An in-process task in the app lifespan queries GSI1 `PENDING` and reconciles each request with a per-household `SYSTEM` actor that may only reconcile. | — (TDD §4.6) |
| P3-2 | **Full staff surface** per TDD §4.10:<br>- queue (technician: own; coordinator: all);<br>- case view with personal fields masked unless the role needs them;<br>- visit and provider events;<br>- assignment changes;<br>- `NO_SHOW` exception;<br>- the manual-review queue (list and resolve);<br>- clearing safety flags and holds;<br>- `verify-model`.<br>The Ops page stays deferred under P1-1. | — (TDD §4.10) |
| P3-3 | **Address and contact route captured by voice** through a new customer tool `record_service_details` (it is not in TDD §5.4, so it is added here under the `mcp-tool-contract` skill). Values are stored USER_REPORTED on the household, copied into the request snapshot, and read back in full only in the booking read-back. They are never logged. | TDD §5.4 tool catalogue (new tool) |
| P3-4 | **One implementation pass**, as P2-1 did: build 3a (booking core), run the `make lint`/`make test` checkpoint, build 3b (staff surface, sweep, resolution, history), then the verifier and the reviewer once, and Deb commits once. | — |

### Gaps found, with the proposed handling (approving this plan accepts them)

- **G3-1 Opaque reference lookups for staff.** Staff are not tenants, but invariant 1 forbids any API from taking a household ID. Records staff act on get a global lookup item, `REF#{opaque_id} / META → {household_id, kind}`, written in the same transaction as the record. This covers service requests (cases), issues, appliances and safety holds. Staff routes take the opaque ID and resolve it themselves. This needs a small change in the existing `register_appliance`, `report_issue` and seed paths.
- **G3-2 GSI1 use.** A service request item carries `GSI1PK = PENDING` while it is pending (for the sweep) and `ASSIGNEE#{sub}` otherwise (the technician queue). Its `REF#` item carries `GSI1PK = CASE` (the coordinator queue). Flagged issues and household holds carry `GSI1PK = SAFETY` on their `REF#` items (the coordinator's safety list). While a request is CHANGE_PENDING or CANCEL_PENDING it leaves the technician's queue; the coordinator still sees it.
- **G3-3 Auto-assignment.** A confirmed demo booking is assigned to the seeded demo technician. The seed writes `PROVIDER#demo / CONFIG` with that technician's `sub` (Cognito-assigned on AWS, `local-tech_assigned` locally). Coordinators can reassign (P3-2).
- **G3-4 Virtual slot inventory.** Slots are generated for any date: 10:00–13:00 and 14:00–17:00 Asia/Kolkata, the next 7 days, capacity 2 (1 on the second day, so AT-15 has a contested last slot), with an illustrative fee of ₹499 marked ESTIMATE. Taking a slot is a conditional counter on `PROVIDER#demo / SLOT#{date}#{window}`, so nothing needs pre-seeding and the slots never run out before 20 Nov. An offer expires 10 minutes after listing.
- **G3-5 The read-back timing travels with `confirm_action`.** The channel passes `readback_completed_at`, `speech_started_at` and `channel` (`voice` or `text`). The domain re-checks expiry, the payload hash against current records, the grant and, for voice, that speech began after playback. No extra tool is added. Text approvals apply rules 1, 4 and 6 only, and are recorded as `channel=text` (never a voice pass, FR-21-AC2).
- **G3-6 Consent by voice** (closes G2-4): `prepare_action(CONSENT_STORAGE | CONSENT_SHARING)` is allowed before storage consent exists. Its read-back is the approved consent text, and `execute_action` calls `record_consent`.
- **G3-7 Reopen** goes through `report_issue(continue_issue_id=<closed issue>)` → `RECURRED` (OPEN). Prior visits and events are untouched. No new tool.
- **G3-8 Attestation is bound to the tool and its arguments.** The MAC input becomes `sub|session|turn|tool|sha256(canonical args)|ts`, which closes the Slice 2 open item before `confirm_action` and `execute_action` exist.
- **G3-9 Sessions are bound to their member.** `load_session` refuses another member's session (`NOT_FOUND`), closing that Slice 2 open item. The approval is also bound to the actor and the session.
- **G3-10 `UNAVAILABLE`** (the provider is down at submission) is a definitive failure, so the request becomes FAILED. The elder hears that it didn't go through and is offered to try again; a new request is linked to the issue (BRD §7.2: terminal states stay terminal).

## Prerequisites (Deb)

1. `git checkout main && git merge slice-2` (local; no push needed).
2. `git checkout -b slice-3`.
3. Save this plan as `plans/slice-3.md` and commit it before any code.

## Requirements covered

- **FR-01** (consent by voice)
- **FR-03** (verify-model)
- **FR-11 to FR-18**
- **FR-27** (fee and warranty representation)
- **FR-28** (correlation through approval, dispatch and reconciliation)
- **NFR-04**, **NFR-05**, **NFR-08**
- **AT-12 to AT-19**, **AT-34**, **AT-35**
- **Invariants** 1–8 and 10

## Phase 3a: booking core

**Provider simulator** (`app/provider/`)
- `simulator.py`: the only adapter. It provides:
  - `list_slots`, the virtual inventory (G3-4);
  - `submit(op_key, slot)`, de-duplicated by operation key (`REQ#{op}` stores the result, AT-14);
  - `replace(op_key, old, new)`, `cancel(op_key)` and `status(op_key)`.
- `faults.py`: the admin-only `PROVIDER#demo / FAULT` item, one-shot or N-shot and per household, honoured only when `FAULTS_ENABLED`. Faults: `CONFIRM`, `ACK_ONLY`, `TIMEOUT_AFTER_SUCCESS`, `REJECT`, `UNAVAILABLE`, `FEE_CHANGE`, `REPLACE_FAIL`, `CANCEL_REFUSE`, `CANCEL_TIMEOUT`. `DUPLICATE_EVENT`, `STALE_EVENT` and `NO_SHOW` are exercised through staff events. Tests write the item directly; the admin API stays deferred under P1-1.

**Domain**
- `app/domain/service.py`:
  - `draft_service_request` reuses an open request for the issue, moves OPEN or TRIAGING issues to SERVICE_NEEDED, takes a snapshot of the symptoms and checks, sets fee and warranty to UNKNOWN, and returns the missing fields.
  - `record_service_details(field address|contact, value, expected_version)` (P3-3).
  - `list_slots`.
  - `get_service_status`, which reconciles before reading and returns the state, the local date in words, the window and the last-update time.
  - `reconcile(sr)`.
  - `SIMULATION_MODE` is stamped on every request.
- `app/domain/approvals.py`:
  - `prepare_action(kind, request_id?, slot_id?)`: payload hash, record versions, actor, session; expiry is the earliest of 5 minutes, session end or the slot offer's expiry; an earlier PENDING approval in the session is superseded; it returns the server read-back.
  - `confirm_action` (trusted; G3-5): re-checks everything and refuses with `APPROVAL_EXPIRED`, `RECORD_CONFLICT` (changed fee, slot or version) or `AUTH_DENIED`.
  - `execute_action` (trusted): operation key `sha256(approval_id|"execute")`, so it runs once. SUBMIT, RESCHEDULE and CANCEL follow the BRD §7.2 map with persist-before-dispatch (the pending state is written before the provider call). The outcome writes are single transactions:
    - **confirmation:** request, appointment, `ACTIVE` sentinel, issue SERVICE_PENDING, OP record, event, assignment and the `REF` state;
    - **replacement:** the old appointment SUPERSEDED, the new one CONFIRMED, the sentinel swapped;
    - **cancellation:** the appointment CANCELLED and the sentinel cleared; the issue goes back to SERVICE_NEEDED only if no other active booking exists.

    A timeout stays pending with `RESULT_UNKNOWN`. Cancelling or changing while pending queues a MANUAL item instead.
  - `cancel_pending_action` (trusted) now cancels for real.
- `app/domain/history.py`: `get_history(appliance_id)` returns the attributed timeline and a server-built spoken summary.
- `app/domain/issues.py`:
  - `confirm_resolution(issue_id, answer RESOLVED|PERSISTS|UNSURE, close?)`;
  - reopen via `report_issue` (G3-7);
  - REF items written for issues (G3-1).
- `app/domain/appliances.py`: REF items for appliances (G3-1).
- Templates (`app/channel/templates.py`, under `elder-voice-copy`):
  - the booking read-back: provider "HomeKeep Demo Service Desk", the full date in words (Asia/Kolkata), the window, the fee ("an estimated 499 rupees" or "the fee is not known yet"), "warranty not known", the address and contact on file, the data shared, the demo status and "Shall I book it?";
  - the consent read-backs;
  - the outcomes: demo booking confirmed (date, window, provider, "This is a demonstration; no real technician will visit."), pending, requested, rejected, failed, reschedule confirmed or failed with the original kept, cancellation pending, cancelled, cancellation refused;
  - status replies.

**MCP**
- `app/mcp_server/tools.py`: add `draft_service_request`, `record_service_details`, `list_slots`, `prepare_action`, `get_service_status`, `confirm_resolution` and `get_history`; update `names.py` (`CUSTOMER_TOOLS`).
- `app/mcp_server/trusted.py`: `confirm_action`, `execute_action`, and the real `cancel_pending_action`.
- `app/security/attestation.py`: tool and argument binding (G3-8). `app/channel/trusted_client.py` signs the same way.

**Channel**
- `app/channel/approval_guard.py`: TDD §4.3 rules 1–6:
  - one PENDING, unexpired approval;
  - `readback_completed_at` recorded;
  - speech began after playback, in the LISTENING state;
  - the whole utterance matches the affirmative grammar;
  - echo similarity below 0.6;
  - the grant.

  Text applies rules 1, 4 and 6. A negative cancels the pending approval; any other utterance leaves it pending.
- `app/channel/pipeline.py`:
  - T6 between T5 and the cap. An eligible "yes" goes `confirm_action` → `execute_action` through the trusted client, and the outcome template is spoken.
  - Speech precedence gains `prepare_action` → read-back (sets `pending_approval_id`) and `get_service_status` → status template.
  - `TurnRequest` gains `client_state`, `channel` and the timestamps.
  - Session binding (G3-9).
- The output guard stays strict on model text: only server templates ever confirm.

**Seed and fixtures**
- `PROVIDER#demo / CONFIG` (default technician sub).
- `STAFF#{sub}` directory items (role, display name) for assignment.
- REF items for seeded appliances.
- No addresses are seeded (P3-3: captured by voice). Household A gets a synthetic address only so QA can book without dictating one; this can be dropped if Deb prefers.

**Order (3a)**
1. Attestation binding.
2. REF lookups.
3. Provider simulator and faults.
4. Service requests and the address tool.
5. Approvals, prepare, confirm and execute **(riskiest: transactions and hash re-validation)**.
6. The approval guard and T6.
7. Templates.
8. Consent by voice.
9. Checkpoint: `make lint` and `make test`.

## Phase 3b: staff surface, sweep, resolution, history

- `app/staff/api.py` (Cognito groups; the opaque references from G3-1):
  - `GET /api/staff/queue`: technician sees own (GSI1 `ASSIGNEE#`); coordinator sees all (GSI1 `CASE`).
  - `GET /api/staff/cases/{case_id}`: masked personal fields unless the role needs them (the assigned technician sees the address and contact; others see them masked). Demo badge.
  - `POST /api/staff/cases/{case_id}/events` with `event_id` and `expected_version`, for:
    - visit events: `VISIT_STARTED`, `WORK_NOTE`, `VISIT_COMPLETED` (a work summary is required);
    - the coordinator exception: `NO_SHOW` raises a coordinator exception plus a MANUAL item, leaves the request CONFIRMED and the issue unresolved (AT-35);
    - provider events: `PROVIDER_CONFIRMED` and `PROVIDER_REJECTED` for ACK_ONLY requests.

    A duplicate `event_id` returns the original result (one event). An older version is refused and never regresses state (AT-18).
  - `POST /api/staff/cases/{case_id}/assign` (coordinator) and `GET /api/staff/technicians`.
  - `GET /api/staff/manual` and `POST /api/staff/manual/{item_id}/resolve` (coordinator).
  - `GET /api/staff/safety`; `POST /api/staff/issues/{issue_id}/clear-safety` and `POST /api/staff/safety-holds/{hold_id}/clear` (coordinator, with evidence).
  - `POST /api/staff/appliances/{appliance_id}/verify-model` (catalog_reviewer): it must match a published catalog model and cite a document; a mismatch records a visible conflict (FR-03, G2-1).
- `app/domain/staff.py`: the domain entry points behind these routes, each calling an `authorize` extended with staff rules (role, assignment).
- `app/security/authz.py`: staff actions and a `SYSTEM` reconcile action; `ActorKind.SYSTEM`.
- `app/provider/sweep.py`: the P3-1 task, started in the lifespan (`create_app(start_sweep=True)`; tests call `sweep_once`).
- `app/staff/api.py`: 401 vs 403 split (the Slice 2 N1 nit), which also applies to `/api/*`.

**Order (3b)**
1. Staff authorisation and REF resolution.
2. Events (AT-18, AT-19, AT-35).
3. Queue and case view.
4. Assignment.
5. Manual review.
6. Safety clearing.
7. verify-model.
8. The sweep.
9. `confirm_resolution`, reopen and history (AT-19).
10. Final gates.
11. Verifier and reviewer.

## Risks

- **Transaction correctness for booking outcomes (riskiest).** Mitigation: every outcome is one `TransactWriteItems` with conditions on the request version, the `ACTIVE` sentinel and the slot counter; tests run on moto and the local check runs the full journey on DynamoDB Local.
- **Approval-guard false accepts.** Grammar and echo tables are unit-tested; there is a contract test per AT-13 case (silence, background "yes", "yes" during playback, expired approval, corrected date, fresh "yes").
- **The sweep racing a read-path reconcile.** Both are conditional on version, so the loser re-reads (TDD §4.6).
- **Personal data.** Addresses and contacts only in household, snapshot and case items. Never logged (allowlist), masked in staff views unless needed, spoken only in the booking read-back.
- **Scope and schedule.** See Context for the cut order.

## Proof

`make test` must pass, including these key tests (full names are fixed when the tests are written first):
- **AT-12:** `test_service.py::test_at12_unknown_model_draft_and_missing_address_blocks_submission_only`, `::test_fr27_fee_and_warranty_unknown_never_free`.
- **AT-13:** `tests/contract/test_approvals.py::test_at13_silence_background_yes_playback_expired_and_corrected_date_cannot_submit`, `::test_at13_fresh_explicit_yes_books_once`, plus `tests/unit/channel/test_approval_guard.py` (grammar, echo and timing tables).
- **AT-14:** `test_booking.py::test_at14_timeout_after_success_reconciles_to_one_reference` (correlation trail joins approval, dispatch and reconciliation).
- **AT-15:** `::test_at15_last_slot_one_winner_others_get_alternatives`, `::test_at15_fee_change_requires_new_approval`.
- **AT-16:** `::test_at16_failed_reschedule_keeps_original_success_supersedes_once`.
- **AT-17:** `::test_at17_cancel_timeout_pending_refusal_restores_confirmation_cancels_issue_unresolved`.
- **AT-18:** `tests/contract/test_staff.py::test_at18_only_assigned_technician_duplicate_and_stale_events_do_not_regress`.
- **AT-19:** `::test_at19_completion_awaits_customer_still_faulty_reopen_history_intact`.
- **AT-34:** `::test_at34_local_midnight_rollover_and_concurrent_edit_invalidates_approval`.
- **AT-35:** `::test_at35_no_show_stays_unresolved_and_raises_exception`.
- **P3-1 sweep:** `test_sweep.py::test_p3_1_sweep_reconciles_pending_requests_once`.
- **P3-2 staff:** `test_staff.py::test_p3_2_queue_masking_assignment_manual_review_safety_clear_verify_model`.
- **P3-3 address:** `test_service.py::test_p3_3_address_captured_by_voice_never_logged`.
- **G3-6 consent:** `test_approvals.py::test_g3_6_consent_by_voice_unlocks_persistence`.
- **G3-8:** `test_attestation.py::test_g3_8_attestation_bound_to_tool_and_arguments`.
- **G3-9:** `test_sessions.py::test_g3_9_another_members_session_is_not_found`.
- Templates: `test_templates.py` covers every outcome template; confirmation templates contain "demo" and "No real technician will visit".

`make lint`: zero findings.

**Local check** (fake model, scripted turns through the turn API with a `channel=text` "yes"):
1. Consent by voice on J1.
2. Register an AC.
3. Report the problem.
4. Draft the request.
5. Dictate the address and contact.
6. List slots.
7. Hear the read-back.
8. Say "yes" and hear the demo confirmation.
9. Staff `VISIT_COMPLETED`.
10. Answer "it works now", then close.
11. Read the history.

**Verifier:** PASS. **Reviewer:** findings for Deb.

## Out of scope

- The web client, voice capture, Playwright E2E, reset/purge/admin CLI and the admin fault API (Slice 4 or deferred by P1-1).
- The Ops page and token-usage records (deferred by P1-1).
- A real provider adapter (invariant 3); payments.
- AWS resources, real Bedrock calls, `make eval`; commits and pushes.

## Implementation deviations and notes (recorded during implementation, 16 Oct 2026)

Built in one pass per P3-4: 3a, then the checkpoint (`make lint` clean, 295 passed), then 3b. The Proof tests were written before the code for each half.

| # | Plan said | Implemented | Why |
| --- | --- | --- | --- |
| D3-1 | `execute_action` operation key `sha256(approval_id\|"execute")`, recorded as an `OP#` item | Idempotency comes from the approval item itself (state `EXECUTED` plus the stored result), together with the provider's de-duplication by operation key (`{approval_id}:submit`, `:replace`, `:cancel`) | An `OP#` record would freeze an unknown outcome. A `PENDING` or `CANCEL_PENDING` result is not stored, so a retry re-asks the provider, which returns the same record (AT-14). |
| D3-2 | — | `SLOT_UNAVAILABLE` is decided by an availability check *before* anything is persisted; the request stays `DRAFT` and alternatives can be offered | BRD §7.2 has no `DRAFT → FAILED` for a lost slot; AT-15's losers must be able to choose another time on the same request. The provider's conditional counter still decides the real race. |
| D3-3 | `FEE_CHANGE` fault | Consumed by the re-quote in `confirm_action`, which refuses with `RECORD_CONFLICT` (`FEE_CHANGED`, `details.fee_paise`) so a new read-back is needed | AT-15: a changed fee needs a new approval, before anything is sent. |
| D3-4 | — | When the approval guard decides `EXPIRED`, the pipeline speaks `APPROVAL_EXPIRED` instead of passing the turn to the agent | The elder must hear why "yes" did nothing (FR-12). |
| D3-5 | Cancellation wording | Customer templates say the visit was "called off" | Plain words, and "cancel" is one of the STOP command words (`guards.py`), so the elder repeating the outcome back is not mistaken for a new request. Templates are server text; the output guard on model text is unchanged. |
| D3-6 | P3-3: values stored on the household and copied into the snapshot | `record_service_details` writes the request and `META` in one transaction, with one conditional write on `META` (version **and** storage consent) | A DynamoDB transaction may touch an item only once, so the consent check is folded into the `META` condition. |
| D3-7 | Local check: the fake model in `make run` | The journey ran with the real app in-process (uvicorn, MCP, Strands loop) and a scripted model, against the **DynamoDB Local container** from `make run`. The container itself was checked for `/healthz`, the staff queue, 401 without a token and 403 for a household token, and no sweep errors | The container's default fake model only calls `get_context`, so it cannot drive a booking; a scripted model can. |
| D3-8 | 401 vs 403 split for staff routes | A shared `app/http_errors.py` (`status_for`, `bearer`) maps token failures to 401 and every other `AUTH_DENIED` to 403, `RECORD_CONFLICT` to 409; the turn API uses it too | Slice 2 nit N1, applied to `/api/*` as the plan says. A household member without an active membership now gets 403 (was 401). |
| D3-9 | — | `get_context` returns `service_requests` (open ones, pending ones reconciled first) and `pending_approval` for this session | The plan names reconcile-on-read for `get_context`; Slice 2 left `pending_approval` as `None`. |
| D3-10 | — | The agent prompt lists the booking, consent, status, resolution and history steps | The model must know when to call the new tools; it still never approves anything. |
| D3-11 | — | History speech names the household, not "you", for customer answers ("the household said it was fixed") and speaks the latest three entries | Another member may have answered; the full timeline stays in the record (FR-18). |
| D3-12 | Cancelling or changing while the request is pending queues a MANUAL item | `prepare_action` refuses a cancel or change on a `*_PENDING` request (`NOT_CANCELLABLE` or `NOT_RESCHEDULABLE`); no manual-review item is raised | Review finding I6, decided by Deb (16 Oct): honest and on the plan's cut list. The elder asks again once the pending answer is known; a stuck request raises its own manual item (I5). |

Notes:
- `record_service_details` and `confirm_resolution`/`get_history` follow the `mcp-tool-contract` skill; `docs/architecture/interactions.md` needs no change (no arrow's meaning changed).
- Sharing consent is not required to submit a demo booking; the read-back states what is shared. If Deb reads FR-01 as requiring `sharing_consent = GRANTED` before submission, that is a one-line check in `prepare_action(SUBMIT)`.
- Extra tests beyond Proof: `tests/unit/domain/test_staff_events.py` (ACK_ONLY confirmed or rejected by a coordinator provider event; technicians refused; duplicate event).

## Review fixes (16 Oct 2026)

The `reviewer` subagent found 1 Critical and 15 Important issues, plus nits. Deb chose to fix all of them except I6, which is recorded as D3-12. Each fix started with a test that was confirmed to fail for the reported reason (two guard tests, `test_i1_cancel_retried_…` and `test_i5_fresh_…`, passed already; they are kept as regression guards).

| # | Finding | Fix | Test |
| --- | --- | --- | --- |
| C1 (Critical) | Staff event de-dup returned a stored result whatever the case or payload; provider-event de-dup was written outside the outcome | The key is `SREVT#{case}#{event}` and stores a fingerprint of (type, expected version, summary): the same event again gets the original result, a different one under a used ID is `RECORD_CONFLICT EVENT_ID_REUSED`. Provider events write the de-dup item inside the outcome transaction | `test_staff_events.py::test_c1_reused_event_id_…`, `::test_c1_event_ids_are_scoped_to_their_case` |
| I1 | A reschedule retried after success superseded again | Before a new dispatch, `reschedule` and `cancel` check the provider's record for the operation key; if it ran, the recorded outcome is returned | `test_booking_integrity.py::test_i1_reschedule_retried_…`, `::test_i1_cancel_retried_…` |
| I2 | Every failed `execute_action` was spoken as "sent, pending" | The pipeline asks `approvals.outcome_after_failure`, which reads the records (reconciling first): `NOT_SENT` ("nothing was sent") when nothing was dispatched for this approval, otherwise the recorded outcome | `::test_i2_outcome_after_a_failed_execute_…`, `::test_i2_consent_outcome_…`, `test_templates.py::test_review_outcome_wording` |
| I3 | A reconcile that lost a race raised `RECORD_CONFLICT` | `booking._settle`: on a lost conditional write, re-read the request and report what is recorded | `::test_i3_reconcile_that_loses_a_race_…` |
| I4 | Coordinator rejection kept the place; could reject a timed-out request; place and record not atomic | `PROVIDER_CONFIRMED`/`PROVIDER_REJECTED` need `REQUESTED` and settle the provider's own record (`DemoProvider.settle`; a rejection releases the place in the same write). Taking or releasing a place and writing the provider record are one transaction (`Table.update_op`) | `test_staff_events.py::test_i4_…`, `test_booking_integrity.py::test_i4c_…` |
| I5 | A dispatch lost before reaching the provider stayed pending forever | `reconcile` repeats the call under the same operation key after 60 s (the provider de-duplicates), and after 15 minutes raises one `DISPATCH_UNKNOWN` manual item. The sweep now logs and skips a failing request instead of ending the round | `::test_i5_lost_dispatch_…`, `::test_i5_fresh_pending_request_…` |
| I7 | Approval expiry was a flat 5 minutes; any slot could be prepared | `list_slots` records each offered slot (`SR#{id}#OFFER#{slot}`, 10 minutes). `prepare_action` needs an unexpired offer (`SLOT_NOT_OFFERED`) and expires at the earliest of 5 minutes, the offer and the session's end | `::test_i7_approval_needs_a_listed_slot_…` |
| I8 | Client playback and speech times were trusted unbounded | The pipeline accepts a playback end only after the read-back was prepared, not in the future and not while the client reports SPEAKING (`approval_guard.accept_playback_end`). The guard and `confirm_action` refuse future speech times (`SPEECH_TIME_INVALID`) and read-back times before the approval was prepared | `test_approval_guard.py::test_i8_…` (2), `test_booking_integrity.py::test_i8_…` |
| I9 | Sharing consent was answered with the storage sentence | `CONSENT_SHARING_RECORDED` template | `test_templates.py::test_review_outcome_wording` |
| I10 | Status replies had no "last updated" | Pending and requested replies add "It was last updated on Friday, 16 October at 3:05 pm" (Asia/Kolkata) | `::test_fr15_status_says_when_…` |
| I11 | Reopening recorded no reason | `reopen_reason` (the customer's new wording) on the issue and in its view | `test_staff.py::test_at19_…` (strengthened) |
| I12 | The agent received the full address and contact on every turn | Request views carry `address_on_file`/`contact_on_file` only; full values appear only in the booking read-back | `test_service.py::test_p3_3_…` (moved to the stored record, plus non-exposure checks, including `get_context`) |
| I13 | The correlation trail did not join | Every request event carries `approval_id` and `dispatch_correlation_id`; `APPROVAL_PREPARED`/`APPROVAL_CONFIRMED` carry `approval_id`, and the latter is on the appliance's timeline | `test_booking.py::test_at14_…` (strengthened) |
| I14 | The QA contact used Pune's real STD code | `Landline 000 0000 0000`, a non-dialable placeholder; fixture notes corrected | — |
| I15 | Two concurrent drafts could create two requests for one issue | Per-issue sentinel `OPENSR#{issue}` written with the draft (new, or conditionally taken over from an ended request); a losing draft returns the winner | `::test_i15_one_open_request_…` |
| N1 | Cancel read-back said "cancel" (a STOP word); questions not last | All read-backs end with their one question; cancel says "call off"; the guard accepts "yes call it off", "yes change it", "yes move it" (and without "yes") | `test_templates.py::test_review_readbacks_…`, `test_approval_guard.py::test_n1_…` |
| N2 | Reschedule and cancel read-backs omitted the provider (reschedule also the address and data shared) | Added | `test_templates.py::test_review_readbacks_…` |
| N3 | `NO_SHOW` had no state check | Needs `CONFIRMED` | `test_staff_events.py::test_n3_…` |
| N4 | Disclosure wording differed from TDD §4.6 | Templates use `DEMO_DISCLOSURE`: "This is a demonstration. No real technician will visit." | `test_templates.py::test_review_outcome_wording` |

Test-setup corrections (no assertion weakened):
- `test_at13_fresh_explicit_yes_books_once` had the read-back finishing 2 s *before* it was prepared; the clock now advances 20 s first. The new I8 rule rightly refused the impossible timeline.
- `test_at15_last_slot_…`: Household B now lists slots before approving, because I7 requires an offered slot.
- `test_ack_only_request_is_confirmed_…` re-sent a duplicate with a different `expected_version` and expected the original result; under invariant 5 that is a conflict, so the duplicate now repeats the identical body.

Added after the re-verification (verifier suggestion): `tests/contract/test_mcp_trusted.py::test_inv2_confirm_and_execute_refuse_without_attestation_for_that_call`. Over MCP, `confirm_action` and `execute_action` refuse a missing or garbage attestation, and one made for another tool or other arguments, and the pending approval does not move. The same call with the channel's attestation is accepted. With attestation checking disabled in a scratch probe, the test fails as it should.

Not changed: N5's tautological `authorize_system` (the settled count is no longer logged in `action`), and the four unlisted nits. The cancel transaction still scans for other confirmed requests instead of conditioning on the I15 sentinel; with one open request per issue the scan is exact.

Local check re-run on DynamoDB Local after the fixes: the full journey passes; one slot place taken, one provider record, one open-request sentinel.
