# Independent Review: Future-Schema Refusal Prerequisite

Date: 2026-09-14 | Reviewer: lifetime/fleet closer

The bounded v0.82.7 prerequisite is justified independently of the lifetime
release. Current `init_db` and `connect` execute application schema setup and
then overwrite a different version stamp. A newer database opened by this
runtime can therefore be modified and falsely labelled compatible.

Accept a shared guard on the actual SQLite connection before application
`journal_mode` policy, schema DDL, trigger refresh or stamping. A single valid
integer newer than this runtime is refused. Multiple rows and malformed
non-integer/invalid version values are refused. A missing or empty stamp follows
the existing legacy/new-database initialization contract; do not silently turn
this patch into a migration-policy redesign.

Validation must exercise both public entry points, compare schema objects,
retained user rows, version stamp and journal mode after rejection, and retain
valid current/older/new-empty initialization plus existing job-claim transaction
tests. The guarantee is no application DDL/DML or journal-policy change after
refusal. SQLite may create coordination sidecars when reading a WAL database;
this patch must not claim byte-for-byte filesystem immutability.

A private-copy preflight is unnecessary for this guarantee and would introduce
a stale header/WAL and check-versus-open gap. The actual connection supplies the
relevant version check. Concurrent migration remains unsupported: upgrade must
quiesce writers, so the patch does not claim to serialize arbitrary migration
against a previously checked open connection.

This improves rollout only once v0.82.7 or newer is installed on every writer of
the database being upgraded. It cannot retrofit refusal into older installed
binaries, and old plugins writing the shared session file still need coordinated
upgrade separately. A disconnected peer's distinct database may remain old
until its own upgrade; exact-version transport continues to defer that peer.

No application code or production data changed during this review.
