# HomeKeep delivery process: AI-native SDLC, sized for a solo hackathon

Based on Anthropic's *The AI-Native SDLC Playbook* (Claude blog, 21 Aug 2026). Every stage ends with a committed artifact that the next stage reads, and the commit history is the audit trail: who asked for what, what the agent produced, and who approved it.

| Stage | Committed artifact | Who produces it | Gate (who approves) | Status |
| --- | --- | --- | --- | --- |
| 1 Plan | `intent/homekeep.md`; later `intent/<issue>.md` for each live-test finding | Deb with Claude (chat) | Deb commits | Done |
| 2 Design | `docs/HomeKeep_BRD_v1.0.md`, `docs/HomeKeep_TDD_H_v1.0.md`, `docs/architecture/*` | Claude (chat), reviewed by Deb | Deb accepted | Done (read-only in repo) |
| 3 Build | `plans/slice-N.md`, then code + tests in a branch per slice | Claude Code in plan mode, then implementation | Deb commits the plan before code | Per slice |
| 4 Test | `make lint` / `make test` output; verifier report; `make eval` results | Claude Code; `verifier` subagent; Deb for evals and voice | Slice "done" only on verifier PASS | Per slice |
| 5 Deploy | PR with `reviewer` findings; ECS deployment | `reviewer` subagent; Deb deploys | Deb merges (branch protection) and deploys | Per slice |
| 6 Maintain | GitHub issue from the daily smoke check, converted to `intent/<issue>.md` | Scheduled GitHub Action | Deb triages | From first deploy until 20 Nov |

## Controls and where they live

| Control | Kind | Location |
| --- | --- | --- |
| Context a new joiner needs | Memory | `CLAUDE.md` (kept to about a page) |
| Elder-facing wording rules | Skill (advisory) | `.claude/skills/elder-voice-copy/` |
| MCP tool checklist | Skill (advisory) | `.claude/skills/mcp-tool-contract/` |
| No commits, pushes, AWS/CDK/Terraform, `docker push`; no reading `.env`; specs read-only | Permission deny rules (enforced) | `.claude/settings.json` |
| Python formatting after every edit | Hook (enforced) | `.claude/settings.json` PostToolUse |
| Independent check before "done" | Subagent (report only) | `.claude/agents/verifier.md` |
| Review against policy | Subagent (read-only) + policy | `.claude/agents/reviewer.md`, `REVIEW.md` |
| Secrets scanning, dependency audit, lint, tests | CI (Slice 0) | `.github/workflows/ci.yml` |
| Product AI evals (Bedrock) | CI on prompt/catalog/guard changes (Slice 4) | `.github/workflows/evals.yml`, AWS via GitHub OIDC (no stored keys) |
| Daily smoke check: `/healthz`, MCP handshake, one text turn | Scheduled CI (Slice 4) | `.github/workflows/smoke.yml`, opens an issue on failure |
| Cost guardrail | AWS Budgets | Provisioned by Deb |

## Branch and PR routine (per slice)

1. `git checkout -b slice-N`
2. Ask Claude Code, in plan mode, for the slice plan. Iterate, save it to `plans/slice-N.md`, and commit it.
3. Let Claude Code implement. It finishes with `make lint`, `make test` and a verifier PASS.
4. Ask for a review: "Use the reviewer agent on this branch."
5. Resolve findings, then commit, push and open a PR; merge into `main` after reading the review. Turn on branch protection on `main` so only PRs land.

## Deliberately not adopted (and why)

- **Managed or enterprise settings, Claude Security scans, Claude Tag:** these need an organisation admin or Enterprise plan. gitleaks, pip-audit and ruff security rules cover the scanning need.
- **Evals of the Claude Code configuration itself:** low value for one builder over three weeks. The product's own eval set is what protects quality.
- **Automated incident diagnosis tiers:** the daily smoke check plus budget alerts are proportionate to a demo with three users.
- **More than two parallel sessions:** slices depend on each other. Running the web client in a separate worktree once the Slice 3 API is fixed is the only worthwhile parallel stream.

## Two logs, two purposes

- `CLAUDE.md` → "Things Claude gets wrong": lessons about the coding agent.
- `docs/friction-log.md`: friction with Amazon/AWS tools, which earns the hackathon bonus of up to 10%.
