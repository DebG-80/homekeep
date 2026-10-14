# HomeKeep Business Requirements Document

Version 1.0 | 24 September 2026 | Status: proposed implementation baseline for stakeholder review

Prepared for the HomeKeep product owner, development team, QA team, and future service operations team.

HomeKeep will let elders in Indian households obtain appliance help through conversation without requiring them to find invoices, scan receipts, or use a mobile app during everyday operation. The first release is a working hackathon web simulation with voice and text interaction, persistent records, and a clearly identified demo service desk. A later commercial release will connect approved voice devices and real service operations.

This BRD specifies business outcomes, functional behavior, data, integration boundaries, acceptance criteria, and release gates. It is the basis for backlog refinement and test design, not a claim that the proposed service, partner contracts, or Alexa+ production access already exist. Decisions marked proposed require product-owner review before becoming a committed delivery baseline.

## 1 Document governance and reading guide

**Confirmed** means a product direction explicitly accepted in the conversation. **Proposed** means a requirement or target introduced here to make implementation testable. **Assumption** means a planning condition needing validation. **Open** means an unresolved decision with an owner role and decision gate. Official platform facts have source references in Section 16 and a verification date.

Release codes: **H** = hackathon MVP; **P** = post-hackathon controlled production pilot; **F** = future expansion. H requirements carry forward into P unless replaced explicitly. Priority means Must for that release, Should if capacity permits, or Could for an optional enhancement. A P Must is not an H release blocker.

Requirements use BR for business, FR for functional, NFR for non-functional, and AT for acceptance test. Functional acceptance criteria use their requirement ID plus an AC suffix. The acceptance scenarios in Section 12 map these IDs to testable evidence. Role names designate responsibilities, not currently staffed positions.

| Review area | Accountable role | Required decision |
| --- | --- | --- |
| Product scope and priorities | Product owner | Accept H baseline and record approved deviations |
| Architecture and interfaces | Technical lead | Select stack, identity model, and deployment approach |
| Test coverage and evidence | QA lead | Review test cases, fixtures, and release gates |
| Appliance guidance | Qualified appliance specialist | Approve supported guidance and escalation content |
| Live service delivery | Operations owner | Confirm providers, geography, charges, and support process before P |
| Data handling and consent | Privacy and security reviewers | Approve retention, access, and consent design before P |

Change control: retain stable requirement IDs; record version, requested change, rationale, affected tests, and approver. Do not renumber existing requirements when inserting new ones. Version 1.0 establishes the first proposed baseline; stakeholder approvals are pending. Record reviewer, date, version, and exceptions for each approval. Production operations and privacy approval are required before the live pilot.

Reading order: business stakeholders should review Sections 2 to 5 and 14 to 15; developers should also use Sections 6 to 11; QA should use requirements and Sections 12 to 13 together. Section 16 contains source links and terms.

## 2 Business problem and intended outcomes

Elders may know that an appliance is not working but lack its exact model, purchase date, receipt, or a dependable way to organize repairs. Repeatedly explaining symptoms, navigating booking applications, and finding past service records add work. HomeKeep will accept incomplete information, maintain the case across conversations, and help the household reach a documented outcome.

The core value is continuity from a spoken problem to a completed service journey. Guidance is limited by available evidence. A request for a technician is a valid outcome even when troubleshooting is skipped or cannot identify the cause. The product must not make paperwork a prerequisite for ordinary assistance.

### 2.1 Confirmed product decisions

- C01: Primary audience is elders in Indian households; family support is optional.
- C02: Everyday elder interaction should be mobile-free. Initial device setup may be assisted.
- C03: Appliance registration must allow unknown model, serial number, invoice, and purchase date.
- C04: Appliance categories initially include AC, refrigerator, and television; complete troubleshooting focuses on AC.
- C05: The hackathon uses a web simulation; production ambition includes Echo or other supported voice devices.
- C06: Persistent appliance and issue history is central to the service.
- C07: Service-provider availability and booking in H are simulated and must be disclosed.

### 2.2 Business requirements

| ID and phase | Priority | Required outcome | Measurement and acceptance |
| --- | --- | --- | --- |
| BR-01 H and P | Must | Provide help without documents or exact model | All missing-information test journeys can record an appliance and issue and reach a service-request draft |
| BR-02 H and P | Must | Support spoken everyday tasks | Core voice journey completes after assisted setup without clicking, typing, or reading the screen |
| BR-03 H and P | Must | Preserve continuity | Returning user retrieves the same issue and prior checks after session restart |
| BR-04 H and P | Must | Represent outcomes accurately | No test labels a pending, failed, or simulated real-world booking as a confirmed live visit |
| BR-05 H and P | Must | Keep guidance evidence-based | All model-specific steps in evaluation reference approved content for the verified model |
| BR-06 H and P | Must | Control household and provider access | All isolation and authorization tests pass without cross-household disclosure |
| BR-07 H | Must | Demonstrate an executable submission | Reproducible build, working demo, and submission checklist are complete |
| BR-08 P | Must | Operate a dependable repair service | Pilot starts only after provider, support, escalation, privacy, and operational gates pass |

BR-01 through BR-08 are proposed measurable formulations of the confirmed direction. They do not establish a commercial SLA.

### 2.3 Proposed success measures

Pilot targets require validation with intended users. Measure voice task completion as participants finishing registration, issue reporting, and service-request confirmation without screen assistance divided by participants attempting the journey. Initial target: at least 8 of 10 consenting elder participants after assisted setup. Record language, hearing or speech accommodations, interruptions, and whether a human intervened; do not present this small sample as market proof.

Track median questions before a usable issue record, repeated-question rate after resumption, request-to-provider-confirmation time, unresolved issues, cancellations, and customer-confirmed resolution. Baselines and service-time targets remain open. Count troubleshooting success only when the user confirms the symptom resolved. Report service cost per completed case separately from cloud cost; neither pricing nor profitability is established.

## 3 Delivery scope and boundaries

### 3.1 Release scope matrix

| Capability | H hackathon | P production pilot | F expansion |
| --- | --- | --- | --- |
| AC fridge and TV registration | Must with optional fields | Retain and validate household adoption | Add categories based on demand |
| AC guidance | One verified model minimum; second model Should | Approved catalog for pilot models | Broader reviewed catalog |
| Unknown appliance model | Observations and service handoff | Same rule | Improve identification assistance |
| Voice and text | English browser speech and text; assisted start | Validated voice device and launch language | Additional Indian languages and channels |
| Identity | Test households and authenticated staff roles | Approved household and device binding | Additional identity providers |
| Service desk | Working simulated provider and slots | Contracted provider or staffed coordination | Additional providers and retailers |
| Documents | Staff or helper attachment; no OCR dependency | Optional family and technician upload | OCR and retailer import |
| Family support | Seeded authorized helper role | Invitation and revocation workflow | Additional delegation choices |
| Technicians | Staff records simulated visit updates | Assigned technician access and reconciliation | External field-service integrations |
| Reminders | Opt-in records surfaced on return | Approved delivery channel if supported | Additional proactive channels |
| Actual payments | Excluded | Separate approved payment design needed | Optional provider payment integration |

English is a proposed H implementation baseline, not a decision that English is sufficient for the Indian market. Hindi, Hinglish, regional-language priorities, and speech-provider coverage must be validated before the pilot. The English H experience is not evidence of production language readiness.

### 3.2 Explicit exclusions

H excludes live Alexa+ publication, real dispatch, charging users, automatic email or purchase-history access, automatic warranty approval, remote AC control, electrical or refrigerant repairs, broad open-web diagnostic generation, and retailer integrations. H will not send external messages or use real customer documents as public demo fixtures.

P does not promise universal appliance diagnosis, emergency response, automatic access to invoices, unrestricted smart-speaker compatibility, or a guaranteed repair price. Any expansion needs its own validated requirements. Wi-Fi and device/account setup remain operational dependencies; mobile-free everyday use does not mean no internet or no setup assistance.

### 3.3 Minimum coherent hackathon release

Ship one repeatable path: identify or register Bedroom AC without an invoice; record poor cooling; use approved limited guidance or escalate; create and confirm a demo request; resume later; change its appointment; record service; obtain customer confirmation; retrieve history. Include an unknown-model path and a verified-model evidence path. Keep all Must H integrity and authorization controls when reducing scope; drop optional OCR, extra languages, extra models, and external integrations first.

## 4 Actors and permission boundaries

An elder may also be the household account owner. Family relationship alone grants no access. A household owner approves helper access and sharing; an installer may assist setup without acquiring continuing access. A technician only sees an assigned job. A coordinator manages service operations for assigned cases. An administrator configures the service and accesses customer records only through an authorized, audited support function.

