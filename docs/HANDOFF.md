# HomeKeep — handoff from the planning conversation

Written 29 September 2026; updated 4 October 2026 to adopt the AI-native SDLC workflow (`docs/SDLC.md`). This file records what was decided and verified during planning, so a fresh Claude Code session starts with the same context. The BRD and TDD remain the authoritative specs.

## 1 Decisions taken

| # | Decision | Notes |
| --- | --- | --- |
| 1 | Build the **full BRD H scope** (not the reduced scope from the earlier assessment) | If time runs short, apply the TDD §14.2 cut line in order: FR-19 reminders → FR-04 staff upload UI (keep API) → Ops page charts → formal AT-29 load run. Never cut integrity controls, the hazard/output guards, or the MCP path. |
| 2 | Alexa+ track via a **self-hosted MCP server** (spec 2025-11-25, Streamable HTTP), with the browser voice client as the simulated Alexa+ experience on top of it | The agent must call tools only through MCP. That is the "imported and actually called at runtime" rule. |
| 3 | AWS Builder via Bedrock + Strands + DynamoDB + S3 + Cognito + ECS Express Mode | Document each service in the submission's Product Feedback answer (TDD §11.6). |
| 4 | **Public GitHub repo** with an OSI licence (Apache-2.0 recommended) | Add the licence through GitHub's "Add file → Create new file → LICENSE → Choose a licence template" so it is detected and shown in the About panel, as the rules require. |
| 5 | Owner provisions and deploys AWS; Claude Code writes the application | Claude Code never commits, pushes, or creates cloud resources. |
| 6 | Load assumption: **at most 3 concurrent users**; three resettable judge households J1–J3 | One Fargate task, one Uvicorn worker. |
| 7 | Fictional catalog content ("Frostline FL-18i", plus "FL-24x" for conflict tests) written from scratch | Removes manual-rights risk (BRD R09, D01). |
| 8 | Region us-east-1; Claude Haiku 4.5 via the US inference profile | TDD §1.4 (D03). |
| 9 | **No CDK or `infra/`** (14 Oct, P0-1). `docs/infra-contract.md` is the provisioning checklist; Deb provisions by console or CLI. No `make bootstrap/deploy/destroy`; for AT-32 the README points to the contract | Deviates from TDD §4.1, §11.1 and §11.5 steps 2 and 7. Recorded in `plans/slice-0.md`. |
| 10 | **Minimal `web/` skeleton in Slice 0** (14 Oct, P0-2): Vite + TypeScript placeholder page, so the Dockerfile has its final shape and `package-lock.json` exists | Deviates from §6 (web was Slice 4). |
| 11 | **Node 24 LTS** in the container, `.nvmrc` and README (14 Oct, P0-3) | Node 20 has been EOL since 30 Apr 2026. Deviates from TDD §11.5 step 1. |
| 12 | **Task-role additions** (14 Oct, P0-4): `dynamodb:ConditionCheckItem`, prefix-conditioned `s3:ListBucket`, `cognito-idp:AdminDisableUser`; still no wildcard resources | Reasons in `docs/infra-contract.md` §16. Deviates from TDD §11.2. |
| 13 | **Web client config at runtime** (14 Oct, P0-5): `GET /config.json` serves public Cognito config (domain, client ID, scopes) from env vars. Route lands in Slice 4; variable names fixed now | New; the TDD is silent. |
| 14 | **Product feedback covers Amazon/AWS tools plus the MCP tools** (14 Oct, P0-6), 13 sections in `docs/product-feedback.md` | — |
| 15 | **`docs/submission/feature-requests.md` holds requests to Amazon** (14 Oct, P0-7), each cross-linked to a friction-log entry | — |

## 2 Platform facts verified (25–26 Sep 2026; recheck before submission)

