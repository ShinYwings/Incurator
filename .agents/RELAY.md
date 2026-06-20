# Cross-Agent Relay State

## Goal
Ship v0.19.0 — Agent Prompt Architecture & Context Overhaul (roadmap item 2).

## Branch
`release/v0.19.0` from `master`.

## Current State
- **Implementation complete; full local CI green.**
  - Plugin: tsc clean, 495 vitest tests pass.
  - Backend: ruff + mypy clean, 985 passed / 6 skipped / 5 xfailed.
  - Spec sync: all manifests + 4 spec titles at v0.19; `test_spec_sync` green.
  - Testbed smoke: `VAULT_ROOT=testbed wiki status` OK.
- Shipped in this release:
  - `promptRegistry.ts` — shared, surface-aware prompt blocks (sidechat + popover).
  - Popover MCP tool isolation via `streamChat({ toolPolicy: "none" })` +
    `shouldInjectMcpTools` single decision point.
  - Recency anchor (`<critical_invariants>`) appended last on both surfaces;
    fixes long-session `Cmd+Shift+L` context decay.
  - Also: explicit 0.x SemVer version-bump criteria added to AGENTS.md/CLAUDE.md.
- Plan artifacts deleted on release (Step 11); Arena reasoning preserved in Git
  history (commit `docs(plans): v0.19.0 agent prompt overhaul Arena plan`).

## Plan Reference
Deleted on ship — see Git history for the Arena debate + master plan + evidence
ledger.

## Immediate Next Action
Push `release/v0.19.0` and open the PR. Human reviews and merges. After merge,
truncate this file to an IDLE stub.

## Known Validation Gap
The end-to-end LLM attention behavior (F1 recency fix) cannot be deterministically
smoke-tested without a live model; covered at the unit level (prompt-assembly
assertions) per the testbed-blocker policy.
