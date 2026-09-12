# Synchronization and Cache Safety Proposal: Repair the Existing Debris Proof
Date: 2026-09-11 | Agent Persona: Adversarial Synchronization / Data Preservation Reviewer

## 1. Core Logic & Implementation

### Recommendation and scope

The smallest independently justified next release is a patch to the existing
cache collector's eligibility proof and read-only inspection. It addresses a
verified deletion hazard in B1/B2 without choosing new history windows, changing
transport, expiring tombstones, or removing a useful user capability. It does
not finish the whole retention queue. Remaining diagnostic/history policy is a
separate product decision after this guard is corrected.

### Shipped behavior, verified against code

- `gc.py:100–144` selects a cache namespace only when its marker names an absent
  temporary root and its `sources` count is zero. Directories without a database
  also qualify. `gc.py:147–158` recursively deletes selected paths.
- `commands/gc.py:144–178` plans first, can pause for user confirmation, then
  passes the old candidate list directly to `sweep`.
- `config.py:180–189` writes a resolved vault-root marker. A cached database is
  machine-local, and a missing non-temporary root is intentionally insufficient
  evidence for deletion (`gc.py:41–54`). Keep this offline-mount protection.
- `db_sync.py:47–74` exports `deleted_records`, prompt/query diagnostics and
  compiler history. Tombstones precede inserts in snapshots. Local bookkeeping
  is in `.cache/config/sync_state` (`db_sync.py:828–833`), and records a per-file
  imported `last_export_id` (`db_sync.py:2785–2819`). It does not convey a peer's
  receipt of our deletion. A known device registry is not an acknowledgement
  protocol either.
- Current guides promise “provably debris” but specify the insufficient
  zero-sources test (`docs/guides/USER_GUIDE.md:1080`). Existing tests protect
  non-temp missing roots, live roots, source-bearing databases, unreadable
  SQLite files, and absent markers (`backend/tests/test_gc_cache_sweep.py`).

### Verified defect A: planning writes into candidate databases

`gc.py:132` uses `db.get_stats`. That opens `db.connect` (`db/schema.py:1005`),
which enables WAL, executes current schema DDL, refreshes triggers and stamps the
schema version (`db/schema.py:945–951`). The exception handler around this call
does not undo those committed mutations. Inspection can “repair” an incomplete
or unfamiliar database into something whose newly created `sources` is empty,
then classify it as disposable.

Isolated reproduction, executed with `.venv-dev/bin/python` and automatically
removed `TemporaryDirectory` fixtures only:

1. Create a marker under an absent `/private/tmp/` root.
2. Create `state.sqlite` containing only `unfamiliar_durable_history(value)` and
   insert one `must survive` row.
3. Save database bytes; call `dead_vault_caches` without `sweep`.
4. Observed: cache **is reclaimable**, bytes **changed**, and the `sources` table
   **was created**. No live cache or user vault was modified.

### Verified defect B: zero sources is not absence of retained data

The same isolated fixture with a fully initialized schema, zero sources, and
one `deleted_records` row is returned as reclaimable. No source row is needed
for prompt diagnostics, query history, terminal job evidence, or deletion
markers to remain valuable. Recursively deleting the namespace also removes
its other files. A temp-root predicate narrows exposure but does not prove all
surviving state is dispensable; the existing source-bearing-fixture test itself
acknowledges that real work and test fixtures can share a temporary prefix.

Blast radius: a namespace whose marker names an absent temporary directory;
ordinary `/Users/`, `/Volumes/`, NAS, and existing roots already fail selection.
A source-less namespace can be the last local copy of terminal history or
unexported tombstones. Losing those is not an authorized history policy.

### Verified defect C: eligibility can change after the plan

`sweep` makes no current marker/root/database check (`gc.py:151–153`). During the
CLI confirmation gap, a root can reappear or a source can be ingested into the
cache; accepting the old plan then recursively deletes it. This follows directly
from the call sequence. A focused test can plan an empty fixture, add a source
or recreate its root, then require that `sweep` skips it. Symlinked and replaced
namespace identities must likewise be rejected rather than following an old
path's authority onto its new target.

### Minimal patch design

1. Introduce one small internal cache-eligibility predicate, used by both
   `dead_vault_caches` and `sweep`. Its proof covers a real namespace directory,
   a readable regular marker, canonical absent temporary root, and safely
   inspected database state. Reject symlinked namespace/marker/database paths
   and unrecognized or unreadable database layouts.
