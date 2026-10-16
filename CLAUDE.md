# HomeKeep — project memory for Claude Code

HomeKeep lets elders in Indian households get appliance help by voice, without invoices or a mobile app. It keeps each appliance case alive across conversations, from a spoken problem to a customer-confirmed fix. This repo is the **hackathon release (H)** for *Build, Ship, Shape: Amazon Developer Hackathon*: the Alexa+ track (self-hosted MCP server) and the AWS Builder mini challenge. Deadline: **23 Oct 2026, 12:00 PDT**; internal target 20 Oct.

## Sources of truth

| File | Use it for |
| --- | --- |
| `intent/homekeep.md` | Why we are building this; constraints. Read-only. |
| `docs/HomeKeep_TDD_H_v1.0.md` | **The build spec.** Components, modules, MCP tools, data, state machines, guards, tests. Read-only: propose changes, don't drift. |
| `docs/HomeKeep_BRD_v1.0.md` | Requirement IDs (BR/FR/NFR/AT) and acceptance scenarios. Only H-phase items are in scope. Read-only. |
| `docs/architecture/interactions.md` | The 24 numbered interactions and flows A–G. |
| `docs/HANDOFF.md` | Decisions, verified platform facts, hackathon rules, and the slice order. |
| `plans/*.md` | The approved plan for each slice. Code must match its plan. |

## Workflow (AI-native SDLC, see `docs/SDLC.md`)

1. **Plan mode first.** For each slice in HANDOFF §6, propose a plan (files, order of work, risks, proof). Iterate with Deb, then save it as `plans/slice-N.md`. Deb commits the plan before any code is written.
2. **Build** to the plan. If you must deviate, update the plan file in the same change and say why.
3. **Verify** your own work (below), then run the `verifier` subagent for an independent check.
4. **Review:** run the `reviewer` subagent against `REVIEW.md` on the branch diff.
5. **Deb** reviews, commits, pushes, merges and deploys. You never do.

## Division of work

- **You (Claude Code):** application source, fixtures, catalog content, tests, Dockerfile, Makefile, local run setup, README, and `docs/infra-contract.md`.
- **Deb:** all AWS provisioning and deployment, and every git commit/push. Enforced by `.claude/settings.json`. Don't write CDK or Terraform unless asked.

## Commands (created in Slice 0)

- `make test`: unit + contract tests (pytest, moto, fake model). Must exit 0.
- `make lint`: ruff check and format check, plus the web typecheck; zero findings.
- `make fmt`: apply ruff fixes and formatting.
- `make run`: local app on :8000 with DynamoDB Local and the fake model (`ENV=local`), seeded. `make stop` stops it.
- `make seed`: create the local table and load the synthetic fixtures (DynamoDB Local only). The AWS seed is Deb's (contract §14.1).
- `make build`: the `linux/arm64` image `homekeep:local`.
- `make audit`: pip-audit on the lock plus `npm audit`.
- `make e2e`: Playwright text-path tests against `make run`. Stub until Slice 4 (exits 2).
- `make eval`: **Deb only.** The real-Bedrock evaluation set. Stub until Slice 4 (exits 2).

## Verifying your work

Run `make lint` and `make test` before reporting any task complete, and paste the summary lines. If a test fails, **fix the code, not the test**. Never skip, weaken or delete a failing test. For a bug, write the failing test first, confirm it fails for the expected reason, then fix it. A slice is done only when its plan's Proof section passes and the verifier reports PASS.

## Stack (pinned — ask before changing)

- Python 3.12; `uv` with the lock committed; FastAPI + Uvicorn (**exactly 1 worker**, async); Pydantic v2; boto3; PyJWT[crypto]
- `mcp==1.29.1`: FastMCP, `stateless_http=True`, `json_response=True`, protocol **2025-11-25**. Not mcp 2.x, which targets spec 2026-07-28 and is not hackathon-confirmed.
- `strands-agents`: `BedrockModel` (Converse) plus `MCPClient` over `streamablehttp_client` with `tool_filters`. Model `us.anthropic.claude-haiku-4-5-20251001-v1:0`, us-east-1, both configurable.
- Web: TypeScript + Vite, no UI framework; Web Speech API (`en-IN`); `oidc-client-ts`
- Tests: pytest, moto, MCP-client contract tests, Playwright + axe-core, a scripted fake model
- Container: multi-stage Dockerfile, **linux/arm64**; docker compose with DynamoDB Local

## Non-negotiable invariants

1. **Tenant scope comes only from the token → membership lookup.** No tool or API takes a household ID.
2. **The LLM never approves or executes.** `confirm_action`, `execute_action` and `cancel_pending_action` are trusted-only: excluded from the agent's `tool_filters`, and rejected without a valid `X-HK-Attest`. The channel's deterministic approval guard decides (TDD §4.3).
3. **No live provider adapter in H.** `SIMULATION_MODE="DEMO"` is a constant; confirmations say "demo" and "No real technician will visit."
4. **Persist before acknowledging.** Use optimistic versions, conditional writes, and one transaction for booking confirmation.
5. **Idempotency.** The browser sends `turn_id`; operation keys are derived server-side; the same key with a different payload returns `RECORD_CONFLICT`.
6. **Outcomes are spoken from server templates**, never model free text. The output guard blocks unbacked confirmations and repair instructions.
7. **Guidance only for a VERIFIED exact model with a PUBLISHED item**; otherwise `NO_APPROVED_GUIDANCE` with a reason. No vector search.
8. **Technician completion never resolves an issue**; only the customer's answer does.
9. **No secrets or real identifiers** in the repo (public). Fictional catalog only ("Frostline FL-18i"). Logs follow the TDD §10.2 allowlist.
10. **Times are stored in UTC and spoken in Asia/Kolkata**, as absolute dates. `CLOCK_OVERRIDE` only when `ENV` is local or test; never in demo.

Project skills apply automatically: `elder-voice-copy` (anything the elder hears) and `mcp-tool-contract` (any tool change).

## Things Claude gets wrong

Add an entry the second time the same mistake happens: `- <mistake> → <correct behaviour> (date)`.

- Wrote the implementation before the plan's named tests or the regression test (Slice 0 review fixes; Slice 1 services) → write those tests first, run them and confirm each fails for the expected reason, then write the code (2026-10-16)