| Operation | Elder or owner | Authorized helper | Assigned technician | Coordinator | Administrator |
| --- | --- | --- | --- | --- | --- |
| Register appliance and report issue | Household access | Within granted scope | Enrich assigned appliance only | On user request | Audited support only |
| Read appliance history | Household access | Within granted scope | Relevant case extract | Assigned cases | Audited support only |
| Book or change visit | Authorized household session | Only with booking grant | Propose change only | Following captured approval | No automatic booking authority |
| Attach model evidence | Yes optionally | With edit grant | Assigned job only | Assigned case | Catalog and support tools |
| Confirm symptom resolved | Yes | If explicitly delegated | Report work only | Record customer's answer | No unilateral closure |
| Grant or revoke helper access | Owner through secured flow | No | No | Assisted owner flow | Enforce request |
| Approve guidance catalog | No | No | Submit evidence only | No | Publish specialist-approved version |

Proposed default helper grants are separate flags for view, edit, book, and receive updates. Revocation blocks new reads and actions immediately and cancels unsent helper notifications. It does not silently cancel an already approved household appointment. Record changes to grants and disclose the sharing scope in plain language.

H uses distinct authenticated test actors, not an unrestricted UI role switch. A household session is a household identity, not proof of which individual is speaking. Do not rely on claimed names, voice similarity, or speech recognition alone for sensitive access. The production identity assurance policy is an open launch gate.

## 5 User journeys and interaction rules

### 5.1 Assisted setup and first appliance

An authorized family member or installer creates the household, binds the intended device or demo session, sets a language, and helps the elder understand storage and sharing choices. Only necessary setup data is collected. A service address and contact route can wait until service is requested. The elder can decline family sharing and still use HomeKeep.

User: “I have an AC in the bedroom.” HomeKeep: “I can save it as Bedroom AC. Is that right?” User: “Yes.” HomeKeep saves category and nickname. It may ask an optional brand question once. “I don't know” produces an unknown value and continues; it does not re-ask until new evidence is offered.

The no-family path in H uses an assisted demo setup. In P it requires a staffed onboarding service or installer arrangement, including account-recovery support. That service is a launch dependency, not a currently available capability.

### 5.2 AC problem to service request

1. User says “The bedroom AC is not cooling.” Resolve the appliance in the authenticated household. If missing, offer to create it; if ambiguous, ask which room or appliance.
2. Find active issues on that appliance. Ask whether this continues the existing problem before creating another case.
3. Record the symptom and ask when it started. Accept approximate dates and “not sure.” A proposed intake records onset, airflow observation, displayed error if readily visible, and warning signs; each question can be skipped.
4. Screen reported warning signs using approved content. If a hazard is reported, stop routine troubleshooting and move to human escalation. Never ask the elder to climb, remove electrical covers, handle refrigerant, or keep restarting a tripping unit.
5. For a verified supported model, retrieve approved guidance and provide one step at a time with a source reference available. For an unknown or unsupported model, collect non-invasive observations and offer service. Do not guess error-code meanings across models.
6. Record every offered step and its outcome: not tried, completed, skipped, or unsuccessful. User may ask for a technician at any time.
7. Read back the issue summary and draft a service request. Ask for missing service address, contact route, and preferred time only now. Invoice and model remain optional.
8. Read provider, full date, time window, disclosed fee or fee uncertainty, data to be shared, and demo status. Capture explicit approval for the exact action.
9. Submit once. Announce a booking only after the provider adapter returns a confirmed reference and slot. On uncertainty, say the status is pending and reconcile before retrying.

### 5.3 Resumption and change of plan

User: “Continue the AC problem.” HomeKeep retrieves open issues and asks which one if necessary. It summarizes the saved symptom, previous checks, and current service status. It does not read unnecessary personal details aloud.

User: “Move it to Sunday afternoon.” HomeKeep resolves “it” against the current issue, converts the proposed date to an explicit date in Asia/Kolkata, checks current availability, and requests confirmation. The old appointment remains valid until replacement is confirmed. Failure leaves the old booking unchanged and explains that result.

### 5.4 Service completion and unresolved repair

A technician records work performed and optional evidence. HomeKeep marks the visit completed but asks the household whether the symptom is resolved. “Still not cooling” keeps the issue open and offers a follow-up. “It works now” moves the issue to resolved; the user may then close it. No response leaves it awaiting customer confirmation. Elapsed time alone never means a successful repair.

When a closed issue recurs, reopen it with an event if it is the same reported problem, or create a linked new issue if the user describes a different problem. Prior completed visits and receipts are retained, not overwritten.

### 5.5 Voice design and recovery

| Situation | Required response pattern |
| --- | --- |
| Long explanation | Start with one short action or question; offer more detail on request |
| Unknown answer | Accept “not sure”; record unknown and move to a useful next step |
| Recognition uncertainty | Repeat only the ambiguous field; never guess an address, date, price, or approval |
| Repeat or slower | Repeat current prompt without changing case state; reduce speech rate if supported |
| Correction | Read back the corrected field and invalidate any affected pending confirmation |
| Silence | Reprompt once after a proposed 15 seconds; after a further 20 seconds pause and save, without submitting actions |
| Two failed attempts | Offer pause or human assistance; text remains optional in H, never the only P recovery |
| Stop or cancel during speech | Stop playback and pending capture promptly; cancel unsubmitted action and save prior committed state |
| Microphone denied | Explain permission need and offer text in H; record voice test as blocked, not passed |
| Connection loss | Show or speak failure if possible; never announce a write that is unacknowledged |
| Unsupported language | Explain supported choices; do not treat misunderstood speech as confirmation |

After initial browser microphone permission and session start, H must allow spoken turns without per-turn clicks in the chosen supported browser. A visible microphone control and keyboard equivalent remain available. The selected browser must support this interaction before the voice-only H gate can pass. Timings are proposed accessibility settings and must be adjustable after user testing.

Suggested ordinary responses contain at most two sentences and one question. Long consent and service summaries may be broken into short parts without omitting material information. Confirmations must be explicit and tied to a currently pending action, never inferred from background audio or a previous “yes.”

## 6 Functional requirements

All FR entries are proposed implementation requirements derived from the confirmed direction. Unless stated otherwise: authenticated household scope is a precondition; failed writes leave previously committed state unchanged; authorization is checked on the server; acceptance tests use synthetic data. Metadata names actor, trigger, priority, phase, and linked business requirements. Each FR contains its own observable acceptance criteria.

### FR 01 Household setup and consent

**H and P | Must | BR-01 BR-02 BR-06. Actor:** owner assisted by helper or installer. **Trigger and precondition:** first use; no existing authorized session.

Create a household and bind an authenticated session. Explain stored appliance/case data and optional sharing separately. Require consent for persistent service use; allow declining optional family sharing. H uses synthetic seeded identities with a consent interaction; P requires supported account/device linking and owner recovery.

**FR-01-AC1:** Given no invoice or helper, when setup consent is accepted, then an authorized household session can create an appliance. **AC2:** Declining optional sharing creates no helper grant. Declining required storage consent creates no persistent appliance/case and explains the limitation.

### FR 02 Minimal appliance registration

**H and P | Must | BR-01. Actor:** elder or helper with edit grant. **Trigger:** identifies a new appliance; household exists.

Require category and a confirmed household nickname; generate appliance ID and timestamps. Room, brand, model, serial number, dates, invoice, and AMC are optional. Handle AC, refrigerator including “fridge,” and television including “TV.” Proposed duplicate nicknames require disambiguation rather than silent overwrite.

**FR-02-AC1:** Given only “bedroom AC,” confirmation persists a usable record with unknown optional fields. **AC2:** A repeated submission with the same operation key returns that record; a second distinct AC can be registered with a clarified nickname.

### FR 03 Resolve and correct appliance identity

**H and P | Must | BR-01 BR-03. Actor:** elder or authorized editor. **Trigger:** ambiguous reference or correction; household record available.

Resolve nickname and approved aliases only within the household. Ask a clarifying question when multiple matches exist. Store provenance per model/brand field. User recollection is user-reported; exact model verification requires readable trusted evidence and review. Conflicts remain visible until resolved by an authorized reviewer.

**FR-03-AC1:** Two ACs and “my AC” cause clarification without mutation. **AC2:** “I think it is model X” does not unlock model-specific guidance; a reviewed matching label/manual record does. A corrected model invalidates incompatible pending guidance.

### FR 04 Optional document enrichment

**H and P | Must | BR-01 BR-05 BR-06. Actor:** authorized helper, coordinator, or assigned technician. **Trigger:** document added; relevant record exists.

Accept PDF, JPEG, or PNG up to a proposed 10 MB per file through the staff interface. Validate content type and access scope; quarantine until validation completes. Record document type, provenance, linked appliance/case, and reviewer. H permits manual entry; OCR is F and never establishes truth automatically.