2. Inspect existing SQLite with a `mode=ro` URI and ordinary read queries;
   never call `db.connect`, schema initialization, stats helpers, or migrations.
   Do **not** use `immutable=1` to suppress WAL awareness: ignoring committed
   WAL rows could falsely report an empty database. Include a committed-WAL
   regression case. Missing/partial schemas must remain untouched and retained.
3. Check application-table occupancy, not only sources and not only
   `SYNC_TABLES`: local `job_events` are retained history too. Fail closed on
   populated unknown ordinary tables. Use schema discovery with correctly
   quoted table identifiers and small `SELECT 1 ... LIMIT 1` probes.
   Exempt only exact infrastructure needed by a freshly initialized empty DB.
   Fresh `db.init_db` empirically creates populated `schema_version`, and the
   `search_documents_fts[_tri]` data/config shadow tables even with zero rows.
   These cannot be treated as user history; logical FTS tables must still be
   empty. Prefer reliable virtual/shadow classification if available, with a
   narrowly documented compatible fallback rather than ignoring arbitrary
   table-name prefixes. SQLite sequence counters alone are not retained rows.
4. Account for unknown files before recursively declaring the whole namespace
   disposable. Preserve unexpected content; do not invent an expiry for cache
   log/history files while claiming this is only a DB-emptiness repair. If this
   needs a broader file taxonomy, make that an explicit follow-up instead of
   silently expanding the deletion contract.
5. Revalidate immediately before deletion and compare the planned namespace
   filesystem identity with the current identity. Skip changed candidates and
   count only actual removals. This closes the concrete confirmation-window
   hazard. State honestly that checks alone do not provide an atomic lock
   against an uncooperative process writing between the final check and rmtree;
   do not claim absolute race freedom without a shared lifecycle protocol.
6. Update English USER_GUIDE first and its Korean translation, and every other
   current guide/spec that claims a zero-sources proof. Correct the nearby GC
   mtime-checkpoint explanation to imported export IDs, while retaining its
   essential statement that no fleet acknowledgement exists.

### Required tests and release gates

- A current zero-source database containing a tombstone is retained unchanged.
- Parameterized representative source-independent diagnostic/history tables are
  retained; unknown populated tables cannot evade the proof.
- A partial/unrecognized SQLite schema is retained byte-for-byte, with exactly
  the same schema afterwards. Inspecting valid candidates does not migrate or
  stamp them. Include WAL-held durable rows and read failures.
- A freshly initialized genuinely empty fixture remains reclaimable: safety
  must not turn the existing collector into a universal no-op.
- A root recreated after planning, newly inserted source/history row, modified
  marker, replaced namespace, and symlink redirection all prevent removal.
- Existing offline-volume, missing-marker, corrupt-database, confirmation and
  CLI JSON tests remain green. Add a CLI case proving refresh affects reported
  removals when eligibility changes at confirmation.
- Run repository pytest/ruff/mypy, vitest and plugin tsc gates, documentation
  checks and the required review skill before release. This patch changes no
  schema/config/API; synchronize the patch version in all manifests/changelog.
  Do not run production GC as part of validation.

### Remaining product decisions and explicit non-goals

DB/session tombstone expiry remains technically unsafe: any age default admits
an offline-peer resurrection counterexample. A finite window requires a
membership/acknowledgement/recovery protocol and a policy for obsolete device
snapshots; this is its own stored-contract plan, not a cleanup parameter.

Full active-session replay and image thumbnails remain intact. User-chosen
session windows and opt-in unreferenced prompt caps are already implemented.
Choosing job-event/query/compiler-history windows trades historical capability
for disk; record concrete present consumers before offering any options. Do
not label “keep” as a completed finite-retention feature or invent a 30/90-day
policy from the old roadmap proposal.

Do not delete sync snapshots, model downloads, or broad `.cache` temp paths.
The snapshots are complete recovery copies, not append-only log debris. No
compression/transport change is needed to repair this defect.

## 2. Pros & Cons

The patch directly repairs the collector's advertised preservation contract and
uses isolated counterexamples instead of old vault size estimates. It preserves
the supported empty-temp-cache collection capability and does not select policy
on the user's behalf. It can remain a backward-compatible patch release.

Conservative inspection can retain caches it cannot prove empty, including old
or partial databases and namespaces with unexplained content. That is the
existing “provably debris” contract applied correctly. The final-check race
cannot be eliminated by a second stat alone; a larger shared writer/lifecycle
lock would need separate design if adversarial concurrent writers are in scope.
The rest of B1/B2 remains active pending explicit history policy and a future
peer-safety protocol; this patch is not permission to claim the queue complete.
