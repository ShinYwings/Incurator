# Active Relay State

**STATUS: DB-2 slice 1 shipped to PR #66 — awaiting merge.**

**Current branch**: `fix/db-decomposition`

**Last refreshed**: 2026-06-29 by Claude Code.

---

## Goal

System Stability Overhaul Phase C, S2 god-file decomposition **DB-2**: convert
`db.py` (4759 LOC) into a `db/` package with a re-export facade — zero caller
changes, behavior-preserving. Shipped as **v0.27.7** in PR #66.

## Progress
- `db.py` → `db/` package: `schema.py` (DDL/migrations/connect/init/enums) +
  `_entities.py` (repositories, via `git mv` so history preserved) + `__init__.py`
  facade. Public `db.*` surface intact; facade also re-exports `db._maybe_conn`/
  `db._now_iso` (external callers).
- New `test_db_public_api.py` snapshot (128 public + 2 underscore externals).
- Module-move fixups: D2 frozen oracle re-pinned (`db.py` → 3 `db/` files +
  re-arm note); 2 white-box monkeypatch tests repointed to real lookup locations.
- **jobs.py + per-entity carving DEFERRED to slice 2** (plan §5).
- Full pytest 1121 passed; ruff/mypy clean; vitest 626 + tsc clean; spec-sync at
  0.27.7. CLAUDE.md table + CHANGELOG updated.

## Immediate Next Action
- Human: review and merge PR #66.
- After merge, **DB-2 slice 2** (fresh branch, own plan): carve `_entities.py`
  into `jobs.py` + per-entity modules (sources, spans, knowledge_units, claims,
  graph, resolution, relations, community, audit, leaf entities), each a small
  verbatim-move PR re-pinning the D2 oracle. Then CM-1 (cli/mcp) and PL-1 (plugin)
  remain as the other S2 god-files.
