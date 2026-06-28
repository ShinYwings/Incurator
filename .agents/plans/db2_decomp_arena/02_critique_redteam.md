# Critique + Resolution — db.py decomposition

Date: 2026-06-28 | Agent Persona: red_teamer / schema_guardian

## 1. Vulnerabilities & Flaws

1. **`from .schema import *` drops underscore helpers.** Repository functions
   call `_now_iso`, `_chunked`, `_maybe_conn` — these start with `_` so `import *`
   won't re-export them, and a moved repository module that forgot to import them
   explicitly raises `NameError` at call time (not import time → may pass a shallow
   smoke test, fail in a rare path).

2. **Circular imports.** If any submodule does `from . import db` (the facade) for
   a sibling function, importing the package triggers a partially-initialized
   module → `ImportError`/`AttributeError` at load.

3. **Module-level state executed at import.** db.py:26 frozen enums and any
   module-level constants must move exactly once; duplicating or losing them
   changes behavior. The DDL string constants likewise.

4. **`__all__` omissions = silent API loss.** A public function not in its
   submodule's `__all__` (or shadowed by another module's `*`) disappears from
   `db.*` → callers break only when that path runs.

5. **Name collisions across modules under `import *`.** Two submodules exporting
   the same helper name → last-wins, silently shadowing.

6. **mypy/ruff package semantics.** `db/__init__.py` with `import *` triggers
   `F403/F405`; the snapshot test and explicit `__all__` must keep this clean.

7. **Git history / reviewability.** A 4759-line cut/paste is hard to review for
   "no logic change." Reviewer can't easily diff moved code.

## 2. Suggested Alternatives (accepted)

- **R1 — Explicit helper imports + NO manual `__all__`.** Each submodule imports
  `from .schema import connect, _now_iso, _chunked, _maybe_conn` explicitly. The
  facade uses `from .<mod> import *`, which auto-exports every non-underscore
  top-level name — so **no submodule defines a manual `__all__`** (hand-listing
  the ~100 functions in `_entities.py` would guarantee omissions and a snapshot
  failure loop). Verbatim moves ⇒ each public name defined once ⇒ no `import *`
  collisions.
- **R2 — Submodules import only downward** (`from .schema import …`), NEVER
  `from . import db` and never a sibling-via-facade. If two entity modules need a
  shared helper, it lives in `schema.py` (or a tiny `_util.py`), not cross-imported.
- **R3 — API snapshot test FIRST (P0)**, asserting the facade exposes a superset
  of today's public names. Primary guard against #1/#4/#5. The snapshot captures
  only **package-owned** names (`__module__` startswith `"curator.db"`): this
  excludes re-imported stdlib (`sqlite3`/`json`/`Path`) so the facade need not
  re-export them, and tolerates the `__module__` change after the move (prefix
  match). Public bare constants/enums without a usable `__module__` → explicit
  allowlist captured in P0.
- **R4 — `mypy` + full `pytest` after EACH module move**, not just at the end —
  the suite exercises db heavily; a `NameError`/missing-export surfaces fast.
- **R5 — Reviewability + history**: convert via
  `git mv db.py db/_entities.py` so git tracks the bulk as a rename (blame/history
  preserved) and there is never a transient state where both a `db.py` module and
  a `db/` package resolve as `curator.db`. Then carve `schema.py`/`jobs.py` out of
  `_entities.py`. Slice 1 is verbatim moves only (no renames of symbols, no logic
  edits); the commit message enumerates which line-ranges moved to which module.
- **R6 — Patch (0.27.7)**: pure internal refactor, no contract/schema/behavior
  change; spec titles untouched. Update the CLAUDE.md module table (`db.py` → `db/`).

## 3. Consensus
Adopt R1–R6. Helpers imported explicitly; submodules import downward only; API
snapshot test is P0; full pytest+mypy after each move; verbatim moves only.
Stop-condition: if a circular import or dropped symbol can't be resolved cleanly,
revert that module's move (per-module commits) and reassess.
