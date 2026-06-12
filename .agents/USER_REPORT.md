# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

- **[Bug] `db.init_db` leaks its SQLite connection (WAL sidecars persist; environment-dependent "database is locked")** — reported by Claude Code during Plan E P7 verification on Ubuntu 24.04 (2026-06-12).
  - `backend/src/curator/db.py` `init_db()` uses `with sqlite3.connect(db_path) as conn:` — Python's sqlite3 context manager only commits/rolls back the transaction; it does **not** close the connection. The connection is left to GC.
  - Observable symptom: after `init_db()` returns, `state.sqlite-wal` / `state.sqlite-shm` sidecar files remain on disk while the leaked connection is alive. On Ubuntu 24.04 + Python 3.11 (anaconda-based venv, sqlite 3.45.3), GC timing differs from macOS, so `tests/test_v021_status_stats.py::StatusStatsTests::test_get_stats_bootstraps_when_db_file_exists_without_sources_table` fails with `sqlite3.OperationalError: database is locked`: the test truncates the main DB file while the stale `-shm` from the leaked connection still exists, and the next `PRAGMA journal_mode=WAL` cannot acquire the lock.
  - Repro (deterministic on Ubuntu): `db.init_db(path)` → observe `-wal`/`-shm` persist → `path.write_bytes(b"")` → `db.get_stats(path)` raises "database is locked".
  - Suggested direction (not implemented — Plan E branch forbids production changes): explicitly close the connection in `init_db` (e.g., `contextlib.closing`), and audit other `with sqlite3.connect(...)` call sites for the same commit-only misconception. Root-cause fix, no workaround.
  - Cross-platform note: this is exactly the class of macOS↔Ubuntu environment divergence the dual-platform setup must tolerate; the fix should not depend on GC timing on either platform.