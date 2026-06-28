# Active Relay State

**STATUS: IDLE.**

No active goal. v0.27.8 (DB-2 slice 2: `jobs.py` + `sources.py` carved out of
`db/_entities.py`) shipped and merged via PR #67. Each overhaul release is a
complete, deployable build (DB-2 is a behavior-preserving internal refactor).

## Next candidates (not started)

Remaining S2 god-file decomposition — each on a fresh branch with its own plan:

- **DB-2 slice 3+**: carve the remaining `db/_entities.py` — the graph/community/
  knowledge/claim cluster + leaf entity modules (synthesis/memory_paths/
  prompt_runs/curation_plans/insights/artifact_deps). These are bidirectionally
  coupled, so the next slice must first relocate the shared helper(s) (e.g.
  `record_artifact_dependency`) to break import cycles before carving.
- **CM-1**: decompose `cli.py` (7389) + `mcp_server.py` (3362).
- **PL-1**: decompose plugin god-files (`chatSidebar.ts` 4828, etc.).

Overhaul chain (all deployable): v0.27.3 → v0.27.4 → v0.27.5 → v0.27.6 →
v0.27.7 → v0.27.8.