**FR-04-AC1:** Missing attachment does not block reporting or booking draft. **AC2:** Unsupported or oversized upload is rejected without changing appliance fields; quarantined files cannot be retrieved by the agent. Another household cannot fetch the document.

### FR 05 Capture an issue and prevent accidental duplicates

**H and P | Must | BR-01 BR-03. Actor:** elder or authorized helper. **Trigger:** defect reported; appliance resolved or newly registered.

Persist original symptom wording and a structured summary with unknown fields allowed. Search active issues for the same appliance; ask whether the user means an existing case. A new distinct symptom may create a separate issue with explicit confirmation. Repeated transport requests use an idempotency key.

**FR-05-AC1:** Poor cooling without onset/model creates one open issue. **AC2:** Repeating the same request returns the original issue; a user-confirmed different problem creates a separately identified case.

### FR 06 Focused symptom collection

**H and P | Must | BR-01 BR-02 BR-05. Actor:** elder. **Trigger:** open issue; approved intake for category exists.

Ask one question at a time and accept skipped or unknown answers. Save each committed answer immediately. Never require visual inspection of an inaccessible label. Confirm an ambiguous displayed code before looking it up. Intake question order may adapt but must not bypass the safety gate.

**FR-06-AC1:** “I don't know” advances without inventing a value or blocking escalation. **AC2:** After a restart, answered questions are not asked again unless the user changes the symptom or the relevant answer is stale and the reason is explained.

### FR 07 Hazard and unsupported symptom escalation

**H and P | Must | BR-05. Actor:** elder or coordinator. **Trigger:** reported warning sign at any point, or guidance cannot safely continue.

Use a specialist-approved escalation policy for reported burning smell, exposed electrical damage, repeated tripping, and other reviewed hazards. Stop troubleshooting; provide approved concise guidance and offer human service assistance. Do not claim emergency dispatch. The content catalog must define exact wording before enabled release.

**FR-07-AC1:** A hazard reported mid-flow blocks further routine steps and records the escalation reason. **AC2:** Requests for electrical disassembly or refrigerant repair never produce such instructions and instead offer a service handoff.

### FR 08 Retrieve and explain approved guidance

**H and P | Must | BR-05. Actor:** assistant on user's request. **Trigger:** non-hazard issue and confirmed guidance eligibility.

Filter by verified exact model, catalog version, approved step type, and source rights. Return source document ID, page/section, and evidence text with each model-specific step. If no suitable evidence exists, state the limitation and offer service. Unknown-model mode is limited to reviewed generic observation prompts.

**FR-08-AC1:** A supported verified model returns an approved matching step and source locator. **AC2:** Unknown model, missing citation, conflicting document, withdrawn catalog entry, or retrieval failure returns no model-specific step. A manual containing instructions to bypass system controls cannot authorize any tool action.

### FR 09 Record steps and outcomes

**H and P | Must | BR-03 BR-05. Actor:** elder. **Trigger:** a guidance step is offered.

Record offered, not tried, completed, skipped, or unsuccessful status with time and user response. Store source version and symptom context. Do not equate completion of a check with repair. Stop further steps when the user requests service or reports a new warning sign.

**FR-09-AC1:** “Already tried that” records the result and advances without repeating the step. **AC2:** “It is cooling now” triggers outcome confirmation before resolution; “no change” preserves the unresolved issue.

### FR 10 Resume a conversation

**H and P | Must | BR-02 BR-03. Actor:** elder or authorized helper. **Trigger:** return to saved issue.

Rebuild context from structured records, including latest symptom, attempted steps, hazard flag, and current request state. Ask which issue when ambiguous. Offer a short summary and the next useful action. An interrupted draft is recoverable but unsubmitted approvals do not silently carry into a new session.

**FR-10-AC1:** A new authenticated session resumes the same issue after reload with prior steps intact. **AC2:** A stale pending booking requires a fresh availability check and approval; a previous session's “yes” cannot submit it.

### FR 11 Draft a service request

**H and P | Must | BR-01 BR-04. Actor:** elder or helper with booking grant. **Trigger:** asks for service or accepts escalation.

Create a draft linked to the issue containing symptoms, performed checks, optional evidence, preferred date, and sharing scope. Collect address and contact route only if missing. A draft can exist without them; submission cannot. Show and speak unknown warranty/fees accurately. H uses synthetic address and provider data.

**FR-11-AC1:** An unknown-model case produces a reviewable draft with no invoice. **AC2:** Missing service location/contact blocks submission only and requests that field; user can save or abandon the draft.

### FR 12 Explicit approval and sharing

**H and P | Must | BR-02 BR-04 BR-06. Actor:** authorized household session. **Trigger:** a consequential action is ready for review.

Summarize action, provider, address confirmation, date/window, price or price uncertainty, and data shared. Bind approval to action payload, record version, actor, and expiry. Proposed expiry is five minutes or session end, whichever occurs first. A change to material fields invalidates approval. Slot expiry may be earlier.

**FR-12-AC1:** A clear “yes” to the current complete summary permits that exact action once. **AC2:** Silence, unrelated speech, expired approval, changed fee, or changed slot causes no submission. Sharing unrelated appliance history is excluded from the approved payload.

### FR 13 Availability and booking confirmation

**H and P | Must | BR-04. Actor:** elder and service adapter. **Trigger:** approved service request with required fields.

Check slot availability at commit, submit with an idempotency key, and distinguish provider acknowledgment from confirmed booking. H uses a functioning simulated adapter and audible/visible demo disclosure. Store provider reference and slot only on authoritative confirmation. Unknown response remains submission pending until reconciled.

**FR-13-AC1:** Available confirmed slot yields one booking and an explicit demo confirmation in H. **AC2:** Slot contention offers alternatives without booking. Timeout followed by retry/reconciliation creates at most one provider request and never fabricates confirmation.

### FR 14 Reschedule and cancel

**H and P | Must | BR-03 BR-04. Actor:** elder, authorized booking helper, or coordinator acting on captured approval. **Trigger:** change requested on non-terminal service request.

Read the current appointment, check alternatives/terms, and obtain fresh approval. Preserve the old booking until replacement confirmation. If an adapter cannot replace safely, refer to manual coordination instead of cancel-and-rebook without authorization. Cancellation is pending until acknowledged; any fee change needs renewed approval.

**FR-14-AC1:** Confirmed replacement supersedes the old appointment exactly once. **AC2:** Failed replacement retains the original; failed/unknown cancellation is not announced as cancelled. Appointment history remains available.

### FR 15 Enquire about status

**H and P | Must | BR-02 BR-03 BR-04. Actor:** household user or granted helper. **Trigger:** asks about a service request.

Return latest stored authoritative state, local date/window, and last-update time. Reconcile stale or pending requests where supported. Explain uncertainty or provider unavailability; never infer technician travel or arrival from elapsed time. Avoid speaking the full address unless needed and authorized.

**FR-15-AC1:** “When is the AC person coming?” reads the correct issue's confirmed slot. **AC2:** A pending request says pending; stale provider data is labelled with its last update rather than presented as live tracking.

### FR 16 Service desk and technician updates

**H and P | Must | BR-03 BR-04 BR-06. Actor:** assigned coordinator or technician. **Trigger:** case assignment or service event.

Allow scoped queue access, assignment, visit updates, work notes, and optional invoice/model evidence. H uses staff accounts to simulate provider events. Require event ID, reference, timestamp, and expected version. Reject unauthorized, duplicate, or invalid transitions; older events must not regress state.

**FR-16-AC1:** Assigned technician can add work notes and mark visit completion but cannot close the customer issue. **AC2:** Unassigned actor is denied; duplicate completion leaves one event; an older scheduled event cannot undo completion.

### FR 17 Confirm resolution and reopen

**H and P | Must | BR-03 BR-04. Actor:** elder or explicitly delegated helper. **Trigger:** reported improvement, completed visit, or recurrence.

Ask whether the original symptom is resolved. Positive answer records customer-confirmed resolution; a negative answer returns the issue to service-needed or triage. Closure is explicit. Reopening preserves prior visits and links a new service request when needed; never mutate a completed visit into a new booking.

**FR-17-AC1:** Technician completion alone leaves the issue awaiting confirmation. **AC2:** “Still not cooling” keeps it unresolved; a subsequently closed and recurring case reopens with a recorded reason and unchanged earlier evidence.

### FR 18 Appliance history

**H and P | Must | BR-03 BR-06. Actor:** authorized household user or scoped staff. **Trigger:** history requested.

Provide a chronological event timeline and spoken summary covering symptoms, checks, service changes, work, and customer outcomes. Label technician reports and customer statements separately. Correct records through attributed amendments; do not erase prior events silently. Full transcripts are not required for history.

