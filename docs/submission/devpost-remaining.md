# Devpost: what is left after "Project Story"

For Deb, 23 Oct 2026. Deadline **12:00 PDT = 00:30 IST (24 Oct)**. Devpost keeps a draft and lets you edit until the deadline, so save after each section and submit early, then refine.

Real values (URLs, logins, passwords) go **only** into the Devpost form, never into this repository.

## 0 Fix one line in the story you already pasted

The app now runs on **Amazon Nova Pro**, not Claude Haiku 4.5. In your Project Story, find the "Conversation" bullet and replace it with:

> **Conversation:** the Strands Agents SDK on Amazon Bedrock (Converse API with tool use), running Amazon Nova Pro. The model is one environment variable; the app was designed for Claude Haiku 4.5, which needs an AWS Marketplace subscription that our account could not complete before the deadline. The agent sees only customer tools.

If "Challenges we ran into" is still open, today's AWS work is the honest answer: Cognito's wizard forcing email or phone for username sign-in; managed login showing "Login pages unavailable" until a style exists; Bedrock's first-use chain (use-case form, then a Marketplace subscription that our role could not create, then `INVALID_PAYMENT_INSTRUMENT` until the payment currency was set); switching to Nova and hardening the server for it (stripping `<thinking>` text, carrying state between turns).

## 1 Built with

Paste these tags (drop any Devpost doesn't offer; it accepts free text too):

`python`, `fastapi`, `pydantic`, `amazon-bedrock`, `amazon-nova`, `strands-agents`, `model-context-protocol`, `alexa`, `amazon-dynamodb`, `amazon-cognito`, `amazon-ecs`, `aws-fargate`, `amazon-ecr`, `amazon-cloudwatch`, `aws-iam`, `aws-budgets`, `typescript`, `vite`, `web-speech-api`, `docker`, `github-actions`

Not `claude` and not `amazon-s3`: neither is used by the running app.

## 2 "Try it out" links

| Link | Value |
| --- | --- |
| Source code | `https://github.com/DebG-80/homekeep` (create and push it first: section 8) |
| Live app | `<APP_URL>` (the `…ecs.us-east-1.on.aws` address) |

## 3 Video demo link

Required. Under 3 minutes, YouTube (unlisted is fine) or Vimeo. Script: `docs/submission/video-script.md`. Record it after the final deploy works end to end; record the typed path if voice is unreliable on the day, and say so. Crop out your address, phone and account ID. No copyrighted music.

## 4 Image gallery (optional, recommended)

- `docs/architecture/homekeep_aws_architecture.png` (the diagram; shows what is and isn't in this release).
- Two or three screenshots: the Talk page mid-booking, the read-back with "This is a demonstration. No real technician will visit.", the staff console. Crop personal details.

## 5 Additional questions (names vary; match by meaning)

| Devpost asks | What to paste or choose |
| --- | --- |
| Track / category | **Alexa+** (self-hosted MCP server). Also tick **AWS Builder** if it's a separate option |
| MCP server URL or endpoint | `<APP_URL>/mcp` |
| How judges test it / testing instructions | `docs/submission/testing-instructions.md`, with the placeholders replaced **only in this field**: the app URL, the MCP URL, `hk-judge-1`, `hk-judge-2`, `hk-judge-3` and their passwords, and `hk-tech-1` / `hk-coordinator` for the staff part. Tell judges to use one judge login each, and that **Reset my demo data** restores a clean household |
| AWS services used | Amazon Bedrock (Nova Pro), Amazon ECS Express Mode on Fargate (ARM64), Amazon ECR, Amazon DynamoDB, Amazon Cognito, AWS IAM, Amazon CloudWatch Logs, AWS Budgets |
| Product feedback | `docs/product-feedback.md`: one section per tool, five questions each. It still has `TODO(Deb)` slots; answer the ones you can from today, and ask Claude to draft the rest from this session for you to edit |
| Friction log | `docs/friction-log.md` plus today's entries (see section 0): each with what you tried, what happened, what you expected, and the fix. Up to 10% bonus |
| Feature requests (if asked) | `docs/submission/feature-requests.md` |
| Repository licence | Apache-2.0 (`LICENSE`), shown in GitHub's About panel |
| Open Source mini challenge | No (decided) |

## 6 Before you press Submit

- [ ] The live app answers: sign in as a judge, "Hi", then one appliance problem.
- [ ] Judges J1–J3 reset to a clean state: `uv run python -m scripts.hk_admin --target aws --table-name homekeep-demo --user-pool-id <POOL_ID> --region us-east-1 --yes reset --household judge-1` (and 2, 3).
- [ ] Only one ECS task running (two tasks break approvals).
- [ ] Budget: **AWS Budgets → Create budget**, monthly cost USD 75, email alerts at 50%, 80% and 100% (infra-contract §12).
- [ ] The video link plays in a private window.
- [ ] The repository is public and CI ran (Actions tab).

## 7 After submitting (until 20 Nov)

- Keep the service running; don't change `MODEL_ID` or the image without testing first.
- A free uptime check on `<APP_URL>/healthz` every 5 minutes (any free monitor).
- Calendar reminder for 21 Nov: tear down ECS, ECR, DynamoDB, Cognito, the log group and the IAM roles.

## 8 GitHub (if not done)

1. github.com → **New repository** → `homekeep`, **Public**, no README, `.gitignore` or licence.
2. `git remote add origin https://github.com/DebG-80/homekeep.git && git push -u origin main`
3. Check: About panel shows Apache-2.0; **Actions** runs lint, test, audit and gitleaks.
