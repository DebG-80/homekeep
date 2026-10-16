# Submission checklist (owner)

For Deb. Tick each item with the evidence location. Rules were checked on 25 September 2026 against the official rules page [S01] (https://amazonappdev2026.devpost.com/rules).

## Key dates

| Date (2026) | What |
| --- | --- |
| 20 Oct | Internal target: submission complete |
| **21 Oct, 12:00 PT** | Credits request form closes |
| **23 Oct, 12:00 PDT** | Submission deadline |
| 20 Nov | End of judging: demo must stay live and free until then |

## 0 Recheck the rules

- [ ] Re-read the rules page [S01] and the Updates tab in the week of submission. Note any change here, and update TDD §2 through a proposal (the TDD is read-only).

## 1 Eligibility (TDD §2)

- [ ] **Alexa+ track:** self-hosted MCP server on spec `2025-11-25` over Streamable HTTP. Evidence: contract-test log of the `initialize` handshake with `protocolVersion: 2025-11-25`; MCP Inspector session in the video.
- [ ] **Runtime hook:** the MCP technology is imported and actually called at runtime. Evidence: code path `app/orchestrator/agent.py` → `mcp.client.streamable_http`; a correlation trail joining turn → MCP call → domain write.
- [ ] **Simulated Alexa+ experience:** the browser voice client sits on top of the MCP path. Evidence: the video shows both.
- [ ] **AWS Builder:** AWS services with documented integrations. Evidence: `docs/product-feedback.md` pasted into the Product Feedback answer.
- [ ] **Repository:** all source, assets and setup/run instructions. Evidence: README, `docs/infra-contract.md`; AT-32 walk-through from a clean account.
- [ ] **Working demo** shown in a video under 3 minutes.
- [ ] **Free access until 20 Nov**; credentials only in the Devpost testing-instructions field.
- [ ] **Third-party material:** fictional manual and brand; `fixtures/PROVENANCE.md` present; no copyrighted music.
- [ ] **English** materials.

## 2 Repository

- [ ] Repository is public.
- [ ] `LICENSE` (Apache-2.0) is detected and shown in GitHub's About panel.
- [ ] README has clear setup and run instructions (local and AWS).
- [ ] CI is green on `main`: `lint`, `test`, `audit`, `gitleaks`.
- [ ] No secrets or real identifiers in the history (gitleaks full-history scan green).

## 3 Runtime MCP hook evidence

- [ ] Contract-test output saved (handshake version, trusted-tool refusal).
- [ ] Screenshot or clip of MCP Inspector connected to the hosted `/mcp`.
- [ ] Log excerpt showing one turn's correlation ID across the turn, the MCP call and the domain write (redacted per TDD §10.2).

## 4 Video and Devpost fields

- [ ] Video under 3:00, captions on, no copyrighted music, no real brands or people (`docs/submission/video-script.md`).
- [ ] Video uploaded (YouTube or Vimeo) and linked.
- [ ] Story sections pasted from `docs/submission/description.md`.
- [ ] Built-with tags from `docs/submission/built-with.md`.
- [ ] Testing instructions from `docs/submission/testing-instructions.md`, with real values typed **only in the Devpost field**.
- [ ] Product Feedback from `docs/product-feedback.md`.
- [ ] Feature requests from `docs/submission/feature-requests.md` (if there is a field for them).

## 5 Friction log

- [ ] `docs/friction-log.md` entries reviewed, reproducible and pasted into the submission (up to 10% bonus).

## 6 Live until 20 November

- [ ] Budget USD 75/month with alerts at 50%, 80% and 100% (`docs/infra-contract.md` §12).
- [ ] External uptime check on `/healthz` every 5 minutes.
- [ ] Judge households J1–J3 seeded and reset; "Reset my demo data" tested.
- [ ] Calendar reminder to tear down after 20 November.

## 7 Optional: Open Source mini challenge

- [ ] Decide yes or no. A public primary repo alone does **not** qualify; the rule asks for a new, additional open-source project or a contribution to an existing public repo, made during the window. Candidate: extract the provider simulator or the attested-approval MCP pattern as its own licensed package. A project can win only one mini-challenge prize (HANDOFF §3).
