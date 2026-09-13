# Domain Analysis: Schema Open Guard

Date: 2026-09-13

## Code and specification constraints

`db/schema.py` exposes `init_db` and context-managed `connect`. Both open SQLite,
set WAL, apply SCHEMA_SQL, refresh triggers and stamp version 14. The stamp
currently overwrites any unequal value. SYSTEM_BEHAVIOR §26.6 promises current
schema initialization, while job semantics require setup committed before yield.
Future-version import rejection exists independently and cannot protect local
DB opening. The guard must run before setup in both entry points.

## Alternatives and tradeoffs

Checking only in `_stamp_schema_version` happens after schema changes and is too
late. Checking an isolated DB copy adds copying and a TOCTOU without securing
the real connection. Holding a new migration lock across every connection is a
different lifecycle contract, unnecessary for refusing an already-newer DB.
The selected actual-connection read is small and sees committed WAL changes.
This does not establish safety for upgrading a DB beneath existing live callers.

## Final decision and pseudocode

Read sqlite_master for the schema_version table. Missing table means existing
initialization path. Reject an object under that name that is not a table.
Read at most two version/type pairs; empty means initialization, anything other
than one positive SQLite integer means inconsistent stamp, and a greater value
means incompatible runtime. Raise before setup. Keep connection close in finally.

```text
conn = sqlite.connect(path)
try:
    check_existing_schema_version(conn)
    existing_journal_schema_trigger_stamp_setup(conn)
    commit_setup()
    yield_outside_transaction_if_connect()
finally:
    close(conn)
```

Version 14 remains unchanged. Older binaries still require upgrade before a
later production migration. A reader can create SQLite-managed sidecars, so
tests assert application data/schema/stamp/journal policy preservation rather
than presenting this as a cache-style no-filesystem-effects inspector.
