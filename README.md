# HomeKeep

Voice-first appliance care for elders in Indian households. Report a problem by voice, with no invoice or model number. Get checks backed by the appliance's manual. Book a demo technician visit after an explicit spoken "yes". The case closes only when you confirm the appliance works.

Built for *Build, Ship, Shape: Amazon Developer Hackathon*: the Alexa+ track (a self-hosted MCP server, spec 2025-11-25, Streamable HTTP) and the AWS Builder mini challenge.

> **Demo only.** Every service booking is simulated by the built-in "HomeKeep Demo Service Desk": no real technician is ever dispatched. All households, people and the "Frostline" appliance catalog are fictional.

## How it works

```
Browser (voice or text) ──► FastAPI turn API ──► deterministic guards ──► Strands agent (Bedrock: Claude Haiku 4.5 by default, Amazon Nova Pro on the hosted demo)
                                   │                                         │ MCP client (Streamable HTTP, tool_filters)
                                   │                                         ▼
                                   └──── trusted approval path ──────► HomeKeep MCP server (/mcp) ──► domain ──► DynamoDB
```

- **The MCP server** at `/mcp` is the only way the agent reaches household data. The agent connects to it at runtime through the MCP client in [`app/orchestrator/agent.py`](app/orchestrator/agent.py), which uses `mcp.client.streamable_http`. Any MCP client, such as MCP Inspector, can use the same endpoint with a Cognito token.
- **The model never approves or executes.** It can only *prepare* a booking. HomeKeep reads the details back, and a deterministic approval guard decides whether the elder's spoken "yes" counts. Only then does HomeKeep call the attested `confirm_action` and `execute_action` tools, which the agent cannot see.
- **Outcomes come from server templates.** "Your demo booking is confirmed … No real technician will visit." is only ever said after the simulated provider has recorded it.
- **Guidance only for a verified model** with a published catalog item. Otherwise HomeKeep says it has no checked advice and offers a demo visit.

Design documents: [intent](intent/homekeep.md), [BRD](docs/HomeKeep_BRD_v1.0.md), [technical design](docs/HomeKeep_TDD_H_v1.0.md), [architecture](docs/architecture/interactions.md).

## Run it locally

Prerequisites:
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)
- Docker with buildx (Docker Desktop on macOS)
- Node 24 LTS (`.nvmrc`; `nvm use` picks it up)
- Chrome, for voice

```bash
make sync     # Python and web dependencies, exactly as locked
make run      # the app on http://localhost:8000 with DynamoDB Local, seeded
```

Open http://localhost:8000. Locally there is no Cognito: a sign-in page lists the seeded test identities. It appears only when `ENV=local`.

### A demo walk-through

1. Sign in as **Judge household 1 (owner)**. You start with no appliances and no consent, as a judge would.
2. On **Talk**, press **Start talking** (or Space) and allow the microphone. Use a headset so HomeKeep doesn't hear itself, and select it as Chrome's microphone (**Settings → Privacy and security → Site settings → Microphone**): Chrome keeps its own choice. Speak, then pause; what you said is sent after about a second. Esc is Stop, not send. You can also type.
3. Say "I have an AC in the bedroom", then "It isn't cooling". Judge households start with storage consent already given, as after assisted setup.
4. Ask for a technician. Give a made-up address and phone number when asked (this is public demo data), and pick a time. Listen to the read-back and say "yes". You hear the demo confirmation.
5. Sign in as **Technician (assigned)** in another browser profile. Open the case in the **Service desk** and mark the visit completed.
6. Back as the judge, say "It works now, you can close it". Then open **Household and history** to see who recorded what, and when.
7. **Reset my demo data** on the household page puts the judge household back to the start.

Locally the language model is a scripted fake that only looks up the household. The full conversation needs the real model, which is the AWS deployment, or `make eval` for the evaluation set. The automated E2E suite drives the fake model through a local-only script endpoint.

Voice commands that always work: "stop", "repeat that", "slower". Keys: Space toggles the microphone, Esc stops, R repeats, Enter sends typed text.

### Commands

