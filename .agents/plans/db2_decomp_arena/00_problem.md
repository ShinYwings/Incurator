# Briefing: DB-2 — Decompose db.py (4759 LOC god-file)

Date: 2026-06-28 | Phase: System Stability Overhaul → Phase C (S2 architectural)

## Problem

`backend/src/curator/db.py` is a 4759-LOC god-file (145 top-level defs) holding,
in one module: schema DDL, idempotent migrations, the job queue, and repository
queries + lifecycle reconciliation for ~15 entities (sources, source_spans,
knowledge_units, claim_supports/compiler_generations, graph_entities/relations,
entity resolution, relation lifecycle, community construction, community_reports,
graph-generation compiler, graph audit, memory_paths, prompt_runs, curation_plans,
insight_candidates, artifact_dependencies, synthesis_nodes). Diagnosis item DB-2.

## The safety backbone (verified)

Every caller imports db as a **module** (`from . import db` / `from .. import db`)
and uses `db.<name>()`. There are **zero** `from .db import <name>` name-imports
in the codebase. Therefore converting `db.py` → a `db/` **package** whose
`__init__.py` re-exports every public name preserves the entire public surface
(`db.<name>`) with **zero caller changes**.

## Constraints

- **Pure structural refactor**: NO behavior change, NO schema change, NO SQL
  change. The decomposition must be byte-for-byte behavior-preserving.
- **DB-1 positive (keep)**: `db.py` already uses `_chunked` 900-row IN-clause
  batching — the move must preserve it, not "simplify" it.
- **`connect()` is shared** by every repository function → lives in the schema/core
  module and is imported by the others.
- **No silent API drift**: the facade must re-export EVERY public name the module
  exposes today (guarded by a test).
- **Incremental**: this is multi-PR. Slice 1 establishes the package + facade and
  extracts the foundational layers; entity repositories are carved in follow-ups.

## Definition of done (slice 1)

`db` is a package with an `__init__.py` facade; the public `db.*` surface is
identical (asserted by a snapshot test); schema/migrations + job queue (+ the
chosen first repository group) live in their own modules; the rest sits in a
holding module re-exported by the facade; full `pytest`/`ruff`/`mypy` green and
testbed `wiki add/sync` unaffected.
