# Plan: Slice 0, infrastructure contract, repo scaffold and submission kit skeleton (from intent/homekeep.md; TDD §2, §3.1, §4.1, §5.2, §6, §9.1, §10.2, §11)

## Context

HANDOFF §5 makes `docs/infra-contract.md` the first task: Deb provisions AWS against it, so it has to be exact and complete. HANDOFF §6 Slice 0 then adds the repo scaffold that every later slice depends on: the pinned Python stack, lint, tests, container, local run and CI. At Deb's request this slice also adds the submission kit skeleton (`docs/submission/*` and `docs/product-feedback.md`), so that Devpost material grows alongside the code. That is an addition to HANDOFF §6.

**Schedule flag (not resolved here).** Today is 14 Oct. The TDD §14.2 plan had the spikes and domain core done by 2 Oct. There are 6 days to the internal target (20 Oct) and 9 to the deadline (23 Oct 12:00 PDT). TDD §14.2 estimates full H scope at 38–42 developer-days. Slice 0 is kept deliberately small. Deb should decide soon whether to apply the §14.2 cut line, or a deeper one, before Slice 1.

## Decisions taken in planning (14 Oct 2026, Deb)

| # | Decision | Deviation from |
| --- | --- | --- |
| P0-1 | **No CDK or `infra/`.** `docs/infra-contract.md` is the provisioning checklist; Deb provisions by console or CLI. No `make bootstrap/deploy/destroy`. For AT-32 the README points to the contract. | TDD §4.1 (`infra/`), §11.1, §11.5 steps 2 and 7 |
| P0-2 | **Minimal `web/` skeleton now** (Vite + TS, placeholder page), so the multi-stage Dockerfile has its final shape and `package-lock.json` exists. | HANDOFF §6 (web is Slice 4) |
| P0-3 | **Node 24 LTS** in the container, `.nvmrc` and README (Node 20 has been EOL since 30 Apr 2026). | TDD §11.5 step 1 |
| P0-4 | **Task-role additions:** `dynamodb:ConditionCheckItem`, `s3:ListBucket` (prefix-conditioned), `cognito-idp:AdminDisableUser`. Each is marked in the contract with its reason, and there are still no wildcard resources. | TDD §11.2 |
| P0-5 | **Web client config at runtime:** the server will serve public, non-secret client config (Cognito domain, client ID, scopes) from env vars at `GET /config.json`. The route lands in Slice 4; the variable names are fixed now. | TDD silent (new) |
| P0-6 | **Product feedback covers Amazon/AWS + MCP tools** (13 sections, listed below). | — |
| P0-7 | **`feature-requests.md` = requests to Amazon**, cross-linked to friction-log entries. | — |

These are recorded as new rows in `docs/HANDOFF.md` §1, and in a "Deviations from the TDD" section of the contract. The TDD itself stays read-only.

### Other conflicts or gaps found (flagged, with the proposed handling; approving this plan accepts them)

- **G-1 Makefile targets.** CLAUDE.md "Commands (created in Slice 0)" lists `test`, `lint`, `e2e`, `run`, `eval`. Slice 0 creates `test`, `lint`, `fmt`, `run`, `stop`, `build`, `audit`, `sync` and `help`. `e2e` and `eval` become honest stubs that print "arrives in Slice 4" and exit 2. `seed`, `reset`, `mcp-check` and `load` arrive with their slices.
- **G-2 `make run` in Slice 0** runs the `/healthz`-only app plus DynamoDB Local. The fake model arrives in Slice 2, and local table creation arrives in Slice 1 with `store/`.
- **G-3 `CLOCK_OVERRIDE`.** "Honoured only when `ENV=test`" will be implemented as **fail-fast at startup**: if it is set in any other ENV, the app refuses to start. Silently ignoring it was the alternative, but it hides misconfiguration.
- **G-4 Cognito callback paths are fixed now** (`{APP_BASE_URL}/auth/callback`, logout `{APP_BASE_URL}/`), so Deb can provision before Slice 4. Slice 4 must use these paths.
- **G-5 MCP Inspector callback.** The contract uses Inspector's default local callback (`http://localhost:6274/oauth/callback`). Deb should check it against the Inspector version used, at provisioning time.
- **G-6 Spike S-1 is not recorded as done.** The contract carries the S-1 confirmations as owner checks: Express Mode resource type, AWS-provided HTTPS domain, public subnets with no NAT, ARM64 at 0.5 vCPU.

## Prerequisites (Deb, before implementation)

