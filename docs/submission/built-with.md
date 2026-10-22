# Built with (draft)

## Devpost tags

`python`, `fastapi`, `pydantic`, `amazon-bedrock`, `claude`, `strands-agents`, `model-context-protocol`, `alexa`, `amazon-dynamodb`, `amazon-cognito`, `amazon-ecs`, `aws-fargate`, `amazon-ecr`, `amazon-cloudwatch`, `aws-budgets`, `typescript`, `vite`, `web-speech-api`, `docker`, `github-actions`

TODO(Deb): trim to the tags Devpost offers; add any that only exist as free text.

## Technology → code path

"Status" tracks what exists in the repository today. Update it as slices merge, and before submission make sure no row says "planned".

| Technology | Version (pinned) | Used for | Code path | Status |
| --- | --- | --- | --- | --- |
| Python | 3.12 | Application language | `app/`, `.python-version` | In place (Slice 0) |
| uv | 0.13.1 | Dependency lock and environment | `pyproject.toml`, `uv.lock` | In place (Slice 0) |
| FastAPI + Uvicorn | from `uv.lock`; 1 worker | HTTP app, `/healthz`, API routes | `app/main.py` | Built (Slices 0–4) |
| Pydantic v2 | from `uv.lock` | Settings and schemas | `app/config.py` | In place (Slice 0) |
| MCP Python SDK | `mcp==1.29.1`, protocol 2025-11-25 | Self-hosted MCP server and the agent's MCP client | `app/mcp_server/`, `app/orchestrator/agent.py` | Built (Slice 2) |
| Strands Agents SDK | from `uv.lock` (≥ 1.55) | Agent loop, `MCPClient` with `tool_filters` | `app/orchestrator/` | Built (Slice 2) |
| Amazon Bedrock, Claude Haiku 4.5 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Converse API with tool use | `app/orchestrator/` | Built (Slice 2); real runs via `make eval` |
| Amazon DynamoDB (+ DynamoDB Local) | on-demand; local image 3.3.1 | All records; conditional writes, transactions, TTL, GSI | `app/store/`, `compose.yaml` | Built (Slices 1–4) |
| Amazon S3 | — | Document uploads: presigned POST, quarantine, validation (designed in TDD §4.8) | — | Not in this release (documents deferred, P1-1) |
| Amazon Cognito | — | PKCE sign-in, resource-server scopes, JWT verification for API and MCP | `app/security/` | Built (Slices 1–4): JWT verification; browser sign-in with PKCE |
| Amazon ECS Express Mode (Fargate + ALB) | ARM64, 0.5 vCPU / 1 GB | Hosting with an AWS-provided HTTPS domain | `Dockerfile`, `docs/infra-contract.md` §8 | Image in place; deploy by Deb |
| Amazon ECR | — | Image registry | `Makefile` (`build`), `docs/infra-contract.md` §7 | Contract in place |
| AWS IAM | — | Least-privilege task role | `docs/infra-contract.md` §6 | Contract in place |
| Amazon CloudWatch Logs | 30-day retention | Redacted structured logs | `app/logging.py`, `docs/infra-contract.md` §8 | Built: allowlisted JSON logs (`app/logging.py`) |
| AWS Budgets | USD 75 / month | Cost alerts | `docs/infra-contract.md` §12 | Contract in place |
| TypeScript + Vite | from `web/package-lock.json`; Node 24 | Browser client | `web/` | Built (Slice 4) |
| Web Speech API | Chrome, `en-IN` | Speech recognition and synthesis | `web/src/` | Built (Slice 4) |
| Docker (buildx) | multi-stage, `linux/arm64` | Container image | `Dockerfile`, `compose.yaml` | In place (Slice 0) |
| GitHub Actions | — | Lint, test, audit, gitleaks | `.github/workflows/ci.yml` | In place (Slice 0) |
| pytest, moto, ruff, pip-audit, gitleaks | from `uv.lock`; gitleaks 8.30.1 | Tests and security checks | `tests/`, `.gitleaks.toml`, `.pre-commit-config.yaml` | In place (Slice 0) |
| Playwright + axe-core | — | Text-path end-to-end and accessibility tests | `web/e2e/` | Built (Slice 4) |
