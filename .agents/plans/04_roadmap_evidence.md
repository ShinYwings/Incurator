# Evidence Ledger — v0.27.7 DB-2 db.py Decomposition (slice 1)

Date: 2026-06-28 | Branch: `fix/db-decomposition` (off `master` post-#65)

## Rollback anchor
- Base: `master` at `622f432` (post PR #65) + plan-docs commit.
- Per-phase commits (git mv preserves history) → single-phase revert.

## Baselines
- Backend `pytest` (branch base): **1119 passed**.
- Public `db.*` API: 128 names (118 package-owned functions + 10 public
  constants), captured in `backend/tests/test_db_public_api.py` (P0). Test green
  pre-refactor.

## Public API snapshot (P0) — DONE
- Filter: package-owned names (`__module__` startswith `"curator.db"`) + allowlist
  of 10 bare constants (`*_STATUSES`/`*_CODES`/`SUPPORT_ROLES`/`SCHEMA_SQL`/
  `SCHEMA_VERSION`). Excludes stdlib/typing re-imports; tolerates `__module__` move.

## Section line-range → target module (move map)
| db.py lines | content | slice-1 target |
|---|---|---|
| 26–~120 | frozen resolution enums + constants | schema.py |
| 718–1330 | helpers (_now_iso/_chunked/_maybe_conn), migrations, init_db, connect, get_stats | schema.py |
| 1330–~1600 | ingest job queue | jobs.py (P2) |
| ~1600–4759 | sources + all entity repositories | _entities.py (holding; carved in follow-ups) |

## P1 — package + schema.py — DONE (pending full-suite gate)
- `git mv db.py db/_entities.py` (history preserved); split header (lines 1-1329)
  into `db/schema.py`; facade `db/__init__.py`.
- schema.py = enums/constants (SCHEMA_VERSION, RESOLUTION/MERGE/QUARANTINE codes,
  SCHEMA_SQL), helpers, migrations, init_db, connect, _maybe_conn, get_stats.
- `_entities.py` imports downward: `from .schema import (connect, _now_iso,
  _chunked, _maybe_conn, _QUARANTINE_REEVAL_TRIGGERS,
  _RELATION_CORROBORATION_THRESHOLD)`. (SUPPORT_*/FORMULA_*/GENERATION_*/
  GRAPH_AUDIT_CODES are defined in `_entities.py` itself.)
- Relative import lifted: `from . import constants` → `from .. import constants`.
- Facade re-exports `import *` over schema + _entities, PLUS explicit
  `_maybe_conn`/`_now_iso` — external callers use `db._maybe_conn`/`db._now_iso`
  (claim_support, compile). Snapshot test extended to guard these underscore
  externals (lesson: the public-only snapshot missed them).
- ruff --fix removed 8 split-artifact stdlib imports; mypy clean.
- Test fix (module move, not behavior): `test_db_schema.py` patches
  `curator.db.schema._apply_migrations` at its real location.

## P2 — jobs.py — DEFERRED to slice 2 (plan §5 scope trim)
Keeps slice 1 reviewable and re-pins the D2 frozen oracle only once.

## Frozen-oracle + monkeypatch fixups (module-move consequences)
- D2 holdout oracle re-pinned: `db.py` fingerprint → `db/__init__.py` +
  `db/schema.py` + `db/_entities.py`, with a `db2_package_decomposition_rearm`
  narrative note (behavior-preserving).
- 2 white-box tests repointed to the helper's real lookup location after the
  split: `test_db_schema.py` → `curator.db.schema._apply_migrations`;
  `test_abstraction_source_trace.py` → `curator.db._entities.connect`.

## P3 — verify + docs + release — DONE
- CLAUDE.md architecture table: `db.py` → `db/` package.
- Version 0.27.7 (Patch; spec titles untouched); CHANGELOG entry.
- Final full pytest gate: see Validation.