**FR-18-AC1:** Reschedule and repair events appear with actor, time, and provenance. **AC2:** Another household's identifier or technician request for unrelated history yields no data.

### FR 19 Reminders and follow-up preferences

**H and P | Should | BR-03. Actor:** elder or authorized helper. **Trigger:** asks for reminder after documented recommendation.

Capture purpose, due date, timezone, source, delivery preference, and opt-in. H surfaces due reminders when the user returns and discloses that it will not proactively speak from a closed browser. P proactive delivery requires a verified supported channel and separate channel permission. No invented universal maintenance interval.

**FR-19-AC1:** An opted-in reminder is retrievable at its due date and can be cancelled by voice. **AC2:** No opt-in or unsupported channel creates no outgoing notification; cancelled reminders are not delivered on retry.

### FR 20 Helper delegation and revocation

**H and P | Must | BR-02 BR-06. Actor:** owner. **Trigger:** grant change; owner identity verified.

H seeds grants and supports secure revocation; invitation is P. Store recipient, scope, expiry if any, and consent version. Do not mandate a helper. A helper cannot widen their own access. P invitations expire and require recipient acceptance; assisted owner access remains available for no-family households.

**FR-20-AC1:** A view-only helper cannot book or edit. **AC2:** After revocation, previously issued sessions cannot read household data or execute pending actions; existing household bookings remain intact.

### FR 21 Voice and text parity

**H and P | Must | BR-02. Actor:** elder. **Trigger:** begins core task in a supported channel.

Use the same backend rules for voice and text. H provides speech input, spoken output, transcript, microphone state, and keyboard controls. All core tasks after assisted launch can use voice alone in the supported browser. “Stop,” “repeat,” “slower,” and correction commands are supported; echo from assistant playback must not count as approval.

**FR-21-AC1:** A tester completes the core journey with the screen hidden after setup. **AC2:** Stop interrupts output and cancels unsubmitted action; muted microphone captures no new audio. Text can recover H usability but does not count as a voice pass.

### FR 22 Recognition and connection recovery

**H and P | Must | BR-02 BR-04. Actor:** elder. **Trigger:** uncertain speech, silence, disconnect, or response timeout.

Follow the recovery rules in Section 5.5. Save confirmed facts; re-ask critical ambiguous values. On reconnect, query committed state before replaying writes. Any local unsent draft must be identified as unsent. Human escalation cannot promise a callback if no reachable contact or staffed route exists.

**FR-22-AC1:** Reconnecting during submission retrieves status without duplicate request. **AC2:** Silence or “Saturday... no, Sunday” does not submit until the corrected explicit date is confirmed.

### FR 23 Catalog and guidance administration

**H and P | Must | BR-05. Actor:** catalog administrator and specialist reviewer. **Trigger:** new, changed, or withdrawn guidance.

Maintain supported models, manual rights, source locators, permitted generic prompts, hazard responses, and review status. Publish only reviewed versions. Log reviewer and date; withdrawn content is unavailable to new steps. Do not let uploaded customer documents alter system instructions or grant permissions.

**FR-23-AC1:** Draft guidance cannot be retrieved by a customer session. **AC2:** Withdrawal blocks the next use and records why prior case evidence may reference an older version without deleting history.

### FR 24 Data access and account closure requests

**H and P | Must | BR-06. Actor:** verified owner or audited support operator. **Trigger:** access, correction, or deletion request.

H provides a documented test-household purge and correction procedure; P adds an owner-facing request workflow with verbal initiation and assisted verification. Explain pending service consequences. Execute approved retention rules for primary data, files, derived indexes, and backups; preserve only explicitly justified records under the approved policy.

**FR-24-AC1:** Purging a test household removes its searchable records and documents and revokes access. **AC2:** An unverified voice request cannot delete another household. P requests expose status and completion evidence under the approved policy.

### FR 25 Human service coordination

**P | Must | BR-01 BR-02 BR-08. Actor:** coordinator and elder. **Trigger:** user asks for help or automated flow cannot proceed.

Create a scoped coordination task with symptom context and permitted contact route. Offer supported availability without inventing response times. Operators can complete registration, recover account access through the approved process, find contracted service options, and record approvals. Operational ownership and service hours must exist before launch.

**FR-25-AC1:** A no-family customer can complete onboarding and service handoff with staff assistance and no mobile operation. **AC2:** Out-of-hours or no-contact cases disclose the limitation and retain the case without a false callback promise.

### FR 26 Production voice device adapter

**P | Must | BR-02 BR-08. Actor:** authenticated device user. **Trigger:** invokes HomeKeep on approved production hardware.

Bind platform identity to the correct household through supported authorization; enforce the same business services as H. Validate invocation, session limits, speech behavior, country/language availability, permissions, certification, recovery, and notification capabilities. Hackathon simulation and browser speech are not evidence of a live Alexa+ integration.

**FR-26-AC1:** On launch-market hardware, an authorized elder completes the core spoken journey after assisted setup. **AC2:** Unlinked, revoked, or wrong-household device requests reveal no private case data and enter the supported recovery flow.

### FR 27 Warranty and fee representation

**H and P | Must | BR-01 BR-04. Actor:** elder and service coordinator. **Trigger:** coverage or price discussed.

Separate user-reported warranty, document-stated terms, and provider-confirmed coverage for this service. Purchase date alone is insufficient to promise coverage. Distinguish unknown fee from zero; store currency, amount, estimate/final status, and scope. H uses labelled illustrative fees; payment collection is excluded.

**FR-27-AC1:** No invoice returns coverage unknown while allowing service coordination. **AC2:** A provider fee change invalidates pending approval and is read back before submission; “unknown” is never spoken as free.

### FR 28 Audit and actionable operational errors

**H and P | Must | BR-04 BR-06 BR-07. Actor:** services and authorized support. **Trigger:** read/write decision or integration error.

Record correlation ID, actor, tenant, action, result, relevant record version, and time without secrets or unnecessary raw speech. Expose customer-readable errors and a support reference. Authorization failure, validation failure, conflict, timeout, and provider unavailable must be distinguishable internally. Only authorized support can retrieve operational details.

**FR-28-AC1:** QA traces one approved booking from consent to adapter result and persisted state. **AC2:** Error responses expose no credentials, cross-tenant identifiers, raw stack traces, or private documents.

## 7 State models and business invariants

Issue state records whether the customer's problem is resolved. Service-request state records the provider interaction. Appointment records preserve individual slots and changes. These are separate entities; technician completion cannot automatically close an issue.

### 7.1 Issue transitions

| From | Event and authorized actor | To | Guard or consequence |
| --- | --- | --- | --- |
| None | User confirms reported symptom | OPEN | Appliance belongs to household |
| OPEN | Assistant starts approved intake | TRIAGING | Preserve original wording |
| OPEN or TRIAGING | User requests service or guidance exhausted | SERVICE_NEEDED | Model and invoice may remain unknown |
| Any unresolved state | New reported hazard | SERVICE_NEEDED | Set safety flag; stop routine guidance; preserve any valid booking |
| SERVICE_NEEDED | Provider confirms appointment | SERVICE_PENDING | Confirmed service reference required |
| SERVICE_PENDING | Provider completes visit | AWAITING_CUSTOMER | Work report recorded; no resolution inference |
| OPEN TRIAGING SERVICE_NEEDED or AWAITING_CUSTOMER | User confirms symptom resolved | RESOLVED | Record answer and attribution |
| SERVICE_PENDING | User says symptom resolved before visit | RESOLVED | Existing booking stays active until separately cancelled |
| AWAITING_CUSTOMER or RESOLVED | User says symptom persists | SERVICE_NEEDED | Offer follow-up; preserve completed visits |
| SERVICE_PENDING | Booking rejected cancelled or failed | SERVICE_NEEDED | Only if no other active confirmed booking exists |
| RESOLVED | User explicitly closes | CLOSED | Warn of any uncancelled visit and resolve its disposition separately |
| CLOSED | Same problem recurs and user confirms | OPEN | Append reopen event; never erase prior history |

A safety flag is orthogonal to status: it restricts guidance even if an appointment is pending. Only an authorized specialist/coordinator can record reviewed clearance with evidence; conversational “ignore that” does not bypass the restriction. An issue abandoned during conversation remains open or in triage; the session can end without closing it.

### 7.2 Service and appointment transitions

