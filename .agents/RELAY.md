# Active Relay State

**STATUS: Planning — DB-2 slice 2 plan drafted, AWAITING USER APPROVAL. No code yet.**

**Current branch**: `master` (feature branch created only after approval)

Prior: v0.27.7 (DB-2 slice 1: `db.py` → `db/` package + `schema.py` + facade)
shipped and merged via PR #66.

## DB-2 slice 2 plan (DRAFT — needs approval)
- Carve `db/_entities.py` (3457 LOC) → extract `db/jobs.py` (job queue, deferred
  from slice 1) + `db/sources.py` (sources/layer-status/DAG-edges/source-pages).
- Chosen because dependency analysis shows lines 31–651 call **0** cluster
  functions → zero import-cycle risk. Leaf modules + graph/community cluster are
  bidirectionally coupled → deferred to later slices.
- Reuses slice-1 locked architecture (facade, downward imports, snapshot test,
  oracle re-pin, monkeypatch-repoint). Target **v0.27.8** (Patch).
- Plan: `.agents/plans/05_db_decomposition_slice2.md`
- **STOPPED for user approval (Universal Strict Workflow Step 4).**

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
