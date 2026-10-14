# plans/

One approved implementation plan per slice or change: `slice-0.md`, `slice-1.md`, …, `fix-<short-name>.md`.

How a plan gets here:

1. Start Claude Code in **plan mode** and point it at the slice in `docs/HANDOFF.md` §6.
2. Claude reads the code and docs without changing anything, and proposes the plan.
3. Challenge the plan: what could break, what is the riskiest step, which options were rejected.
4. Iterate until someone who never saw the conversation could implement the change from the plan alone.
5. Claude saves the approved plan here. Deb commits it **before** implementation starts.
6. If implementation departs from the plan, update this file in the same commit as the code.

Template:

```markdown
# Plan: <slice or change> (from intent/homekeep.md, TDD §<n>)

## Requirements covered
FR-.., NFR-.., AT-..

## Files that change
path — new / modified — purpose

## Order of work
1. …

## Risks
- …

## Proof
Tests that must pass (by name), plus any manual check for Deb.

## Out of scope
- …
```