1. HANDOFF §8: `git init`, commit the pack as-is ("chore: context pack"), then `git checkout -b slice-0`.
2. `brew install uv`. `uv` and Python 3.12 are not on this Mac (it has Python 3.14 and Node 26); uv fetches 3.12 itself.
3. Docker Desktop running (buildx is present).
4. Expect permission prompts for `uv lock`, `uv python install 3.12`, `npm install`, `docker compose` and `docker buildx`. These need network access, and none are in the allow list.

## Requirements covered

- **BR-07** (partial): submission checklist and kit skeleton
- **NFR-10** (partial): pinned versions and lock files, externalised config, documented provisioning
- **NFR-11** (partial): gitleaks, pip-audit, ruff security rules; TLS-only bucket and least-privilege role specified
- **AT-30** (CI part): secrets scan
- **AT-32**: groundwork only
- **Invariants:** 3 (simulation mode not configurable), 9 (no secrets or identifiers in the repo), 10 (`CLOCK_OVERRIDE` guard; ruff `DTZ` forbids naive datetimes)

## Files that change

**Infrastructure contract**
- `docs/infra-contract.md`: new. Sections:
  1. How to use (values go to env vars, Devpost or a password manager; never into the repo).
  2. Naming and tags (`homekeep-{env}`, env ∈ `test`, `demo`).
  3. **DynamoDB:** `TABLE_NAME`; PK/SK strings; GSI1 (`GSI1PK`/`GSI1SK`, projection ALL); TTL `ttl`; on-demand.
  4. **S3:** Block Public Access on; SSE-S3; bucket-owner-enforced; TLS-only policy JSON; CORS JSON (POST from `APP_BASE_URL` only); lifecycle rule expiring `quarantine/` after 1 day (plus aborting incomplete uploads).
  5. **Cognito:** pool with self sign-up off; managed login domain; resource server `homekeep` with scopes `homekeep/api` and `homekeep/mcp`; public clients `web` (code + PKCE; scopes `openid homekeep/api homekeep/mcp`; callbacks per G-4) and `mcp-inspector` (PKCE; scope `homekeep/mcp`; callback per G-5), both with no secret, token revocation on, access 60 min and refresh 1 day; groups `coordinator`, `technician`, `catalog_reviewer`, `admin`; the claims the server verifies (iss, `token_use=access`, `client_id`, scope).
  6. **IAM task-role policy JSON** using `${ACCOUNT_ID}`/`${REGION}`/… placeholders: TDD §11.2 plus the P0-4 additions; Bedrock on the US inference-profile ARN and its foundation-model ARNs in every region the profile routes to (Deb checks the list in the console). The execution role uses the standard ECR-pull and logs policy.
  7. **ECR** repository, image tag = git SHA, scan on push.
  8. **Container/service:** port 8000; health check `GET /healthz` → 200; linux/arm64; 0.5 vCPU / 1 GB; min = max = 1 task; 1 Uvicorn worker; log retention 30 days.
  9. **Environment variable table** (below).
  10. **Deliberately not configuration:** `SIMULATION_MODE` (a code constant), the attestation key (generated per process), household IDs, and any secret.
  11. Bedrock model access for Haiku 4.5.
  12. Budgets: USD 75 per month, alerts at 50/80/100%.
  13. GitHub repo settings: LICENSE detected in the About panel, branch protection, Actions on.
  14. Outputs Deb records, and where each one goes.
  15. Owner verification checklist (S-1, G-5).
  16. Deviations from the TDD (P0-1, P0-3, P0-4, P0-5, G-3).

  Env vars, each with required-in (local/test/demo), an example placeholder, the default and the purpose:
  - `ENV`, `LOG_LEVEL`, `PORT`, `AWS_REGION`, `TABLE_NAME`, `BUCKET_NAME`
  - `DYNAMODB_ENDPOINT_URL`: only when `ENV=local`
  - `COGNITO_USER_POOL_ID`, `COGNITO_DOMAIN`, `COGNITO_WEB_CLIENT_ID`, `COGNITO_MCP_CLIENT_ID`. The issuer and JWKS URLs are derived from these.
  - `MODEL_ID` (default `us.anthropic.claude-haiku-4-5-20251001-v1:0`) and `BEDROCK_REGION` (defaults to `AWS_REGION`)
  - `MODEL_PROVIDER` (`bedrock` | `fake`; `fake` only when ENV is local or test)
  - `APP_BASE_URL`, `ALLOWED_ORIGINS`, `MCP_LOOPBACK_URL` (default `http://127.0.0.1:8000/mcp`)
  - `FAULTS_ENABLED` (default false), `CLOCK_OVERRIDE` (test only, G-3)
  - `DAILY_TURN_CAP` 300, `MAX_TOOL_CYCLES` 12, `TURN_BUDGET_SECONDS` 20
  - `BEDROCK_PRICE_INPUT_PER_MTOK_USD` and `BEDROCK_PRICE_OUTPUT_PER_MTOK_USD`: optional; the Ops page shows "not configured" when they are unset.
