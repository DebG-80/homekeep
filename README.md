# HomeKeep

Voice-first appliance care for elders: report a problem by voice with no invoice or model number, get evidence-backed checks, book a (demo) technician after explicit spoken approval, and close the case only when you confirm it is fixed.

Built for *Build, Ship, Shape: Amazon Developer Hackathon*: the Alexa+ track (self-hosted MCP server, spec 2025-11-25, Streamable HTTP) and the AWS Builder mini challenge.

> **Status:** under active development. Setup and run instructions are added as the code lands.

## Local development

Prerequisites:
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)
- Docker with buildx (Docker Desktop on macOS)
- Node 24 LTS (`.nvmrc`; `nvm use` picks it up)

| Command | What it does |
| --- | --- |
| `make sync` | Installs the Python and web dependencies exactly as locked (`uv.lock`, `web/package-lock.json`) |
| `make lint` | ruff check, ruff format check and the web typecheck |
| `make fmt` | Applies ruff fixes and formatting |
| `make test` | Unit and contract tests (pytest) |
| `make run` | Starts the app on http://localhost:8000 with DynamoDB Local on :8001 (`ENV=local`) and seeds it; try `curl localhost:8000/healthz` |
| `make seed` | Creates the local table and loads the synthetic households and identities into DynamoDB Local (safe to re-run) |
| `make stop` | Stops the local stack |
| `make build` | Builds the `linux/arm64` image `homekeep:local` |
| `make audit` | Known-vulnerability scan of the Python and web dependencies |

`make e2e` and `make eval` arrive in Slice 4. Configuration comes only from environment variables; `.env.example` lists every one with placeholders. Copy it to `.env` for local overrides (its values are empty, so a copy changes nothing until you fill a line in). Real AWS values for `make eval` go in `.env.eval`, never in `.env`. Both files are gitignored; never commit them. Optionally run `pre-commit install` to get the gitleaks and ruff hooks.

## Deploying to AWS

There is no infrastructure-as-code in this release. Provision the AWS resources by following [`docs/infra-contract.md`](docs/infra-contract.md): it lists every resource, setting, IAM policy and environment variable the app expects, plus a verification checklist. Then seed the users and households with `uv run python -m scripts.seed --target aws --env <test|demo>` (contract §14.1). The first run shows the target and writes nothing; re-run with `--yes`. Each new password is printed once.

## Hackathon submission

The Devpost material is drafted in [`docs/submission/`](docs/submission/), with product feedback in [`docs/product-feedback.md`](docs/product-feedback.md) and friction in [`docs/friction-log.md`](docs/friction-log.md).

## Documentation
- Intent: [`intent/homekeep.md`](intent/homekeep.md)
- Business requirements: [`docs/HomeKeep_BRD_v1.0.md`](docs/HomeKeep_BRD_v1.0.md)
- Technical design (hackathon release): [`docs/HomeKeep_TDD_H_v1.0.md`](docs/HomeKeep_TDD_H_v1.0.md)
- Architecture: [`docs/architecture/homekeep_aws_architecture.png`](docs/architecture/homekeep_aws_architecture.png) and [interaction guide](docs/architecture/interactions.md)
- Delivery process: [`docs/SDLC.md`](docs/SDLC.md)

All service-provider bookings in this release are **simulated**; no real technician is dispatched. All data and the "Frostline" appliance catalog are fictional.
