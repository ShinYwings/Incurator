# Bug: SQLite Connection Leak in db.init_db

## Problem Definition
`db.init_db()` in `backend/src/curator/db.py` uses `with sqlite3.connect(db_path) as conn:` to manage the SQLite connection. However, Python's `sqlite3` context manager only automatically commits or rolls back transactions upon exit; it **does not** explicitly close the connection.

As a result, the connection remains alive until it is garbage collected. During this time, the `state.sqlite-wal` and `state.sqlite-shm` sidecar files persist on disk. 

## Impact & Symptom
This behavior causes environment-dependent test failures. On Ubuntu 24.04 (Python 3.11, sqlite 3.45.3), the GC timing differs from macOS. Consequently, in tests like `tests/test_v021_status_stats.py::StatusStatsTests::test_get_stats_bootstraps_when_db_file_exists_without_sources_table`, the main DB file is truncated while the stale `-shm` sidecar remains. A subsequent connection attempting to set `PRAGMA journal_mode=WAL` fails with `sqlite3.OperationalError: database is locked`.

**Deterministic Repro (Ubuntu):**
1. Call `db.init_db(path)`.
2. Observe that `-wal` and `-shm` persist.
3. Call `path.write_bytes(b"")`.
4. Call `db.get_stats(path)` -> raises "database is locked".

## Constraints
- **Root Cause Required**: Do not implement test-level workarounds (like adding `time.sleep()` or manual garbage collection triggers in tests). The underlying connection leak must be fixed.
- **Cross-Platform Resiliency**: The fix must permanently eliminate GC-timing-dependent sidecar persistence on all operating systems.

## Success Criteria
1. `init_db()` and all other `with sqlite3.connect(...)` call sites in the application are audited and updated to ensure connections are explicitly and immediately closed (e.g., using `contextlib.closing` alongside the transaction manager).
2. The `test_get_stats_bootstraps_when_db_file_exists_without_sources_table` test consistently passes on Ubuntu without raising a "database is locked" error.
3. Zero `-wal` or `-shm` sidecar files remain immediately after `init_db()` completes execution.