- `docs/HANDOFF.md`: modified. Add decision rows 9–15 (P0-1 … P0-7) dated 14 Oct.

**Python scaffold**
- `pyproject.toml`: new.
  - `requires-python ==3.12.*`.
  - Dependencies: `fastapi`, `uvicorn`, `pydantic>=2`, `boto3`, `PyJWT[crypto]`, `mcp==1.29.1`, and `strands-agents` (a range admitting mcp 1.29.x; exact version from the lock).
  - Dev group: `pytest`, `moto[dynamodb,s3,cognitoidp]`, `ruff`, `pip-audit`, `httpx` (needed by FastAPI's TestClient).
  - Ruff: py312, line length 100; select `E,W,F,I,B,UP,S,ASYNC,DTZ,T20,PT,SIM,RUF`; tests ignore `S101`.
  - Pytest: `testpaths=tests`, `--strict-markers -ra`.
- `uv.lock`: new, generated. `.python-version`: new (`3.12`).
- `app/__init__.py`, `app/main.py`: new. A FastAPI app with only `GET /healthz` → `{"status":"ok"}`. It does a liveness check only, with no AWS calls.
- `app/config.py`: new. A Pydantic `Settings` loaded from `os.environ` (no pydantic-settings dependency). It enforces the per-ENV required variables and the G-3, `DYNAMODB_ENDPOINT_URL` and `MODEL_PROVIDER` guards.
- `tests/conftest.py`, `tests/unit/test_healthz.py`, `tests/unit/test_config.py`, `tests/unit/test_env_contract.py`, `tests/unit/test_gitleaks_rules.py`, `tests/unit/test_submission_kit.py`: new (see Proof).

**Web skeleton (P0-2)**
- `web/package.json` (scripts `build` = `tsc --noEmit && vite build`, `typecheck`; devDependencies `typescript` and `vite`; `engines.node` 24), `web/package-lock.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`, `web/src/main.ts` (placeholder page carrying the persistent "DEMO — simulated service desk" badge, TDD §8.6), `.nvmrc` (`24`): all new.

**Container and local run**
- `Dockerfile`: new. Three stages:
  1. `node:24-slim`: `npm ci` and build `web/dist`.
  2. `python:3.12-slim` with a pinned `uv` binary: `uv sync --frozen --no-dev`.
  3. Runtime on `python:3.12-slim`: non-root UID 10001; copies the venv, `app/` and `web/dist`; `EXPOSE 8000`; a `HEALTHCHECK` using Python urllib; `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers`.

  The image is built for `--platform linux/arm64`.
- `.dockerignore`: new.
- `compose.yaml`: new.
  - `app`: built locally; `ENV=local`; `DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000`; dummy local AWS credentials; optional `.env`; port 8000.
  - `dynamodb-local`: pinned `amazon/dynamodb-local` tag, in-memory, host port 8001.
- `Makefile`: new, with the targets in G-1.
  - `build` = `docker buildx build --platform linux/arm64 --load -t homekeep:local .`
  - `audit` = `pip-audit` on `uv export` output, plus `npm audit --audit-level=high`.
  - `lint` = `ruff check`, `ruff format --check`, plus a web typecheck.
- `.env.example`: new. Every contract variable with a `<PLACEHOLDER>` value, grouped by environment.

**CI and secrets**
- `.github/workflows/ci.yml`: new. Runs on push and pull_request with `permissions: contents: read`. Jobs:
  1. `lint` (uv + ruff + web typecheck)
  2. `test` (pytest + web build)
  3. `audit` (pip-audit + npm audit)
  4. `gitleaks` (`gitleaks/gitleaks-action@v2`, full history)

  Actions are pinned to release tags, and SHA pinning is noted as optional for Deb.
- `.pre-commit-config.yaml`: new. A gitleaks hook, plus ruff check and ruff format. Revs are pinned to the versions verified during implementation.
- `.gitleaks.toml`: new. It extends the default rules and adds two: Cognito user-pool IDs (`<region>_<9 alnum>`) and 12-digit account IDs inside ARNs. Placeholders use `<…>`/`${…}` forms, so no allowlist hacks are needed.
- `.gitignore`: modified, extended rather than replaced. Add `.env.*` with `!.env.example`, `dist/`, `*.egg-info/` and `.uv-cache/`.

**Docs**
- `README.md`: modified. Add a "Local development" section (prerequisites uv, Docker and Node 24; `make sync/lint/test/run/build/audit`), plus links to the contract and `docs/submission/`. The status line stays.
- `CLAUDE.md`: modified. In the Commands section only: add `fmt`, `build`, `audit`, `stop`, and note that `e2e`/`eval` are stubs until Slice 4.

**Submission kit skeleton**

Each file contains headings, guidance on what goes there, the facts already known (from the TDD, BRD and HANDOFF), and `TODO(Deb)` or `TODO(slice-N)` markers for anything that does not exist yet. Nothing is claimed as working. Spoken HomeKeep lines are quoted only from server templates, under the `elder-voice-copy` rules.
- `docs/submission/description.md`: Devpost story sections: Inspiration, What it does, How we built it, Challenges, Accomplishments, What we learned, What's next. It carries the demo disclosure and the fictional-brand note.
- `docs/submission/built-with.md`: Devpost tags, plus a table mapping each technology to its code path (TDD §11.6, pinned stack).
- `docs/submission/testing-instructions.md`: a template. Its header reads: **"Credentials are entered only in the Devpost field. Never paste them here."** It covers the hosted URL placeholder, Chrome desktop with en-IN and the microphone, the voice and text paths, MCP Inspector steps (PRM discovery, the `mcp-inspector` client, an expected trusted-tool refusal), "Reset my demo data", known limits, and availability until 20 Nov.
- `docs/submission/feature-requests.md`: requests to Amazon, each with tool, request, HomeKeep context and an `FL-NN` link. Seeded with candidates to confirm: App Runner → Express Mode guidance (FL-01), Cognito dynamic client registration for MCP clients (TDD §5.2), and Alexa+ confirmation of the MCP spec version (TR-03).
- `docs/submission/video-script.md`: a timed beats table under 3:00 (time, screen, narration, rule or AT proved). Beats: problem; voice journey (AT-22); hazard; read-back → "yes" → demo booking; technician completion → customer confirmation (AT-19); MCP Inspector handshake `2025-11-25` + trusted-tool refusal; architecture. Constraints: no copyrighted music, no real brands or people, captions on.
- `docs/submission/checklist.md`: owner checklist covering:
  - eligibility rows (TDD §2)
  - repo rules: public, LICENSE detected, run instructions, gitleaks green
  - runtime MCP hook evidence
  - video and Devpost fields
  - friction log pasted
  - live until 20 Nov, with budget and uptime checks
  - key dates: credits form 21 Oct 12:00 PT; internal target 20 Oct; deadline 23 Oct 12:00 PDT
  - a recheck of the rules page [S01]
  - the optional Open Source mini-challenge decision
- `docs/product-feedback.md`: new, one section per tool:
  - Amazon Bedrock
  - Strands Agents SDK
  - DynamoDB (incl. DynamoDB Local)
  - S3
  - Cognito
  - ECS Express Mode (Fargate + ALB)
  - ECR
  - IAM
  - CloudWatch Logs
  - AWS Budgets
  - Alexa+ (MCP integration docs)
  - MCP Python SDK
  - MCP Inspector

  Each section has "Integration point in code" pre-filled, plus the five questions: *What did you use it for?* (pre-filled from TDD §11.6), *What worked well?*, *What needs improvement?*, *How was onboarding?*, *Would you build with it again?* There are links to FL entries.

## Order of work

1. `docs/infra-contract.md`, then the HANDOFF decision rows. Contract first, per HANDOFF §5, so Deb can start provisioning in parallel.
2. **`pyproject.toml`, `.python-version`, `uv lock`, `uv sync` (riskiest).** If `mcp==1.29.1` and `strands-agents` do not co-resolve on 3.12, or pip-audit reports a vulnerability in a pinned package: **stop and report, without changing any pin.** Log an FL entry if the cause is Amazon tooling (Strands).
3. `app/main.py`, `app/config.py` and the unit tests; ruff config. Get `make lint` and `make test` green.
4. Write `.env.example` from the contract table, then add `test_env_contract.py`.
5. Web skeleton: `npm install` (generates the lock), then `npm run build`.
6. `Dockerfile`, `.dockerignore`, `compose.yaml`, `Makefile`. Then `make build`, check the arch, `make run`, `curl /healthz`, `make stop`.
7. `.gitleaks.toml` with its rule test, `.pre-commit-config.yaml`, `ci.yml`. Run `make audit` locally.
8. `.gitignore`, README and CLAUDE.md edits.
9. Submission kit and `product-feedback.md`, plus `test_submission_kit.py`.
10. Final `make lint` and `make test` (paste the summary lines), then the `verifier` subagent, then the `reviewer` subagent. Report to Deb.

## Risks

- **Dependency resolution (step 2), the riskiest step.** `mcp==1.29.1` is a maintenance line; Strands only admits it from releases after PR #4151 (4 Sep 2026); a transitive pin or a pip-audit finding could invalidate the pinned stack. Mitigation: do this right after the contract, and stop and ask rather than change pins. Proof: `uv lock` succeeds, `uv run python -c "import mcp, strands"` works, and `make audit` is clean.
- **ARM64 image.** Native on Apple silicon, so low risk. Proof: `docker image inspect` shows `arm64`.
- **Contract errors cost Deb time.** A wrong IAM ARN or callback URL surfaces only when deployed. Mitigation: placeholders are explicit, the S-1, G-5 and Bedrock region checks are listed as owner checks, and the deviations are named.
- **gitleaks-action** needs a licence only for organisation-owned repos. If the repo is under an org, switch the job to the gitleaks binary.
- **Slice 4 coupling.** G-4 and P0-5 fix the callback paths and config variable names now, and Slice 4 must honour them.
- **Schedule** (see Context).

## Proof

`make test` must pass with these tests:
- `tests/unit/test_healthz.py::test_healthz_returns_ok_without_aws_calls`
- `tests/unit/test_config.py::test_inv10_clock_override_rejected_outside_test_env`
- `tests/unit/test_config.py::test_inv10_clock_override_accepted_in_test_env`
- `tests/unit/test_config.py::test_dynamodb_endpoint_only_in_local_env`
- `tests/unit/test_config.py::test_fake_model_rejected_in_demo_env`
- `tests/unit/test_config.py::test_nfr10_demo_env_requires_table_cognito_and_origin_vars`
- `tests/unit/test_config.py::test_inv3_simulation_mode_is_not_an_env_setting`
- `tests/unit/test_env_contract.py::test_nfr10_env_example_matches_contract_and_settings`: the variable set in `.env.example` equals the contract table equals the `Settings` fields.
- `tests/unit/test_gitleaks_rules.py::test_inv9_custom_rules_catch_pool_ids_and_account_arns`
- `tests/unit/test_gitleaks_rules.py::test_inv9_placeholders_are_not_flagged`
- `tests/unit/test_submission_kit.py::test_br07_submission_kit_files_present`
- `tests/unit/test_submission_kit.py::test_br07_product_feedback_has_five_questions_per_tool`
- `tests/unit/test_submission_kit.py::test_inv9_testing_instructions_hold_no_credentials`: placeholders only, with no value after password, username or email labels.

`make lint` must report zero findings, including the web typecheck.

Container checks:
- `make build` succeeds.
- `docker image inspect homekeep:local --format '{{.Architecture}}'` prints `arm64`.
- `docker run --rm homekeep:local id -u` is not 0.
- `make run`, then `curl -fsS localhost:8000/healthz` returns `{"status":"ok"}`.
- `make stop`.

Audit: `make audit` reports no known vulnerabilities. Anything it does report goes to Deb, and nothing is suppressed.

Verifier: PASS.

Manual checks for Deb (not gates for this slice):
- push `slice-0` and see all four CI jobs green
- provision against the contract and tick its §15 checklist
- confirm the LICENSE shows in the GitHub About panel

## Out of scope

- Any application behaviour beyond `/healthz` and config loading: `store/`, `security/` and `domain/` (Slice 1); MCP, orchestrator and the fake model (Slice 2); the `/config.json` route (Slice 4).
- Local DynamoDB table creation (Slice 1), and seed, reset, mcp-check, load, e2e and eval implementations.
- CDK, Terraform, creating any AWS resource, `docker push`, git commits or pushes.
- `evals.yml`, `smoke.yml` and the GitHub OIDC role (Slice 4).
- Writing final submission answers, recording the video, filling in product feedback (Deb, near submission).
- Docker image build in CI. The four named jobs only; Deb can add it later.
