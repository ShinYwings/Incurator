# RELAY - v0.36.1 XC-1 Silent Exception Hardening

## Goal

Eliminate silent internal broad-exception fallbacks in the decomposed command,
MCP, and plugin API packages while preserving public CLI/MCP/plugin error
envelopes and intended best-effort behavior.

## Plan Reference

- The implemented master plan, evidence ledger, and Arena are preserved in Git
  history and removed from the active workspace per the release workflow.

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
- The next read-only XC-1 pass counted 232 backend-wide broad handlers and 12
  syntactically silent handlers outside the v0.36.1 target packages.
- Failure injection confirmed four P0 follow-ups: corrupt sync state generates a
  new device identity; failed conflict archiving is suppressed; failed tombstone
  deletion still returns applied and records propagation; malformed curate.yml
  becomes an unrestricted default retrieval policy.
- `find_workspace_exhibition` has no callers and retains a retired Exhibition
  contract; queue it for the later reachability-driven dead-code sweep rather
  than mixing it into the P0 correctness patch.

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
- [x] Pushed `release/v0.36.1` and opened draft PR #89.
- [x] Both GitHub CI runs passed Backend Tests and Plugin Tests; Version
  Consistency passed on the required run (the duplicate run skipped that job).
- [x] Addressed all five PR #89 review threads: null-safe client cleanup,
  missing-curate race guidance, explicit client-name initialization, direct
  MCP test imports, and recursive policy scanning.
- [x] Completed an independent full-diff review. Added a regression test and
  `UnicodeError` degradation boundary so an unreadable packaged model catalogue
  follows the documented `warnings` contract instead of aborting the MCP call.

## Critical Context / Blockers

- No implementation or validation blocker.
- Full backend: 1225 passed, 6 skipped, 5 xfailed.
- Plugin: 688 passed; TypeScript and production build passed.
- Testbed autosync ran twice with zero imported/updated/deleted rows on both
  passes, so the Knowledge Sync loop regression did not recur.
- Review follow-up focused tests: 6 passed; Ruff and Mypy passed.
- Independent-review focused tests: 21 passed; Ruff, Mypy, and all 688 plugin
  tests passed. The full backend run passed 1,227 tests with only the workspace
  hygiene check failing on a pre-existing root `.pytest_cache`; after moving
  that cache into the repository cache area, all 18 hygiene tests passed.
- v0.36.2 diagnostics reproduced all four queued P0 paths in temporary state;
  no application code was changed before the required plan/branch transition.

## Immediate Next Action

Review and merge PR #89. Then update local `master`, create `release/v0.36.2`,
author the fail-closed sync/policy plan, and stop for approval before changing
the affected control flow.