- **AWS App Runner is closed to new customers.** Hosting is ECS Express Mode, AWS's recommended successor. Express Mode gives each service an AWS-provided domain with HTTPS; the owner should confirm this in the first deploy, since one third-party guide disagreed.
- **MCP Python SDK:** 1.x (latest 1.29.1, maintenance mode) speaks the handshake-era protocol up to 2025-11-25. 2.x (stable) targets spec **2026-07-28**. The hackathon rules say "2025-11-25 (or a later version, once confirmed)", so pin 1.29.1.
- **Strands Agents** widened its constraint to `mcp>=1.23.0,<2.2` (PR #4151, merged 4 Sep 2026), so 1.29.1 is compatible. Strands supports `tool_filters={"allowed": [...], "rejected": [...]}` on `MCPClient`.
- **Claude Haiku 4.5 on Bedrock:** Converse supported on bedrock-runtime. US profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`; global profile `global.anthropic.claude-haiku-4-5-20251001-v1:0`. Newer Claude models (Opus 4.7+) use the Messages API on bedrock-mantle, not Converse; keep Haiku 4.5 on Converse for Strands.
- **AgentCore Runtime** can host a stateless Streamable HTTP MCP server, but it is excluded for H (TDD §3.3). Keep the MCP module stateless so it could move there later.

## 3 Hackathon rules that affect the code (official rules, rechecked 25 Sep 2026)

- The repo must contain all source, assets and **clear setup and run instructions**; the project must be shown working in a demo video under 3 minutes.
- Alexa+ via MCP: the repo must show the technology **imported and actually called at runtime** (an entry point or loaded MCP config), not only named in the README.
- The project must stay available free for judges until **20 Nov 2026**. Test credentials go in the Devpost testing instructions, never in the repo.
- Friction-log entries earn up to a **10% bonus**. Keep `docs/friction-log.md` from day 1: task, steps, expected vs actual, severity, workaround, suggestion.
- Product Feedback is mandatory for every tool/API/SDK used: what for, what worked, what needs work, onboarding, would you build again.
- **Open Source mini challenge:** a public primary repo alone does *not* qualify. The rule asks for a *new, additional* open-source project or a contribution to an existing public repo, made during the window. A candidate is extracting the provider simulator or the attested-approval MCP pattern as its own licensed package. This is optional; a project can win only one mini-challenge prize.
- No third-party trademarks or copyrighted material without permission, in code, fixtures or video.

## 4 Public-repo consequences for the code

- Never commit `.env` files, AWS account IDs, Cognito pool or client IDs, or judge passwords. Read all of them from environment variables, and ship a `.env.example` with placeholders.
- Seed scripts create judge users with **random temporary passwords printed once to the operator's terminal**, never written to files.
- CI includes gitleaks. Add a pre-commit hook config too.

## 5 First task for Claude Code: infrastructure contract

Before application code, write `docs/infra-contract.md` for the owner to provision against. It should specify:

- DynamoDB table name variable, key schema (PK/SK strings), GSI1 (GSI1PK/GSI1SK, projection ALL), TTL attribute `ttl`, on-demand billing
- S3 bucket: block public access, SSE-S3, TLS-only policy, CORS for presigned POST from the app origin, lifecycle expiry 1 day on `quarantine/`
- Cognito:
  - user pool and managed login domain
  - resource server `homekeep` with scopes `homekeep/api` and `homekeep/mcp`
  - public clients `web` (PKCE, callback and logout URLs) and `mcp-inspector` (PKCE, localhost callback)
  - groups `coordinator`, `technician`, `catalog_reviewer`, `admin`
  - token lifetimes: access 60 min, refresh 1 day
- IAM task-role policy JSON (TDD §11.2)
- Container: port, health check path `/healthz`, CPU/memory, arm64
- Every environment variable, with an example value and whether it is required: `ENV`, `AWS_REGION`, `TABLE_NAME`, `BUCKET_NAME`, `COGNITO_*`, `MODEL_ID`, `APP_BASE_URL`, `ALLOWED_ORIGINS`, `FAULTS_ENABLED`, `CLOCK_OVERRIDE`, and so on

## 6 Build order (slices)

Every slice follows the same routine (`docs/SDLC.md`): branch `slice-N` → **plan mode** → approved `plans/slice-N.md` committed by Deb → implement → `make lint` + `make test` → `verifier` subagent PASS → `reviewer` subagent → Deb commits, PRs and merges.

Each slice ends with passing tests and a short summary for the owner.

| Slice | Content | Key tests |
| --- | --- | --- |
| 0 | `docs/infra-contract.md`; repo scaffold: pyproject, uv lock, ruff (including security rules), Makefile targets from CLAUDE.md, Dockerfile, compose (DynamoDB Local), `.env.example`, `.github/workflows/ci.yml` (ruff, pytest, gitleaks, pip-audit), `.pre-commit-config.yaml` (gitleaks). `.gitignore` and `docs/friction-log.md` already exist; extend, don't replace. | `make lint` and `make test` green on a placeholder test; the container builds |
| 1 | `store/` (keys, conditional and transaction helpers), `security/` (JWT verification with a local test issuer, membership and grants), `domain/` core (household, consent, appliance, issue, observations, events, clock, state maps), seed fixtures | AT-01, AT-02, AT-03, AT-06, AT-07 (domain level); cross-tenant denial |
| 2 | Catalog data (fictional manuals, hazards, intake, generic prompts), guidance eligibility, MCP server with customer tools plus auth/PRM/Origin handling, orchestrator (Strands + fake model for tests), turn pipeline with command/hazard/output guards, session checkpoints | Handshake at 2025-11-25; AT-04, AT-08, AT-09, AT-10, AT-11; attestation rejection |
| 3 | Approval ledger, trusted tools, approval guard, provider simulator with the fault matrix, booking/reschedule/cancel/status, reconciliation sweep, staff API and events, resolution and reopen, history | AT-12 to AT-19, AT-34, AT-35 |
| 4 | Web client (elder voice/text, household/history, staff console, Ops page), documents (presign/finalize/view), grants and revocation, purge/reset/admin CLI, reminders, eval set and runner, load script, `.github/workflows/evals.yml` (AWS via GitHub OIDC; runs on prompt/catalog/guard changes), `.github/workflows/smoke.yml` (daily `/healthz`, MCP handshake, one text turn; opens an issue on failure), voice-test checklist for Deb, README | AT-05, AT-20 to AT-25, AT-29, AT-30, AT-33; Playwright text-path E2E |

## 7 What only the owner can verify

- Real Bedrock behaviour: `make eval`, 40 prompts × 3 runs, zero tolerance on confirmation and repair violations
- Voice acceptance in Chrome with the screen hidden (AT-13 voice parts, AT-22, AT-23), recorded for the video
- ECS Express Mode HTTPS domain, networking cost (no NAT), `/mcp` reachability from MCP Inspector
- Clean-account reproduction from the README (AT-32)

## 8 Prompts to use in Claude Code

**Before the first prompt:**
- Open this folder as the VS Code workspace root.
- Run `git init`, commit the pack as-is ("chore: context pack"), and create branch `slice-0`.
- Switch the Claude panel to **Plan mode**.

**Step 1: plan the slice** (plan mode):

```
Act as: the lead developer for HomeKeep, working strictly from CLAUDE.md, docs/HANDOFF.md, docs/SDLC.md and docs/HomeKeep_TDD_H_v1.0.md.
Request: produce the implementation plan for Slice 0 (HANDOFF.md §6, starting with docs/infra-contract.md per §5) using the template in plans/README.md. Interview me about anything the TDD leaves open.
Terms: do not write code yet; name every file that will change, the order of work, the riskiest step and the tests that prove it; respect the pinned stack and the invariants; flag any conflict with the TDD instead of resolving it silently.
```

**Step 2:** iterate until the plan is right, then say: "Save the approved plan as plans/slice-0.md." Commit that file yourself.

**Step 3: implement** (switch out of plan mode):

```
Implement plans/slice-0.md exactly. When finished, run make lint and make test, paste the summary lines, then use the verifier agent and report its verdict. If you had to deviate from the plan, update plans/slice-0.md and explain why.
```

**Step 4: review**, then commit and open the PR yourself:

```
Use the reviewer agent on this branch and list the findings.
```

For later slices, repeat steps 1–4 with the slice number changed.