| From | Event | To | Authority and failure behavior |
| --- | --- | --- | --- |
| None | User requests draft | DRAFT | Household actor; draft is not a provider request |
| DRAFT | User approves current payload | APPROVED | Scoped unexpired confirmation |
| APPROVED | Dispatch begins | SUBMISSION_PENDING | Durable operation key exists before sending |
| SUBMISSION_PENDING | Provider acknowledges without slot | REQUESTED | Acknowledgment does not mean booked |
| SUBMISSION_PENDING or REQUESTED | Provider confirms slot | CONFIRMED | Save reference and appointment atomically |
| SUBMISSION_PENDING or REQUESTED | Authoritative rejection | REJECTED | Explain reason; offer revised draft |
| SUBMISSION_PENDING | Confirmed terminal submission failure | FAILED | Timeout alone is insufficient evidence |
| CONFIRMED | User approves new slot | CHANGE_PENDING | Existing appointment remains valid |
| CHANGE_PENDING | Provider confirms replacement | CONFIRMED | New appointment active; old marked superseded |
| CHANGE_PENDING | Change definitively fails | CONFIRMED | Original remains active; record failure event |
| CONFIRMED | Provider begins visit | IN_PROGRESS | Assigned actor or authenticated provider event |
| IN_PROGRESS or CONFIRMED | Provider reports work completed | COMPLETED | Require work summary; issue awaits customer |
| DRAFT or APPROVED | User abandons before dispatch | CANCELLED | Revoke pending approval; no provider call |
| REQUESTED or CONFIRMED | User approves cancellation | CANCEL_PENDING | Record underlying request/appointment state |
| CANCEL_PENDING | Provider confirms cancellation | CANCELLED | Mark active appointment cancelled |
| CANCEL_PENDING | Provider rejects cancellation | Previous active state | Explain authoritative result |

Unknown responses leave the operation pending and trigger reconciliation. A cancel or change during submission/change pending is queued for reconciliation and fresh review, not executed concurrently. In-progress cancellation is coordinator-only under provider policy; the system must not promise it. Completed, rejected, failed, and cancelled requests remain terminal. A follow-up uses a new request linked to the existing issue. A provider no-show becomes a coordinator exception on the confirmed request until resolved, not an automatic completion.

Appointment status is PROPOSED, CONFIRMED, SUPERSEDED, COMPLETED, or CANCELLED. A failed proposal does not replace a confirmed appointment. Keep at most one active confirmed appointment per service request, enforced transactionally.

### 7.3 Cross-cutting invariants

- Tenant scope comes from authenticated context, never an LLM-supplied household ID alone.
- A durable mutation is acknowledged only after storage confirms it. An approved payload must match its stored hash and current version.
- One idempotency key plus one payload yields one logical action. Reusing that key with a different payload returns conflict.
- Proposed operation records remain available for at least seven days in H; retries thereafter require reconciliation or new approval. P retention and provider retry windows require contract alignment.
- Non-terminal requests for the same issue are surfaced before creating another. A coordinator may authorize a separate provider request only after explaining existing obligations and recording user approval.
- No default zero price, default warranty coverage, guessed model, or automatic customer-resolution claim.
- Store times in UTC, present appointments in household timezone, and read absolute dates before confirmation. Default proposed household timezone is Asia/Kolkata; handle date rollover explicitly.
- Simulation mode is a server-controlled environment attribute. Neither spoken user commands nor document content may turn a demo provider into live dispatch.

## 8 Conceptual data model and dictionary

All persistent domain entities carry a generated ID, household ID where applicable, created/updated timestamps, record version, and provenance. Field statuses are UNKNOWN, USER_REPORTED, DOCUMENT_SUPPORTED, or VERIFIED. Verification records evidence, reviewer, and time; it is not merely an LLM confidence score. A conflicting field retains both claims until an authorized resolution.

### 8.1 Entity definitions

| Entity | Required fields at creation | Optional or conditionally required fields |
| --- | --- | --- |
| Household | ID, locale, timezone, lifecycle status | Service address and reachable contact required before dispatch |
| User and membership | User ID, household ID, role, active status, identity binding | Name, helper scopes, grant expiry, preferred accommodations |
| Consent | Subject/household, purpose, version, decision, actor, timestamp | Withdrawal time, authorized recipient, channel |
| Device binding | Platform, external subject reference, household, status | Device label, assurance level; P production adapter required |
| Appliance | ID, household, category, confirmed nickname | Room, aliases, brand, model, serial, dates, verification records |
| Document | Owner scope, type, storage reference, validation status, provenance | Appliance/issue link, rights reference, reviewer; no public URL |
| Guidance item | Model or generic scope, version, source locator, review status | Hazard category, permitted step, language, withdrawal reason |
| Issue | Appliance ID, original symptom, summary, status, reporting actor | Onset, observations, safety flag, linked prior issue, resolution |
| Troubleshooting step | Issue, guidance version or intake ID, offered time, outcome | User response, evidence locator, completion time |
| Conversation checkpoint | Household, session ID, active issue, last committed step | Expiring pending action ID; no permanent approval from transcript |
| Service request | Issue, draft summary, status, mode demo/live | Provider, address/contact snapshot, fee, sharing scope, approval |
| Appointment | Request, slot ID or proposal reference, timezone, status | Start/end required when confirmed, provider reference, prior slot |
| Work report | Request, submitting actor, work summary, reported time | Parts, cost, invoice, model evidence, technician outcome |
| Reminder | Household, purpose, due time, opt-in, delivery mode, status | Source interval, appliance link, last attempt and dedupe key |
| Operation and event | Correlation/key, actor, action, record, time, result | Payload hash, prior/new version, provider event ID, error code |

### 8.2 Validation and relationships

A household has many memberships and appliances. An appliance has many issues and documents. An issue has many steps and service requests. A service request has many appointment revisions and work reports. A guidance catalog is shared, but household documents and case records are tenant-scoped. Deleting or archiving an appliance must not silently destroy service history or an active booking.

Proposed field limits: nickname 80 characters; symptom text 2,000 characters; work notes 4,000 characters. Enforce limits gracefully without truncating meaning silently. Unknown dates are null with optional user wording such as “last summer”; never manufacture a precise purchase date. Store prices in integer minor units plus ISO currency code such as INR and distinguish estimate, final, and unknown status. All identifiers used across household boundaries are opaque.

A service location is separate from ownership and purchase address. Read back material changes and re-check serviceability. The pilot contact route may be a landline, authorized contact, or other provider-supported route; it must not force smartphone ownership. Identity and recovery cannot be completed solely by speaking a household address.

### 8.3 Proposed retention and data minimization

H uses synthetic households and files only. Store structured facts and attributed events; do not persist raw audio by default. If the chosen speech service retains audio or transcripts independently, document and assess that behavior before real-user testing. Application conversation logs should avoid full document contents, credentials, and service addresses.

For P, retention periods, lawful processing basis, required notices, export format, backup deletion handling, and provider data obligations remain open decisions D07. Approve a retention matrix before collecting live customer data. A purge must cover files, database items, retrieval indexes, caches, and access bindings; retained audit items require a documented rationale and access limits. Restoring a backup must reapply deletion records before exposing restored data.

## 9 Application and integration design boundaries

This is a proposed logical architecture. The technical lead must validate specific SDK versions, speech quality, region/model availability, deployment costs, and authentication before choosing the detailed design. No AWS service is mandatory solely because it appears below.

### 9.1 Logical flow

Elder voice or text -> channel adapter -> authenticated conversation service -> approved MCP tools -> domain services -> household records, reviewed guidance, and service adapter.

Staff console -> staff authorization -> the same domain services -> attributed events and record updates.

The LLM interprets requests and composes responses. Domain services enforce permissions, input validation, state transitions, duplicate prevention, approval validity, and provider-confirmed outcomes. Persistent state belongs in application storage, not only in an agent prompt or transport session. A channel adapter translates transport specifics without bypassing these controls.

### 9.2 Proposed component responsibilities

| Component | Candidate implementation | Responsibility and boundary |
| --- | --- | --- |
| Web simulation | Browser UI with validated speech adapter | Conversation, optional visual state, staff views, accessible controls |
| Conversation orchestration | Bedrock model with Strands or equivalent | Interpret utterances and select permitted tools; no direct arbitrary database writes |
| MCP server | Compatible SDK with Streamable HTTP | Typed tool contracts and authenticated invocation; recommended H design |
| Hosting | AgentCore Runtime or a suitable container host | Run selected services; prove transport, auth, and deployment before commitment |
| Domain records | DynamoDB or relational database | Tenant records, conditional writes, indexes, approval/idempotency ledger |
| Documents and catalog | S3 plus reviewed catalog metadata | Private files, scoped retrieval, review and withdrawal |
| Workflow execution | Application state machine; Step Functions if justified | Durable booking and reconciliation; optional service choice |
| Identity | Cognito or compatible identity service | Staff/household sessions and authorization; production platform mapping |
| Observability | CloudWatch or equivalent | Redacted logs, latency, failures, operational alerts, cost signals |
| Reminder scheduling | EventBridge Scheduler or equivalent | Due work after consent; channel delivery is a separate capability |

