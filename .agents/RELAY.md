# Active Relay State

**STATUS: IDLE.**

No active goal. v0.27.7 (System Stability Overhaul Phase C — DB-2 slice 1:
`db.py` → `db/` package with `schema.py` + facade) shipped and merged via PR #66.

## Next candidates (not started)

Remaining S2 god-file decomposition — each on a fresh branch with its own plan
(plan approval before coding):

- **DB-2 slice 2**: carve `db/_entities.py` further — extract `jobs.py` (job
  queue, deferred from slice 1) and per-entity modules (sources, spans,
  knowledge_units, claims, graph, resolution, relations, community, audit, leaf
  entities). Each a small verbatim-move PR re-pinning the D2 frozen oracle. The
  package + facade + snapshot test from slice 1 are the foundation.
- **CM-1**: decompose `cli.py` (7389 LOC) + `mcp_server.py` (3362 LOC) into
  sub-apps / tool modules (also folds in their XC-1 broad-except cleanup).
- **PL-1**: decompose plugin god-files (`chatSidebar.ts` 4828 LOC, etc.);
  replace `any`/`@ts-ignore` with real types.

Shipped in the overhaul chain: G17/G18/G19 (v0.27.3), G17 S3 (v0.27.4),
XC-1 slice 1 (v0.27.5), Robustness Slice 2 (v0.27.6), DB-2 slice 1 (v0.27.7).
