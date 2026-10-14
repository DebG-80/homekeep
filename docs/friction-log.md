# Friction log — Build, Ship, Shape submission

Hackathon judging gives up to a **10% bonus** for useful friction-log entries. Log every time an Amazon or AWS tool, SDK, doc or console slows you down: Bedrock, Strands, Cognito, ECS Express Mode, DynamoDB, S3, MCP/Alexa+ docs, Devpost submission. Write entries while the details are fresh, and keep them factual and reproducible.

Claude Code workflow lessons do **not** go here; they go into CLAUDE.md under "Things Claude gets wrong".

## Entry template

### FL-NN: <short title>
- **Date:** YYYY-MM-DD
- **Tool / service:**
- **Task attempted:**
- **Steps taken:**
  1. …
- **Expected result:**
- **Actual result:** (exact error text, if any)
- **Severity:** Blocker / Major / Minor
- **Workaround used:**
- **Actionable suggestion:**

---

## Entries

### FL-01: AWS App Runner unavailable for new accounts
- **Date:** 2026-09-25
- **Tool / service:** AWS App Runner
- **Task attempted:** Choose a simple managed container host for a small always-on web + MCP service.
- **Steps taken:**
  1. Planned on App Runner as the simplest HTTPS container host.
  2. Checked the documentation and found the service closed to new customers.
- **Expected result:** A new account can create an App Runner service.
- **Actual result:** "AWS App Runner is no longer open to new customers" (App Runner availability change page).
- **Severity:** Major (forced an architecture change)
- **Workaround used:** ECS Express Mode (Fargate + ALB with an AWS-provided HTTPS domain).
- **Actionable suggestion:** Show the availability change prominently on the App Runner console landing page and in the getting-started guides, with a one-click migration path to ECS Express Mode.