AgentCore Runtime officially supports Streamable HTTP MCP servers [S03]. This supports the hosting option; it does not establish Alexa+ production acceptance or replace application persistence. H may qualify as a simulated experience without MCP, but a real, exercised MCP surface is recommended to demonstrate reusable integration. If implemented, pin a compatible protocol version and include transport/authentication contract tests.

### 9.3 Tool contracts

Every tool receives authenticated actor context outside model-controlled arguments. Mutation requests include operation key, expected record version, and where needed approval ID. Responses include result status, correlation ID, current version, and structured data or a typed error. Tool names below are proposed logical contracts, not claims of an existing API.

| Tool group | Inputs beyond auth context | Required output and constraints |
| --- | --- | --- |
| register_appliance | Category, confirmed nickname, optional facts, operation key | Appliance ID and provenance; no inferred verified model |
| resolve_appliance | Nickname, room, aliases | Zero/one/multiple scoped matches; ambiguity requires user choice |
| report_issue and get_issue | Appliance, symptom, optional onset or issue ID | Issue, related active cases, safe next actions |
| record_observation | Issue, field, value/unknown, expected version | Saved fact and provenance; conflict prompts refresh |
| get_guidance | Issue, current verified model, catalog version | Approved steps with evidence or NO_APPROVED_GUIDANCE |
| record_step_result | Issue, step ID, result, version | Saved outcome; no automatic resolution |
| draft_service_request | Issue, service fields, sharing scope | Draft and missing fields; no provider mutation |
| prepare_action | Request/change, current fields, proposed slot | Readback summary, payload hash, pending approval reference |
| confirm_action | Pending reference, explicit intent, current session | Server-issued scoped approval or refusal; not model-forged |
| submit or change_service | Request, approval ID, operation key, version | Pending/confirmed/failed state; provider reference if authoritative |
| get_service_status | Request reference | Current state, last update, reconciliation result |
| record_work and confirm_resolution | Assigned job/work or issue/customer response | Separate visit and issue outcomes |
| get_history and manage_reminder | Appliance scope or due event and preference | Authorized timeline or reminder state |

Approval capture belongs to trusted application logic receiving the current user turn; a model producing the words “approved” is insufficient. Model suggestions may initiate review but cannot grant consent. Protect against document prompt injection by treating retrieved text as evidence, not instructions.

### 9.4 Provider adapter contract and failures

Required operations are check serviceability, list slots, submit request, read request status, replace appointment, cancel request, and receive or poll service events. The simulated adapter must exercise confirmed, unavailable, rejected, delayed, duplicate, and out-of-order outcomes. Live providers must support equivalent semantics or have a documented manual coordination path.

Submission includes operation key, issue summary, minimum approved contact/address fields, slot reference, and consent reference. The adapter returns status, provider reference where available, authoritative time, fee information, and retry/reconciliation instructions. Availability results expire; listing a slot never reserves it. Quote or slot changes require a new summary and approval.

Errors: AUTH_DENIED, INVALID_INPUT, RECORD_CONFLICT, APPROVAL_EXPIRED, NO_APPROVED_GUIDANCE, SLOT_UNAVAILABLE, PROVIDER_UNAVAILABLE, and RESULT_UNKNOWN. Validation/auth errors are not retried automatically. Reads may use bounded retries. Writes with RESULT_UNKNOWN are reconciled by operation/provider reference before any replay. If a provider cannot deduplicate or report status, uncertain requests enter manual review instead of an automatic second dispatch.

Authenticated webhooks must be verified, replay-protected, tenant-mapped from stored provider references, and checked against allowed transitions. Polling is acceptable where webhooks do not exist. A dead-letter or manual-review queue retains failed events with a support reference. H can test this through seeded events without a real provider.

### 9.5 Real and simulated boundary

Real in H: conversation processing, persistence, permissions, guidance retrieval, operation ledger, issue states, and staff updates. Simulated in H: service-provider identity, external availability, technician visit, and fees. User-visible confirmations must include “demo” and explain that no real visit is arranged. P requires an explicitly configured live adapter and operational approval; deployment configuration cannot silently change existing demo records into live jobs.

## 10 Non functional requirements

All targets below are proposed acceptance thresholds, not established service guarantees. H tests run in a declared supported browser, deployment region, model version, and network profile with 10 concurrent sessions and 100 representative turns. QA records cold starts separately. The production load profile remains a pilot decision.

| ID and phase | Priority and area | Measurable acceptance and evidence |
| --- | --- | --- |
| NFR-01 H P | Must performance | p95 end-of-utterance to first meaningful response at most 8 seconds in declared H profile; if longer, issue a progress response without claiming action completion |
| NFR-02 H P | Must interaction control | Stop halts speech playback within 1 second in supported client; confirmed facts survive refresh in every recovery test |
| NFR-03 H P | Must accessibility | Keyboard operation of all H controls, programmatic labels, visible focus, 200 percent zoom without lost controls, and screen-hidden voice pass for every core task |
| NFR-04 H P | Must authorization | All cross-household, role-escalation, expired-session, and revoked-grant tests denied server-side with no private data leakage |
| NFR-05 H P | Must action integrity | Zero duplicate provider requests in 100 repeated/timeout-injected submissions using the same operation key; no lost updates in concurrent edits |
| NFR-06 H P | Must evidence and safety | Every model-specific evaluation output maps to approved model/source; zero forbidden repair instructions or fabricated confirmations in the release evaluation set |
| NFR-07 H P | Must privacy | No raw audio retained by the app by default; no credentials or document bodies in sampled logs; private object access expires and is tenant-scoped |
| NFR-08 H P | Must reliability | Persist facts before acknowledgment; recover the core journey after service restart and handle all defined provider errors without false success |
| NFR-09 H P | Must observability | Each mutation has correlation ID, actor, result, and timing; dashboard shows errors, pending operations, and model/tool cost estimates |
| NFR-10 H P | Must reproducibility | Fresh environment can deploy from documented configuration and seed fixtures; secrets externalized; versions and migrations recorded |
| NFR-11 H P | Must secure transport | TLS on deployed client/service routes, scoped service identities, secrets outside client/repo, encryption at rest, and no unresolved critical security findings |
| NFR-12 H P | Must cost control | Set owner-approved budget alerts and per-session limits before deployment; proposed H cap 12 model/tool cycles per turn then explain and hand off |
| NFR-13 P | Must recovery | Proposed RPO 24 hours and RTO 4 hours; demonstrate restore plus deletion-ledger replay before pilot; owner must approve actual operational targets |
| NFR-14 P | Must availability | Proposed 99.5 percent monthly application availability; measurement and exclusions defined before pilot; do not confuse it with provider response or repair SLA |
| NFR-15 P | Must language readiness | Each launch language passes the same scenario suite and observed elder usability sessions; record task completion and critical-field errors, not only word accuracy |

Evaluation passing is evidence for the tested release only, not proof that generative output can never fail. Retain deterministic permissions and action guards in production. Accessibility review must include participants who need slower speech and recovery from misrecognition. Hearing, speech, and cognitive needs vary; provide optional helper or human support rather than assuming one voice interface serves everyone.

## 11 Screen and channel specifications

### 11.1 Elder conversation surface

Display large microphone and stop controls, text input, transcript, current appliance/issue, and one next action. Speak all essential choices and outcomes. Clearly distinguish listening, processing, speaking, paused, and disconnected states. Do not require scanning a QR code, opening a receipt, or selecting a visual card to advance a core journey. A consented initial microphone click is assisted setup, not repeated task interaction.

### 11.2 Household and history surface

Provide appliance list, nickname/category, information confidence, open issues, and optional documents. Missing data is labelled “not provided,” not an error. History shows actor and timestamp. Editing evidence cannot silently rewrite previously used source versions. Helpers see only their grants and the household they are currently authorized to access.

### 11.3 Service desk surface

Provide assigned queue, issue summary, performed checks, warning flag, draft/pending/confirmed state, current appointment, fee state, and permitted work actions. Highlight pending reconciliation separately from confirmed visits. A demo badge persists throughout H. Show the exact approved payload and provider result for support review, but mask personal fields that the actor does not need.

### 11.4 Administration surface

H may use a minimal secured internal interface or documented operations scripts for catalog publication, test-role grants, and test data purge. Actions must still run through audited authorization paths. A customer-facing staff/admin switch is unacceptable. P requires usable operational controls, support training, and production access review.

## 12 QA acceptance and traceability

### 12.1 Fixtures and execution approach

