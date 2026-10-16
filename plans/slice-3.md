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
