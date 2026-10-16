# Feature requests to Amazon (draft)

Requests to Amazon and AWS teams that came out of building HomeKeep. Each one links to the friction-log entry that shows the problem (`docs/friction-log.md`). Only submit a request whose friction is logged and reproducible.

Status values: **Candidate** (not yet confirmed or logged), **Ready** (logged and reproducible), **Submitted**.

| # | Tool | Request | HomeKeep context | Friction log | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | AWS App Runner → Amazon ECS Express Mode | Show App Runner's closure to new customers on the console landing page and in the getting-started guides, with a guided migration to ECS Express Mode | We planned App Runner as the simplest HTTPS container host and found it closed only after reading the availability page; we moved to ECS Express Mode | [FL-01](../friction-log.md#fl-01-aws-app-runner-unavailable-for-new-accounts) | Ready |
| 2 | Amazon Cognito | Support OAuth Dynamic Client Registration (RFC 7591), or a documented pattern for MCP clients, so MCP clients can register without a pre-created app client | Our MCP server is an OAuth resource server backed by Cognito. External MCP clients have to use a pre-registered public client (`mcp-inspector`) instead (TDD §5.2) | TODO(Deb): log as FL-NN when confirmed while connecting MCP Inspector | Candidate |
| 3 | Alexa+ (MCP integration) | Publish which MCP specification versions Alexa+ accepts (2025-11-25 and/or 2026-07-28) and when later versions will be confirmed | We pinned MCP SDK 1.29.1 for spec 2025-11-25 because 2.x targets 2026-07-28, which the rules do not yet confirm (TDD TR-03) | TODO(Deb): log as FL-NN if the docs remain unclear | Candidate |

TODO(Deb): add requests as friction-log entries accumulate; keep the FL link on every row.
