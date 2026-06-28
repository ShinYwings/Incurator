# Active Relay State

**STATUS: DB-2 slice 2 shipped to PR #67 — awaiting merge.**

**Current branch**: `fix/db-decomposition-slice2`

**Last refreshed**: 2026-06-29 by Claude Code.

---

## Goal
DB-2 god-file decomposition, slice 2: carve `db/jobs.py` + `db/sources.py` out of
`db/_entities.py` (verbatim, behavior-preserving, zero import cycles). Shipped as
**v0.27.8** in PR #67.

## Progress
- `jobs.py` (job queue) + `sources.py` (sources/layer-status/DAG-edges/pages +
  json_dumps) carved out; facade re-exports; public `db.*` surface unchanged.
- D2 oracle re-pinned (re-hashed __init__/_entities, added jobs/sources +
  re-arm note). No monkeypatch tests needed repointing.
- Full pytest 1121 passed; ruff/mypy clean (102 files); vitest 626 + tsc clean;
  spec-sync at 0.27.8.

## Immediate Next Action
- Human: review and merge PR #67.
- After merge, remaining DB-2 work (fresh branch, own plan): the **graph/
  community/knowledge/claim cluster** and the **leaf entity modules**
  (synthesis/memory_paths/prompt_runs/curation_plans/insights/artifact_deps) —
  these are bidirectionally coupled, so the next slice must relocate the shared
  helper(s) (e.g. `record_artifact_dependency`) to break cycles before carving.
  Then CM-1 (cli/mcp) and PL-1 (plugin) remain as the other S2 god-files.

Overhaul chain: v0.27.3 → v0.27.4 → v0.27.5 → v0.27.6 → v0.27.7 → v0.27.8.