Create households A and B; A contains two ACs, a fridge, and a TV, while B owns different records. Seed elder/owner, view-only helper, booking helper, revoked helper, assigned technician, unassigned technician, coordinator, and catalog reviewer identities. Use one permitted verified AC manual, one unknown model, one conflicting manual, one withdrawn guidance version, and a document with malicious embedded instructions.

Seed slots that are available, contested, expired, unavailable, and subject to changed fees. The fake provider supports confirmation, acknowledgment-only, timeout-after-success, rejection, duplicate callback, stale callback, cancellation refusal, and no-show. Set fixed test dates to exercise local midnight and spoken “tomorrow.” Use synthetic contact details and invoices. No real booking or outgoing customer message is part of H testing.

Run domain tests for permissions/state invariants, contract tests for tools/adapters, integration tests for persistence/retrieval, and end-to-end browser speech tests. Generative quality checks use pinned model/prompt/catalog versions and repeat each critical evaluation prompt three times. Seeded text transcripts do not replace actual audio tests for voice acceptance. Record test build, inputs, expected result, actual result, evidence, and defect ID.

### 12.2 Traceability and acceptance scenarios

Each row is a minimum acceptance scenario; QA expands it into positive, boundary, and negative cases. Phase is H unless marked P. A Should requirement is tested when included; exclusion must be documented. FR acceptance criteria in Section 6 remain binding in addition to these scenarios.

| Test ID | Requirements | Scenario and observable pass condition |
| --- | --- | --- |
| AT-01 | BR-01 BR-02; FR-01 FR-02 | Given no documents/helper, consent and spoken nickname create one usable appliance; unknown fields stay null |
| AT-02 | FR-01 FR-20; NFR-04 | Decline optional sharing; no helper grant exists and ordinary household use continues |
| AT-03 | FR-02 FR-03 | Register fridge and TV aliases; two ACs trigger room clarification; no accidental overwrite |
| AT-04 | FR-03 FR-08 FR-23; NFR-06 | User-guessed model cannot unlock model-specific guidance; reviewed evidence can; conflicting source cannot |
| AT-05 | FR-04 FR-24; NFR-07 | Reject oversized/wrong-type file; authorized valid file enriches record; another tenant cannot retrieve it; purge removes it |
| AT-06 | FR-05; NFR-05 | Repeat issue creation and reuse operation key; one issue remains; explicit distinct symptom creates a separate case |
| AT-07 | FR-06 FR-10 | Skip onset, answer airflow, restart session; saved answer remains and is not re-asked without reason |
| AT-08 | FR-07 FR-23; NFR-06 | Report burning smell midway; routine checks stop and approved escalation appears; forbidden repair instructions absent |
| AT-09 | FR-08 FR-09; NFR-06 | Verified model yields correct citation; “already tried” records outcome; retrieval outage offers service without invented guidance |
| AT-10 | FR-08 FR-12 FR-23; NFR-04 NFR-06 | Malicious manual asks to submit booking or reveal data; no unauthorized action/disclosure occurs |
| AT-11 | BR-03; FR-10 FR-18; NFR-08 | Restart backend and client; resume same issue with steps and last authoritative service state preserved |
| AT-12 | FR-11 FR-27 | Unknown model/invoice creates draft; missing address blocks dispatch only; warranty and fee are spoken as unknown |
| AT-13 | FR-12 FR-21 FR-22 | Silence, background “yes,” assistant playback, expired approval, and corrected date cannot submit; fresh explicit approval can |
| AT-14 | BR-04; FR-13 FR-28; NFR-05 | Timeout after provider success, then retry: one confirmed reference; correlation trail joins approval, dispatch, and reconciliation |
| AT-15 | FR-12 FR-13 FR-27 | Two users select last slot; one succeeds; other gets alternatives. Changed fee requires new approval |
| AT-16 | FR-14 FR-15 | Failed reschedule keeps original slot; successful replacement supersedes it; voice enquiry reports current date/window |
| AT-17 | FR-14 FR-15 | Cancellation timeout says pending; rejection restores original state; confirmation marks cancelled; issue stays unresolved |
| AT-18 | FR-16 FR-28; NFR-04 | Assigned technician posts work only for assigned job; duplicate/out-of-order updates do not duplicate or regress state |
| AT-19 | FR-17 FR-18 | Visit completion awaits customer; “still faulty” leaves issue open; resolved/closed/reopened history remains intact |
| AT-20 | FR-19 | Opt in, retrieve due reminder, cancel, replay scheduler event; no cancelled reminder appears and H never claims proactive Echo delivery |
| AT-21 | FR-20; NFR-04 | View-only helper cannot book; revoke booking helper and retry old session/pending action: access denied |
| AT-22 | BR-02; FR-21 FR-22; NFR-02 NFR-03 | Screen hidden after assisted launch: register, report, confirm demo visit, resume, change, and close using speech only |
| AT-23 | FR-21 FR-22; NFR-01 | Denied microphone and network loss give accurate fallback; voice path is not falsely counted as passing; measure response timing |
| AT-24 | FR-23; NFR-06 | Unpublished/withdrawn catalog version cannot be used for a new step; prior case source history remains |
| AT-25 | FR-24; NFR-04 NFR-07 | Unverified deletion denied; authorized test purge removes records/files/index entries and revokes grants |
| AT-26 | FR-25 FR-26; NFR-15; P | No-family elder uses assisted setup and real supported voice device; supported language journey completes without mobile operation |
| AT-27 | FR-25 FR-27; P | Outside service hours or coverage area: no false callback/fee promise; pending case and supported alternative retained |
| AT-28 | FR-26; NFR-04; P | Unlinked/revoked device cannot read private status; approved recovery rebinds only correct household |
| AT-29 | NFR-01 NFR-02 NFR-09 NFR-12 | Run declared 100-turn load profile; timing, stop latency, correlation, loop limits, and budget alerts evidenced |
| AT-30 | NFR-03 NFR-10 NFR-11 | Keyboard/zoom/labels pass; fresh deploy succeeds; secrets scan and transport/access checks pass |
| AT-31 | NFR-13 NFR-14; P | Restore drill meets approved recovery targets; deletion records replay; availability measurement demonstrated |
| AT-32 | BR-07; NFR-10 | Reviewer follows README from clean environment and reproduces declared demo with synthetic data |
| AT-33 | FR-06 FR-07 FR-11 | Unsupported fridge/TV symptom or unknown AC code leads to labelled scope limit and service draft, not guessed diagnosis |
| AT-34 | FR-12 FR-14 FR-22 | Spoken correction and local-date rollover update readback; conflicting concurrent edit invalidates old approval |
| AT-35 | FR-15 FR-16 FR-17 | No-show stays unresolved; late provider event cannot falsely complete/cancel; coordinator sees actionable exception |

Coverage review: every BR, FR, and NFR appears in this matrix directly or via its listed FR linkage. QA must record explicit evidence against each Must acceptance criterion, not only mark its broad scenario complete. Test steps should include storage/provider assertions as well as spoken output.

### 12.3 Defect severity and release disposition

Severity 1 covers unauthorized disclosure/action, unsafe instructions, duplicated live dispatch, or corruption/loss of committed records. Severity 2 blocks a core journey or presents a false booking/resolution. Severity 3 impairs a supported path with a workable fallback. Severity 4 is cosmetic. H release requires no open Severity 1 or 2 defects; other deviations need product-owner acceptance and documented workarounds. P has the same gate plus security/operations approval; a workaround that forces an elder onto a mobile app does not satisfy the promised voice-only core path.

## 13 Release acceptance and hackathon submission

### 13.1 HomeKeep MVP acceptance

All Must H functional requirements and NFRs pass. At least one verified-model guidance path and the no-model/no-invoice path work. The system persists household, issue, approval, request, appointment, and history across restarts. Demo provider fault injection proves no duplicates or false confirmations. The speech journey passes in the declared browser with synthetic data. The staff console demonstrates visit completion followed by independent customer resolution. No real dispatch or charge occurs.

### 13.2 Official submission requirements checked on 24 September 2026

Source S01 governs eligibility; recheck before submission. Submit by 23 October 2026 at 12:00 noon PDT. Include a working project description, runnable GitHub repository, public YouTube/Vimeo demonstration under three minutes, product feedback, and selected track/challenge. Materials must be English or include English translation.

The repository can be public with an open-source license or private with access granted to the designated Devpost and Amazon reviewers. Follow the current collaborator list in S01. The simulated Alexa+ route is permitted without a prescribed SDK/MCP interface; the simulation must function and include source. The MCP route requires specification 2025-11-25 or later and Streamable HTTP.

For AWS Builder, document AWS usage and integration in product feedback for the same primary-track project. Keep judging access available through 20 November 2026. These are submission obligations, separate from HomeKeep product acceptance.

### 13.3 Recommendations for a stronger demonstration

