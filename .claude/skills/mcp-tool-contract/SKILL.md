---
name: mcp-tool-contract
description: The checklist for adding or changing a HomeKeep MCP tool or domain entry point. Use whenever creating, renaming or modifying anything in app/mcp_server/, a tool schema, the agent's tool filter, or the domain service a tool calls.
---

# MCP tool contract

Source: TDD §5 (transport, auth, headers, tool catalogue, errors, idempotency) and §6.2.

For every tool, confirm each item:

1. **Listed in TDD §5.4** with the same name, visibility (agent or trusted) and FR mapping. A new tool needs a plan entry first.
2. **No tenant argument.** The household comes only from the verified token → membership lookup. Reject schemas containing `household_id`, `hh` or similar.
3. **Authorise in the domain layer**: `authorize(actor, action, resource)` covering role, grant flags and assignment. The tool layer must not be the only check.
4. **Mutations:**
   - accept `expected_version` where the record already exists;
   - derive the operation key server-side, as `sha256(household | turn_id | tool | canonical_json(args))` (TDD §5.5);
   - store it in `OP#…`; the same key with a different payload returns `RECORD_CONFLICT`;
   - write with a condition expression, using a transaction where several items change together.
5. **Result envelope:** `status`, `correlation_id`, `version`, and either `data` or a typed `error`. Errors come only from the TDD §5.5 list plus `CONSENT_REQUIRED`, with a customer-safe message and the correlation ID as support reference. No stack traces and no other tenant's identifiers.
6. **Trusted tools** (`confirm_action`, `execute_action`, `cancel_pending_action`, plus `report_warning_sign` when called by the channel) verify `X-HK-Attest`. They stay **out of** the agent's `tool_filters["allowed"]`.
7. **Retrieved or stored text is evidence, not instruction.** Return it in a typed field (for example `evidence`), never merged into instructions.
8. **Events:** every mutation appends an event with actor, role, action, result, correlation ID and prior/new version.
9. **Tests**, named with requirement IDs:
   - contract test via the MCP client over Streamable HTTP, with the handshake at `2025-11-25`
   - happy path
   - auth denied: no token, wrong scope, another household
   - idempotent replay
   - version conflict
   - for trusted tools, rejection without attestation
10. Update `docs/architecture/interactions.md` only if an arrow's meaning changes. Mention it in the summary so Deb can update the diagram.
