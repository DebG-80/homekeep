# Product feedback (draft)

The hackathon requires Product Feedback for every tool, API and SDK used: what it was used for, what worked, what needs work, how onboarding went, and whether we would build with it again. This file covers the Amazon/AWS services plus the MCP tools (HANDOFF §1, decision 14).

"What did you use it for?" and "Integration point in code" are pre-filled from TDD §11.6 and the infrastructure contract. Deb answers the other four questions near submission, from real experience. Link friction-log entries (`docs/friction-log.md`) wherever they apply.

## Amazon Bedrock

- **Integration point in code:** `app/orchestrator/` (planned, Slice 2); IAM in `docs/infra-contract.md` §6.1 and §11
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

Claude Haiku 4.5 through the Converse API with tool use, via the US inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`. It interprets the elder's words, chooses tools and drafts short replies; it never approves or executes an action.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Strands Agents SDK

- **Integration point in code:** `app/orchestrator/agent.py` (planned, Slice 2)
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

The agent loop: `BedrockModel` plus an `MCPClient` over Streamable HTTP with `tool_filters`, so the agent can reach only the customer tools. A fresh client per turn carries that turn's headers.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Amazon DynamoDB (including DynamoDB Local)

- **Integration point in code:** `app/store/` (planned, Slice 1); `compose.yaml` (DynamoDB Local 3.3.1)
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

One on-demand table for every record: optimistic versions with conditional writes, one transaction for booking confirmation, TTL for sessions and approvals, and one overloaded GSI for the staff queue and the reconciliation sweep. DynamoDB Local runs the same code on a laptop.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Amazon Cognito

- **Integration point in code:** `app/security/` (planned, Slice 1); pool in `docs/infra-contract.md` §5
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

Managed login with authorization code + PKCE for public clients, a resource server with `homekeep/api` and `homekeep/mcp` scopes, access-token verification against JWKS for the API and the MCP server, and global sign-out on revocation.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Amazon ECS Express Mode (Fargate + ALB)

- **Integration point in code:** `Dockerfile`; `docs/infra-contract.md` §6.3 and §8
- **Friction-log entries:** [FL-01](friction-log.md#fl-01-aws-app-runner-unavailable-for-new-accounts) (App Runner closed; moved to Express Mode)

**What did you use it for?**

Hosting for the single ARM64 container (0.5 vCPU / 1 GB, one task) with an AWS-provided HTTPS domain, so the browser can use the microphone and the MCP endpoint is reachable.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Amazon ECR

- **Integration point in code:** `Makefile` (`build`); `docs/infra-contract.md` §7
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

Registry for the `linux/arm64` image, tagged with the git commit SHA, with scan on push.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## AWS IAM

- **Integration point in code:** `docs/infra-contract.md` §6
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

A least-privilege task role with no wildcard resources (DynamoDB table and index, the Bedrock profile and its model ARNs, two Cognito admin actions), plus the execution and Express Mode infrastructure roles.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Amazon CloudWatch Logs

- **Integration point in code:** `docs/infra-contract.md` §8; structured logging code (planned, Slice 2)
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

Redacted structured JSON logs with an allowlist of fields (correlation ID, hashed actor, action, result, error code, latency, token counts), kept for 30 days.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## AWS Budgets

- **Integration point in code:** `docs/infra-contract.md` §12
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

A USD 75 monthly budget with alerts at 50%, 80% and 100%, to keep the demo live through 20 November within the credits.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## Alexa+ (MCP integration docs)

- **Integration point in code:** `app/mcp_server/` (planned, Slice 2)
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

Guidance for the Alexa+ track: a self-hosted MCP server on spec 2025-11-25 over Streamable HTTP. HomeKeep's browser voice client stands in for Alexa+ on top of that server in H.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## MCP Python SDK

- **Integration point in code:** `app/mcp_server/` and `app/orchestrator/agent.py` (planned, Slice 2); pinned `mcp==1.29.1` in `pyproject.toml`
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

FastMCP in stateless mode with JSON responses for the server, and the Streamable HTTP client that HomeKeep's agent uses to call its own tools at runtime.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).

## MCP Inspector

- **Integration point in code:** Manual testing; steps in `docs/submission/testing-instructions.md`
- **Friction-log entries:** TODO(Deb): link FL-NN entries, or write "none".

**What did you use it for?**

Checking the hosted `/mcp` endpoint from outside: OAuth discovery through Protected Resource Metadata, the `2025-11-25` handshake, the tool list, and the refusal of trusted tools.

**What worked well?**

TODO(Deb).

**What needs improvement?**

TODO(Deb).

**How was onboarding?**

TODO(Deb).

**Would you build with it again?**

TODO(Deb).
