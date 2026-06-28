# Active Relay State

**STATUS: XC-1 error-handling slice 1 shipped to PR — awaiting merge.**

**Current branch**: `fix/error-handling-pipeline`

**Last refreshed**: 2026-06-28 by Claude Code.

---

## Goal

Phase C of the System Stability Overhaul: XC-1 broad-`except` narrowing, **slice 1**
(backend data-pipeline core). Classify each broad catch into
{KEEP, NARROW, SURFACE, DELETE} and resolve, surfacing masked failures without
regressing the pipeline's intentional fault-tolerance. Shipped as **v0.27.5**
(Patch) in PR #64.

## Progress Status

- 6 modules, 51 sites: 12 NARROW, 35 KEEP+log/comment, 4 already-compliant,
  0 forced SURFACE (every candidate had a valid fallback or already surfaced —
  red-team "KEEP/NARROW-first" bias).
- Reviewer-flagged `ingest_raw.py:155` resolved as KEEP+log (graceful fallback),
  not SURFACE.
- 14 new tests; full backend pytest **1104 passed** / 6 skipped / 5 xfailed
  (baseline was 1090); ruff/mypy clean; plugin vitest 621 + tsc clean;
  spec-sync at 0.27.5; testbed `wiki status` clean.
- Version 0.27.5 (Patch — spec titles untouched), CHANGELOG added, slice plan
  artifacts removed (preserved in git history).

## Immediate Next Action

- Human: review and merge PR #64.
- After merge, remaining Phase B/C on fresh branches (each its own plan):
  - XC-1 slice 2: error-handling in god-files (`cli.py`, `mcp_server.py`,
    `plugin_api.py` — best done during CM-1) and `model_setup.py`; XC-4 plugin
    timers/`console.*`.
  - S2 god-file decomposition: CM-1 (cli/mcp), DB-2 (db.py), PL-1 (plugin).
