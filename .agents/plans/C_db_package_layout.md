# Domain Analysis: db.py → db/ package layout (DB-2)

Date: 2026-06-28

## Current reality
- `backend/src/curator/db.py`: 4759 LOC, 145 top-level defs, sectioned by entity.
- Public surface = module-attribute access only: all callers `from . import db`
  (or `from .. import db`) then `db.<name>()`. Zero `from .db import <name>`.
- `connect()` (context manager) is the shared DB accessor used by every repo fn.
- Frozen resolution enums + DDL constants live at module level (executed at import).

## Section map (line ranges → target module)
| db.py lines | content | target |
|---|---|---|
| 26–~120 | frozen resolution enums | schema.py |
| 718–1330 | helpers, migrations, init_db, connect, get_stats | schema.py |
| 1330–~1600 | ingest job queue | jobs.py |
| ~1600–1953 | sources / ingest runs / source pages | _entities.py (→ sources.py later) |
| 1954–2280 | source_spans, knowledge_units | _entities.py (→ spans/knowledge_units) |
| 2281–3417 | claim_supports, graph_*, resolution, relations, community | _entities.py (→ later) |
| 3418–3868 | community_reports, graph-generation compiler | _entities.py (→ community) |
| 3869–4759 | audit, memory_paths, prompt_runs, curation_plans, insights, artifact_deps, synthesis | _entities.py (→ leaf modules) |

## Slice-1 layout (this PR)
```
curator/db/__init__.py   # facade: from .schema import *; from .jobs import *; from ._entities import *
curator/db/schema.py     # helpers + migrations + DDL + connect + init_db + get_stats + enums
curator/db/jobs.py       # job queue (imports connect/_helpers from .schema)
curator/db/_entities.py  # everything else, verbatim (imports from .schema)
```
Follow-up slices carve `_entities.py` into sources/spans/knowledge_units/claims/
graph/resolution/relations/community/audit + leaf modules.

## Invariants / guards
- Public `db.*` names: SUPERSET-preserved, asserted by `test_db_public_api.py`
  (P0 snapshot). Snapshot filter = package-owned names only (`__module__`
  startswith `"curator.db"`): excludes re-imported stdlib (`sqlite3`/`json`/…) and
  tolerates the `__module__` move (`curator.db` → `curator.db.schema`/`._entities`).
  Public bare constants/enums lacking `__module__` → explicit allowlist (P0).
- `_chunked` batching preserved verbatim (DB-1).
- Submodules import downward only (`from .schema import …`); never `from . import db`.
- **No manual `__all__`** — facade `from .<mod> import *` auto-exports non-underscore
  public names; underscore helpers live in `schema.py`, imported explicitly. Avoids
  enumerating `_entities.py`'s ~100 functions by hand.
- Package conversion via `git mv db.py db/_entities.py` (history-preserving; no
  db.py/db-package import ambiguity), then carve `schema.py`/`jobs.py` out of it.

## Docs / version
- No schema/contract/behavior change → **Patch 0.27.7**; spec titles untouched.
- Update CLAUDE.md architecture module table: `db.py` → `db/` (package).
- SCHEMA.md documents tables (unchanged); no spec edit needed.

## Alternatives rejected
- *Leave as one file, add section markers*: doesn't address the god-file (DB-2).
- *Rewrite queries while moving*: violates "verbatim, behavior-preserving"; would
  make the diff unreviewable and risk regressions.
