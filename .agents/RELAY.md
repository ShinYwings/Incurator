# RELAY - v0.36.1 XC-1 Silent Exception Hardening

## Goal

Eliminate silent internal broad-exception fallbacks in the decomposed command,
MCP, and plugin API packages while preserving public CLI/MCP/plugin error
envelopes and intended best-effort behavior.

## Plan Reference

- Master Plan: `.agents/plans/12_xc1_silent_exception_hardening.md`
- Evidence Ledger: `.agents/plans/12_roadmap_evidence.md`
- Arena: `.agents/plans/12_xc1_silent_exception_hardening_arena/`

## Analysis & Reasoning

- Branch: `release/v0.36.1`, created from PR #88 merge commit `b2a26e3`.
- The old diagnosis named monolithic `cli.py`, `mcp_server.py`, and
  `plugin_api.py`; current owners are `commands/`, `mcp/server.py`, and
  `plugin_api/` after CM-1.
- Current broad-handler counts are 67/69/12 respectively. Most catch-and-return
  handlers are intentional transport boundaries; this patch targets only silent
  internal fallbacks and cleanup paths.
- Python's official guidance distinguishes raised runtime errors from suppressed
  best-effort failures: suppressed failures must be logged at an appropriate
  level rather than silently discarded.

## Progress Status

- [x] PR #88 merged; local `master` fast-forwarded to `b2a26e3`.
- [x] Created patch branch `release/v0.36.1` from merged master.
- [x] Recounted current broad handlers and isolated 28 syntactically silent
  `except Exception` handlers across the three target packages.
- [x] Completed official Python exception/logging prior-art review.
- [x] Authored Arena, domain analyses, evidence ledger, and master plan.
- [ ] Await plan approval before docs/tests/application changes.

## Critical Context / Blockers

- No implementation blocker.
- Stop if a proposed narrowing changes a public error envelope, stdio protocol,
  persistence/schema contract, or converts an intended non-fatal fallback into a
  fatal path.

## Immediate Next Action

Review and approve `.agents/plans/12_xc1_silent_exception_hardening.md`; after
approval, implement P1-P5 TDD-first without widening into all broad handlers.
