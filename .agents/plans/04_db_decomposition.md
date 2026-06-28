# v0.27.7 — DB-2 db.py Decomposition (slice 1) — Master Implementation Plan

Date: 2026-06-28
Status: DRAFT — awaiting user approval (planning phase; no code yet)
Briefing: `.agents/plans/db2_decomp_arena/00_problem.md`
Domain analysis: `.agents/plans/C_db_package_layout.md`
Parent milestone: `.agents/plans/01_system_stability_overhaul.md`

## 1. Objective
Convert the 4759-LOC `db.py` god-file into a `db/` package with a re-export
facade, **with zero caller changes and zero behavior change**. Slice 1 extracts
the foundational layers (schema/migrations/connect + job queue) into their own
modules and moves the rest verbatim into a holding module; follow-up slices carve
the holding module into per-entity repositories.

**Definition of done (slice 1)**: `curator/db` is a package; `db.*` public surface
is identical (snapshot test passes); `schema.py` + `jobs.py` exist; remaining repo
code lives in `db/_entities.py` re-exported by the facade; full `pytest` ≥ prior
pass count, `ruff`/`mypy` clean, testbed `wiki add/sync` unaffected.

## 2. Explicit Non-Goals
- NO behavior/SQL/schema change (verbatim moves only).
- NO carving `_entities.py` into per-entity modules in slice 1 (follow-ups).
- NO caller edits (the facade preserves `db.<name>`).
- NO query "improvements" (preserve `_chunked` batching — DB-1).
- NOT touching CM-1 / PL-1.

## 3. Strict Quality Conditions & Release Gates
- `test_db_public_api.py` (P0 snapshot) asserts the facade exposes a **superset**
  of the pre-refactor public `db.*` names — no symbol silently dropped. The
  snapshot captures only names **owned by the db package** (filter:
  `__module__` startswith `"curator.db"`), which (a) excludes re-imported stdlib
  (`sqlite3`, `json`, `Path`, …) so the facade need not re-export them, and (b)
  tolerates the post-refactor `__module__` change from `curator.db` →
  `curator.db.schema` / `curator.db._entities` (prefix match). Any public bare
  constant/enum lacking a usable `__module__` is added to an explicit allowlist
  captured during P0.
- Full `scripts/backend-check pytest` ≥ baseline pass count; `ruff`/`mypy` clean.
- `import curator.db as db` and `from curator import db` both resolve identically;
  no circular-import error.
- Testbed `VAULT_ROOT=testbed wiki add/sync` unaffected (smoke).
- `git diff --check` clean.

## 4. Locked Design Decisions (Arena Consensus)
- `db.py` → `db/` package; `__init__.py` re-export facade (callers use `db.<name>`,
  verified zero name-imports).
- Submodules import **downward only** (`from .schema import …`); never the facade;
  underscore helpers imported explicitly, not via `import *` (R1/R2).
- **No manual `__all__`.** The facade re-exports via `from .<module> import *`,
  which by default exports every top-level **non-underscore** name — so the
  ~100-function holding module `_entities.py` needs **no** hand-maintained
  `__all__` (manually enumerating it would guarantee omissions). Underscore
  helpers stay private to `schema.py` and are imported explicitly by the modules
  that need them. Verbatim moves mean each public name is defined exactly once,
  so there are no `import *` name collisions.
- Verbatim moves; no logic edits; commit message enumerates line-range → module.
- **Patch 0.27.7** — internal refactor; spec titles untouched. Update CLAUDE.md
  module table (`db.py` → `db/`).

## 5. Scope Exclusions & Stop Conditions
- **Exclusions**: per-entity carving (follow-ups), CM-1, PL-1.
- **Stop Conditions**:
  - If a circular import or a dropped/shadowed symbol can't be resolved cleanly,
    revert that module move (per-module commits) and reassess — do NOT paper over
    with hacks.
  - If the snapshot test shows the facade missing a name, STOP and fix the export
    before proceeding.

## 6. Evidence Ledger
`04_roadmap_evidence.md` before P1: rollback anchor (branch off master post-#65;
per-module commits), baseline pytest count, the captured public-API snapshot, and
the section line-range → module mapping (audit trail of the move).

## 7. Execution Phases (full pytest + mypy after EACH)
- **P0 — API snapshot + baseline.** Add `test_db_public_api.py` capturing the
  current package-owned public `db.*` names (filter per §3) + the constant/enum
  allowlist; record baseline pytest count. No code move yet.
- **P1 — Package skeleton + schema.py.** Convert the module to a package with
  **`git mv backend/src/curator/db.py backend/src/curator/db/_entities.py`** — this
  creates the `db/` dir, moves the file, and preserves git history in one step,
  and avoids any transient state where both a `db.py` module and a `db/` package
  resolve as `curator.db`. Then add `db/schema.py` and **move** helpers +
  migrations + DDL + connect + init_db + get_stats + enums out of `_entities.py`
  into it (`_entities.py` imports them back via `from .schema import …`). Add
  `db/__init__.py` facade (`from .schema import *`; `from ._entities import *`).
  Run full pytest + mypy + the P0 snapshot test.
- **P2 — jobs.py.** Carve the job queue out of `_entities.py` into `jobs.py`
  (`from .schema import connect, _now_iso, …`); facade adds `from .jobs import *`.
  Full pytest + mypy + snapshot.
- **P3 — Verify + docs + release.** Snapshot test green; testbed smoke; update
  CLAUDE.md module table; version 0.27.7; CHANGELOG; PR.

## 8. Multi-Agent Role Sign-off (simulated)
- **schema_guardian**: no DDL/migration/SQL change; DDL strings moved verbatim;
  snapshot test guards the public surface.
- **peer_reviewer**: downward-only imports; explicit helper imports; no logic edits.
- **qa_runner**: full pytest + ruff + mypy after each move + testbed smoke.
- **rollback_strategist**: per-module commits → revert a single move cleanly.