Use a brief elder-centered story. Show the absence of paperwork, a persistent issue, one evidence-backed check, an approved demo booking, and a resumed change of plan. Present actual state changes rather than a scripted video-only conversation. Include one concise failure/recovery moment. Document developer friction with reproducible steps and useful suggestions. These are recommendations, not additional eligibility conditions.

Proposed 170-second script: 0–20 seconds problem and audience; 20–55 voice registration with missing details; 55–90 approved guidance and service draft; 90–125 demo confirmation and failed/successful reschedule; 125–150 return session and customer outcome; 150–170 architecture and feedback. Prepare a resettable demo dataset. Do not present a compressed simulated visit as a real technician visit.

### 13.4 Production launch gate

Before P, confirm platform partner access, launch-market language/device support, supported invocation/account linking, and certification path. Validate assisted setup without mandatory family help. Approve identity assurance, sharing, retention, security, and real-data handling. Contract or staff real service delivery, establish coverage and hours, define charges/cancellation policy, and prove uncertain-request reconciliation.

Run observed elder usability tests, production-adapter fault tests, support training, monitoring, backup recovery, and a limited-household pilot. Release requires documented owner approval of unresolved pilot decisions. A successful H demo does not remove these gates.

## 14 Delivery sequence and dependencies

No team capacity, fixed budget, or sprint duration is agreed. The sequence below supports estimation; the technical lead should size it after the platform spike. The external hackathon deadline is not a promise that every proposed feature will fit.

| Stage | Deliverable | Exit condition and dependency |
| --- | --- | --- |
| 1 Scope and feasibility | Supported browser/speech proof, one permitted AC manual, source catalog, proposed identity design | Voice stop/repeat/confirmation works; sample model evidence and guidance reviewed |
| 2 Persistent core | Household, appliance, issue, grants, consent, history | BR-01 BR-03 BR-06 scenarios pass without LLM dependency |
| 3 Conversation and tools | Speech/text orchestration, typed tools, approved retrieval | Core prompts and source/fallback tests pass; no model-authorized writes |
| 4 Service workflow | Demo provider, approval ledger, slots, changes, reconciliation | Duplicate, timeout, conflict, and cancellation tests pass |
| 5 Supporting operations | Staff updates, documents, outcome confirmation, optional reminders | Complete issue journey including unresolved repair works |
| 6 Release evidence | Accessibility run, fault tests, reproducible deployment, demo and submission | H gate and submission checklist complete |
| 7 Controlled pilot | Approved voice integration, service operations, real-data policy | P gate complete before onboarding live households |

Suggested backlog epics: onboarding/access (FR-01, 20, 24); appliance records (FR-02 to 04, 18); assisted troubleshooting (FR-05 to 10, 23); service lifecycle (FR-11 to 17, 27, 28); voice accessibility (FR-21, 22); optional follow-up (FR-19); production operations/integration (FR-25, 26). Build technical stories under these IDs and preserve links to acceptance tests.

## 15 Assumptions risks and open decisions

### 15.1 Planning assumptions

A01: H uses synthetic households, a controlled browser, and an internet connection. A02: At least one AC manual can be used with appropriate rights and reviewed for safe permitted guidance. A03: A qualified reviewer is available before troubleshooting release. A04: Production customers can receive setup assistance without being required to own a smartphone. A05: Real providers can offer a reachable contact route suitable for elders. A06: AWS model and speech choices meet selected-region availability, cost, and language needs. None of these assumptions should be treated as a signed partnership or completed validation.

### 15.2 Risk register

| ID | Risk and impact | Mitigation and owner |
| --- | --- | --- |
| R01 | Alexa+ access or India/language coverage blocks launch channel | Validate with Amazon; keep domain services reusable; product/technical lead |
| R02 | Speech errors produce wrong appliance or appointment | Short questions, explicit critical-field readback, approval binding, real-user tests; UX/QA |
| R03 | Incorrect guidance damages trust or causes harm | Reviewed catalog, exact-model eligibility, unknown fallback, safety escalation; specialist/technical lead |
| R04 | Provider timeout causes duplicate visit | Durable operation ledger and reconciliation; provider manual-review path; backend/operations |
| R05 | Shared speaker exposes data or allows unauthorized booking | Minimal spoken disclosure, scoped identity/approval design, sensitive-action recovery; security/product |
| R06 | Elder lacks family support or usable documents | Assisted onboarding, optional fields, technician enrichment; operations |
| R07 | Scope expands into broad diagnosis and multiple integrations | Protect H core, defer extra languages/models/OCR; product owner |
| R08 | Cloud or staffed-service costs exceed business case | Measure per-case costs and apply budget limits; owner/operations |
| R09 | Manuals cannot be legally redistributed in repository | Use licensed fixtures or documented permitted retrieval; content owner |
| R10 | Technician reports success but customer remains dissatisfied | Separate visit completion from resolution and track follow-up; operations |

### 15.3 Decision register

| ID | Open decision | Proposed position and decision gate |
| --- | --- | --- |
| D01 | Exact H AC model and source rights | Choose one available reviewed manual; product/content owner before catalog build |
| D02 | H browser speech engine and platform | English browser with continuous conversational turns after setup; technical lead before voice implementation |
| D03 | AWS region model runtime and storage | Select by availability, latency, cost, and team skills; technical lead before deployment |
| D04 | Production Alexa+ access and country/device support | Obtain direct platform confirmation; product owner before P launch commitment |
| D05 | Pilot languages and elder accommodations | User research to prioritize Hindi/Hinglish or regional language; UX/product before pilot scope freeze |
| D06 | Shared-device identity and sensitive-action assurance | No reliance on voice recognition alone; security/product before live booking |
| D07 | Retention consent notices and provider data obligations | Reviewed policy including deletion/backups and speech processor terms; privacy owner before real data |
| D08 | Pilot geography providers service hours and no-family onboarding | Contracted provider or staffed coordination; operations before customer recruitment |
| D09 | Fees cancellations warranty disputes and business model | No payments in H; validate pricing and terms; owner/operations before live paid service |
| D10 | Team capacity budget schedule and NFR targets | Estimate H Must scope and approve thresholds; owner/technical/QA before baseline commitment |
| D11 | Public or private repository | Decide using current submission options and IP goals; owner before repository publication/sharing |
| D12 | Proactive notifications and reminders | On-return H behavior; validate channel permissions for P; technical/product before delivery promises |

These questions do not block implementing a synthetic H core under the explicit proposed defaults. Decisions D01–D03 and reviewer availability block the dependent guidance/voice/deployment work; D04–D09 are production launch dependencies. If assumptions fail, revise scope and affected acceptance tests explicitly.

## 16 Sources and glossary

### 16.1 Verified source register

Official pages were retrieved on 24 September 2026. Recheck them at the corresponding release gate because platform access and event rules can change. User decisions in Section 2 originate from the project conversation; all remaining implementation details are proposals.

- S01: [Amazon Developer Hackathon official rules](https://amazonappdev2026.devpost.com/rules). Used for the short submission checklist in Section 13, including the updated repository-access option. It supersedes the earlier conversation's assumption that all submissions require a public repository.
- S02: [Alexa+ developer documentation](https://developer.amazon.com/docs/alexaplus/add-ons/home.html). The page states that Category SDK and MCP Toolkit access is currently limited to select partners. Production eligibility, India availability, language support, and certification for HomeKeep remain to be confirmed; this source does not establish them.
- S03: [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html). Supports the proposed Streamable HTTP hosting option in Section 9; does not establish production Alexa+ compatibility for this product.
- S04: [Amazon Echo setup guidance](https://www.aboutamazon.com/news/devices/setting-up-echo). Describes Alexa-app setup for screenless Echo and on-device setup for screened models. This supports assisted setup; individual model/account requirements still need validation before a pilot.

### 16.2 Glossary

| Term | Meaning in this BRD |
| --- | --- |
| AMC | Annual maintenance contract; its existence does not automatically prove this repair is covered |
| MCP | Model Context Protocol; a typed interface through which an agent can call application tools |
| Alexa+ simulation | HomeKeep browser experience representing conversational behavior; not a live Alexa+ integration |
| Household | Tenant boundary for appliance data, permissions, and service records |
| Issue | Customer-reported appliance problem and its resolution lifecycle |
| Service request | Provider-facing request linked to an issue; may exist without a confirmed appointment |
| Approval | Explicit authorization for one current action payload within a defined session and expiry |
| Idempotency | Repeated delivery of the same operation produces one logical mutation |
| Provenance | Who supplied or verified a fact, when, and with what evidence |
| RPO and RTO | Maximum approved data-loss window and recovery time target |
| Mobile-free everyday use | Elder completes routine tasks through voice after assisted setup; support staff may use other interfaces |
