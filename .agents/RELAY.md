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
- [x] User approved implementation and explicitly prioritized finding/fixing
  actual behavior bugs alongside exception cleanup.
- [x] Added the silent-handler policy test; all 28 findings are resolved.
- [x] Fixed empty-build false success, missing degraded-index warnings, and the
  broken packaged model-catalogue path.
- [x] Hardened command, MCP, and plugin API fallback/cleanup boundaries.
- [x] Synchronized the English/Korean MCP guide and static behavior spec,
  including a pre-existing provider-parameter and runtime-path mismatch.
- [x] Full backend, plugin, static, build, testbed, and autosync gates passed.
- [ ] Push `release/v0.36.1`, open the PR, and verify remote checks.

## Critical Context / Blockers

- No implementation or validation blocker.
- Full backend: 1225 passed, 6 skipped, 5 xfailed.
- Plugin: 688 passed; TypeScript and production build passed.
- Testbed autosync ran twice with zero imported/updated/deleted rows on both
  passes, so the Knowledge Sync loop regression did not recur.

## Immediate Next Action

Commit release metadata and evidence, delete implemented plan artifacts, push
the branch, open the v0.36.1 PR, and verify remote checks.
