# v0.27.8 — DB-2 db.py Decomposition (slice 2) — Master Implementation Plan

Date: 2026-06-29
Status: DRAFT — awaiting user approval (planning phase; no code yet)
Reuses the LOCKED architecture from slice 1 (shipped v0.27.7, PR #66):
`.agents/plans/04_db_decomposition.md` + `.agents/plans/C_db_package_layout.md`
+ arena `.agents/plans/db2_decomp_arena/`.
Parent milestone: `.agents/plans/01_system_stability_overhaul.md`

## 1. Objective
Continue carving the `db/_entities.py` holding module (3457 LOC) created in slice
1. Extract two **dependency-leaf** groups into their own modules — **zero behavior
change, verbatim moves, facade preserves `db.<name>`**:
- `db/jobs.py` — the ingest job queue (deferred from slice 1).
- `db/sources.py` — sources, source layer-status, DAG edges, source pages.

**Definition of done**: `db/jobs.py` and `db/sources.py` exist; `_entities.py`
holds the rest; `db.*` public surface identical (existing `test_db_public_api.py`
snapshot passes); full `pytest` ≥ prior pass count; `ruff`/`mypy` clean; testbed
`wiki status` unaffected.

## 2. Why these two (dependency analysis — done in planning)
- The top region of `_entities.py` (lines 31–651 = job queue + sources/pages/DAG)
  calls **0** cluster functions (graph/community/knowledge/span/claim/leaf).
  Verified by grep. → jobs.py and sources.py import only `from .schema import …`.
- The remaining cluster may call `sources` helpers (e.g. `set_source_layer_status`)
  one-directionally (`_entities` → `sources`); `sources`/`jobs` never import
  `_entities` → **no import cycle**.
- **Explicitly NOT in scope**: the leaf entity modules (synthesis, memory_paths,
  prompt_runs, curation_plans, insights, artifact_deps) and the graph/community/
  knowledge/claim cluster. They are **bidirectionally coupled** — the cluster
  calls `record_artifact_dependency` while leaves call ≥4 cluster functions — so
  carving them needs shared-helper relocation + cycle analysis in a later slice.

## 3. Locked Design Decisions (inherited from slice 1)
- `db/` package + `__init__.py` re-export facade; callers use `db.<name>`.
- Submodules import **downward only** (`from .schema import connect, _now_iso,
  _chunked, _maybe_conn, …`); never the facade; verbatim moves, no logic edits.
- Facade adds `from .jobs import *` and `from .sources import *`.
- No manual `__all__` (facade `import *` auto-exports non-underscore names).
- **Patch 0.27.8** — internal refactor; spec titles untouched.

## 4. Known module-move consequences to handle (from slice 1 experience)
- **D2 frozen oracle re-pin**: `_entities.py`'s SHA changes and `jobs.py`/
  `sources.py` are added → update `D2_HOLDOUT_RESULT.yml` `evaluated_code.file_sha256`
  (add the 2 new files, re-hash `_entities.py`) + a re-arm note. (Re-pinned once.)
- **Monkeypatch-location tests**: any white-box test patching `db.<fn>` for a
  moved function must repoint to its new module (`curator.db.jobs.<fn>` /
  `curator.db.sources.<fn>`). Grep for `setattr(db,` / `setattr("curator.db.` and
  fix. (Slice 1 had 2 such tests; expect similar.)
- **Snapshot test** already guards the public surface + underscore externals;
  no new public names, so it should pass unchanged.

## 5. Scope Exclusions & Stop Conditions
- **Exclusions**: leaf modules + graph/knowledge/claim/community cluster (next
  slices), CM-1, PL-1.
- **Stop Conditions**:
  - If carving `sources.py`/`jobs.py` reveals an unexpected cross-reference that
    would create an import cycle, STOP and reduce scope (ship whichever is clean).
  - If the snapshot test reports a dropped/shadowed symbol, STOP and fix the
    export before proceeding.

## 6. Evidence Ledger
`05_roadmap_evidence.md` before P1: rollback anchor (branch off master post-#66;
per-module commits), baseline pytest count, the section line-range → module map
(jobs vs sources boundary within lines 31–651), and the oracle re-pin record.

## 7. Execution Phases (full pytest + mypy after EACH move)
- **P0 — Baseline.** Record baseline pytest count; confirm the jobs/sources
  boundary line in `_entities.py`. (Snapshot test already exists.)
- **P1 — jobs.py.** Move the job-queue functions out of `_entities.py` into
  `db/jobs.py` (`from .schema import …`); facade adds `from .jobs import *`. Full
  pytest + mypy + snapshot; repoint any `db.<jobfn>` monkeypatch tests.
- **P2 — sources.py.** Move sources / layer-status / DAG-edge / source-page
  functions into `db/sources.py`; facade adds `from .sources import *`. Full
  pytest + mypy + snapshot; repoint monkeypatch tests.
- **P3 — Oracle + docs + release.** Re-pin D2 oracle (add jobs.py/sources.py,
  re-hash `_entities.py`, re-arm note); update CLAUDE.md module table if needed;
  version 0.27.8; CHANGELOG; PR.

## 8. Multi-Agent Role Sign-off (simulated)
- **schema_guardian**: no DDL/SQL/schema change; verbatim moves; snapshot guards surface.
- **peer_reviewer**: downward-only imports; no cycles (analysis in §2); no logic edits.
- **qa_runner**: full pytest + ruff + mypy after each move + testbed `wiki status`.
- **rollback_strategist**: per-module commits → revert a single move cleanly.
