# Proposal: db.py → db/ package with re-export facade

Date: 2026-06-28 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### Target package layout (full vision, reached over several slices)
```
curator/db/
  __init__.py        # facade: re-exports every public name (back-compat)
  schema.py          # _now_iso, _chunked, _column_names, _maybe_conn, connect,
                     # init_db, _add_column_if_missing, _apply_migrations,
                     # _migrate_*, the CREATE TABLE DDL, get_stats, frozen enums
  jobs.py            # ingest job queue (enqueue/claim/progress/done/failed/…)
  sources.py         # sources, ingest runs, source pages
  spans.py           # source_spans
  knowledge_units.py # knowledge_units
  claims.py          # claim_supports / compiler_generations
  graph.py           # graph_entities / graph_relations
  resolution.py      # entity resolution / reversible merges
  relations.py       # relation lifecycle / topology
  community.py       # community construction + community_reports + graph-gen compiler
  audit.py           # read-only graph invariants
  memory_paths.py / prompt_runs.py / curation_plans.py / insights.py /
  artifact_deps.py / synthesis.py   # leaf entities
```

### The facade (`__init__.py`)
Each submodule declares `__all__`. `__init__.py`:
```python
from .schema import *      # noqa: F401,F403
from .jobs import *        # noqa: F401,F403
from ._entities import *   # holding module (slice 1), later replaced by per-entity
...
```
Because callers only do `db.<name>`, re-export is sufficient — no caller edits.

### Cross-module wiring
- `schema.py` depends on nothing internal (stdlib + sqlite only).
- Every other module: `from .schema import connect, _now_iso, _chunked, _maybe_conn`
  (underscore helpers imported explicitly; they are NOT re-exported by `*`).
- Module-level constants/enums (frozen resolution enums at db.py:26) move to
  `schema.py` and are re-exported.

### Slice-1 scope (this PR)
1. Create the `db/` package + `__init__.py` facade.
2. Extract `schema.py` (helpers, migrations, DDL, connect, init_db, get_stats,
   enums) and `jobs.py` (job queue).
3. Move ALL remaining repository functions verbatim into a single holding module
   `db/_entities.py`, re-exported by the facade.
4. Behavior-preserving: cut/paste only; no logic edits.
Follow-up slices carve `_entities.py` into the per-entity modules above, one
cohesive group per PR.

### Safety net (P0, before moving anything)
A snapshot test `test_db_public_api.py` records the sorted set of public
`db.*` names (everything not starting with `_`, plus the explicitly-public
underscore names callers use, if any) and asserts the post-refactor facade
exposes a **superset** — so no symbol is silently dropped.

## 2. Pros & Cons
**Pros**: zero caller changes (module-attribute access + facade); incremental and
low-risk (verbatim moves under a strong test suite); finally separates schema from
repositories. **Cons**: a package conversion touches import resolution
(circular-import risk if a submodule imports the facade) — mitigated by submodules
importing `from .schema import …`, never `from . import db`. Slice 1 leaves a large
`_entities.py` holding module (honest interim state; carved next).
