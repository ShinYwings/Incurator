# Evidence Ledger — v0.27.8 DB-2 Decomposition (slice 2)

Date: 2026-06-29 | Branch: `fix/db-decomposition-slice2` (off `master` post-#66)

## Rollback anchor
- Base: `master` post PR #66 + plan-docs commit. Carve is one commit (jobs +
  sources together — same contiguous region); revertible as a unit.

## Dependency analysis (planning)
- `_entities.py` lines 31–651 (job queue + sources/pages/DAG) call **0** cluster
  functions; cluster calls **0** of them back → zero import-cycle risk.
- `json_dumps` (in the sources region) is used only within that region (cluster
  0 uses) → travels with `sources.py`.
- Leaf modules (synthesis/memory_paths/…) ↔ cluster are bidirectionally coupled
  (cluster calls `record_artifact_dependency`; leaves call ≥4 cluster fns) →
  deferred to a later slice.

## Carve (P1+P2)
- `db/jobs.py`: `enqueue_job`..`get_pending_count` (16 fns), imports
  `from .schema import connect, _now_iso` (ruff-trimmed to used set).
- `db/sources.py`: `set_source_layer_status`..`get_source_row` + `json_dumps`,
  `source_path_to_relpath`, vision-cache, page-hash, pdf-pages.
- `_entities.py` keeps the cluster (652+); `consts` import dropped (now unused
  there). Facade `__init__.py` += `from .jobs import *`, `from .sources import *`.
- ruff --fix removed 27 split-artifact imports; mypy clean (102 source files).

## Module-move consequences
- D2 frozen oracle re-pinned: re-hashed `db/__init__.py` (facade lines added) +
  `db/_entities.py`; added `db/jobs.py` + `db/sources.py` fingerprints; added a
  `db2_slice2_jobs_sources_rearm` note.
- Monkeypatch tests: none needed repointing this slice (the one white-box test
  patches `curator.db._entities.connect`, and `connect`/`sources_for_spans`
  remain resolvable; snapshot + abstraction tests green).

## Validation
- Targeted: db + snapshot + abstraction + D2 oracle tests green (49).
- ruff + mypy clean; spec_sync green at 0.27.8.
- Full pytest gate: see PR.
