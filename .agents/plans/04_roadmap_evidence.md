# Evidence Ledger — v0.27.7 DB-2 db.py Decomposition (slice 1)

Date: 2026-06-28 | Branch: `fix/db-decomposition` (off `master` post-#65)

## Rollback anchor
- Base: `master` at `622f432` (post PR #65) + plan-docs commit.
- Per-phase commits (git mv preserves history) → single-phase revert.

## Baselines
- Backend `pytest`: (branch-base background run — recorded on completion).
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

## P1 — package + schema.py — pending
## P2 — jobs.py — pending
## P3 — verify + docs + release — pending