| Command | What it does |
| --- | --- |
| `make lint` | ruff check, ruff format check and the web typecheck |
| `make fmt` | Applies ruff fixes and formatting |
| `make test` | Unit and contract tests (pytest, moto, the scripted model) |
| `make run` / `make stop` | Starts / stops the local stack (`ENV=local`) |
| `make seed` | Creates the local table and loads the synthetic fixtures (safe to re-run) |
| `make e2e` | Playwright text-path tests and axe checks against `make run`. It restarts DynamoDB Local and reseeds first, and installs Chromium once |
| `make eval` | The 40-prompt evaluation set against real Bedrock, 3 runs each (needs `make run` and AWS credentials; see below) |
| `make build` | Builds the `linux/arm64` image `homekeep:local` |
| `make audit` | Known-vulnerability scan of the Python and web dependencies |

`uv run python -m scripts.load --sessions 3 --turns 34` runs a load smoke test against `make run`: latency percentiles and correlation evidence.

Configuration comes only from environment variables; [`.env.example`](.env.example) lists every one with placeholders. Copy it to `.env` for local overrides. Never commit `.env` or `.env.eval`; both are gitignored. Optionally run `pre-commit install` for the gitleaks and ruff hooks.

### Evaluation (`make eval`)

`make eval` sends each prompt in [`evals/prompts.jsonl`](evals/prompts.jsonl) through the real turn pipeline with Claude Haiku 4.5 on Bedrock. Each run gets a freshly seeded table in DynamoDB Local. The mix is hazards, repair-instruction requests, guessed models, a malicious manual, confirmation-baiting while a booking is pending, failed or timed out, fees, and fridge and TV requests. Any fabricated confirmation, forbidden instruction or unapproved hazard text fails the set (NFR-06). Bedrock credentials come from your AWS profile. `MODEL_ID` and `BEDROCK_REGION` may go in `.env.eval`. The report is written to `evals/report.json`.

### Trying the MCP server directly

With `make run` up, get a token for a seeded identity and talk to `/mcp`:

```bash
TOKEN=$(curl -s -X POST localhost:8000/local/token -H 'Content-Type: application/json' \
  -d '{"identity":"a_owner"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8000/mcp -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

In MCP Inspector, choose Streamable HTTP, URL `http://localhost:8000/mcp`, and paste the token as a Bearer token. The tool list includes the three trusted tools. They refuse every call without HomeKeep's channel attestation.

## Deploy to AWS

There is no infrastructure-as-code in this release.
1. Provision the resources by following [`docs/infra-contract.md`](docs/infra-contract.md). It lists every resource, setting, IAM policy and environment variable, plus a verification checklist.
2. Build and push the arm64 image (`make build`), then deploy it as described in the contract.
3. Seed users and households with `uv run python -m scripts.seed --target aws --env <test|demo>` (contract §14.1). The first run shows the target and writes nothing; re-run with `--yes`. Each new password is printed once, to your terminal only.

### Operator commands (`hk-admin`)

Run these with your own credentials, never the task role. Each one is audited. The AWS target refuses tables whose names don't end in `-test` or `-demo`, and writes nothing without `--yes`, which goes before the command name.

```bash
uv run python -m scripts.hk_admin --target local reset --household judge-1
uv run python -m scripts.hk_admin --target aws --table-name homekeep-demo --user-pool-id <POOL_ID> \
  --region us-east-1 --yes reset --household judge-1
```

| Command | What it does |
| --- | --- |
| `reset` | Restores a judge household to its seed; members stay signed in |
| `purge` | Removes a test household completely and signs its members out |
| `grant` / `revoke` | Changes a helper's grants, or removes their access and signs them out |
| `catalog withdraw` / `restore` | Withdraws a catalog item without a redeploy (its earlier use stays in history), or restores it |
| `fault set` / `clear` | Injects a demo-provider fault for one household (only when `FAULTS_ENABLED`) |

## Privacy

- Speech recognition uses Chrome's Web Speech API, which sends audio to Google's speech service for transcription. HomeKeep receives only the text, and stores no audio.
- Muting the microphone stops recognition, so no audio is captured.
- Addresses and phone numbers are stored only with consent. They are spoken only in the booking read-back, masked in the service desk unless the assigned technician needs them, and never written to logs.

## Hackathon submission

The Devpost material is drafted in [`docs/submission/`](docs/submission/), with product feedback in [`docs/product-feedback.md`](docs/product-feedback.md), friction in [`docs/friction-log.md`](docs/friction-log.md) and the manual voice test in [`docs/voice-test-checklist.md`](docs/voice-test-checklist.md). The delivery process is described in [`docs/SDLC.md`](docs/SDLC.md).

## Licence

Apache-2.0. See [`LICENSE`](LICENSE).
