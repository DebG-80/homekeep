# Review instructions (HomeKeep)

Used by the `reviewer` subagent and by any Claude review of a branch or PR. Reviews never approve or block on their own; Deb decides.

## Passes

Run three passes and tag each finding with its pass:

1. **Bugs.** Logic errors, broken edge cases, regressions, unhandled provider outcomes (timeout, duplicate, stale event), timezone/date rollover, race conditions on versions or slots.
2. **Security and privacy.**
   - Tenant leakage: any household ID from input; any missing `authorize` call.
   - Approval bypass: the agent able to reach a trusted tool, or a missing attestation check.
   - Prompt injection: retrieved text treated as instructions.
   - Secrets or real identifiers in code, fixtures or logs.
   - Personal data in logs beyond the TDD §10.2 allowlist.
   - Presigned URL scope or expiry.
3. **Compliance.**
   - The diff matches the approved `plans/*.md`; deviations are recorded in the plan.
   - It follows `docs/HomeKeep_TDD_H_v1.0.md` and the CLAUDE.md invariants.
   - The `elder-voice-copy` and `mcp-tool-contract` rules are followed.
   - Tests reference FR/AT IDs and cover the plan's Proof section.

## Severity

- **Critical:** breaks a CLAUDE.md invariant, leaks data across households, enables an unapproved booking, or fabricates a confirmation.
- **Important:** a wrong behaviour against a BRD acceptance criterion, a missing test for a planned proof, or a crash on a defined error path.
- **Nit:** style, naming, small readability points.

## Cap the nits

At most five nits per review; summarise the rest as a count.

## Do not report

- Formatting that ruff already enforces.
- Generated files: `web/dist/`, lock files, `node_modules/`.
- Anything listed as out of scope in the plan.

## Output

1. Findings table: pass, severity, file:line, issue, suggested fix.
2. Plan-conformance summary.
3. Test evidence seen: commands and counts, or "not run".
