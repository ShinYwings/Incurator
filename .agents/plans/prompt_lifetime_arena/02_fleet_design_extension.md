# Fleet Design Extension: Owner-Backed Retention Restoration

Date: 2026-09-13 | Independent distributed-state design review

This extends `01_proposal_fleet.md`; its reproduction and initial alternatives
remain intact. No application code, live database, retention configuration, or
vault content was changed during this investigation.

## Recommendation and precise scope

A capability-preserving design is feasible without membership or acknowledgement
waits: separate **retention eviction** from ordinary deletion, carry complete
prompt evidence with exported surviving owners, and let a valid retained owner
protect or restore its evidence only across a retention eviction. Implement the
producer reservation lifecycle from the independent producer proposal in the
same versioned prompt-lifetime contract. These are coupled parts of one stored
invariant, not independently safe releases.

This preserves useful finite reclamation of locally unreferenced prompt rows,
delayed offline artifact publication, and full retained prompt inspection. It
does not promise irrevocable erasure of a run which a disconnected peer still
needs. The existing cap already excludes referenced runs and is not a bound on
total rows or bytes. Revisable retention therefore implements the intended cap
more faithfully than either permanently dropping offline evidence or retaining
all successful runs. No user-level choice is needed solely because the schema
and transport version must change.

The recommendation applies prospectively to the new contract. Existing missing
evidence cannot be reconstructed from hashes, and legacy ambiguous deletion
records must not be relabelled automatically.

## Actual deletion writers and why the marker must be distinct

Repository search finds one direct local `DELETE FROM prompt_runs` writer:
`backend/src/curator/gc.py:626`, immediately followed by the normal tombstone
writer. Source deletion in `db/sources.py` does not delete prompt runs; prompt
rows are not foreign-key children of sources. `prompting/trace.py` creates and
finishes records and contains no deletion. Generic deletion helpers remain
capable of deleting any supported sync table, and `_apply_tombstone` implements
ordinary imported deletion dynamically. There is consequently no basis to
reinterpret every prompt tombstone, including arbitrary supported imports, as
revisable retention.

Prefer a separate synced prompt-retention marker relation, keyed by trace ID
and carrying its eviction revision, over inserting `reason=retention` into the
same single tombstone slot. The latter needs a new non-LWW precedence algebra:
a later retention event must never replace and thereby weaken an earlier
ordinary deletion. Separate namespaces avoid that collision entirely. Ordinary
`deleted_records` retain their existing semantics; retention markers have only
the new, narrowly specified prompt-lifetime meaning.

Retain the retention marker when restoring a prompt. It continues to suppress
stale **unowned** copies from unrelated snapshots; clearing it would permit
those snapshots to resurrect reclaimed history once the protecting owner is
later removed. A new local cap may update the marker after the last owner is
gone. Metadata retention remains subject to the same existing lack of a fleet
acknowledgement floor; this proposal does not claim bounded tombstone metadata.

## Merge invariant and algorithm

For a trace ID, distinguish ordinary deletion, a retention marker, accepted
retained owners, and available complete prompt evidence. No wall-clock
comparison between an artifact creation timestamp and retention is needed to
give a delayed valid owner protection. The owner may correctly predate the
retention event that simply did not know about it.

1. Parse and validate the incoming snapshot before mutating canonical rows.
   Resolve ordinary tombstones, natural-key convergence, row LWW decisions, and
   owner retirement/replacement into the owners that will actually survive this
   import. An obsolete incoming report rejected by a newer local report or its
   ordinary deletion is not a valid excuse to restore a prompt.
2. Combine those surviving owners with surviving local owners and protected
   producer reservations. Derive prompt references through one shared explicit
   registry covering scalar IDs, JSON lists, and nonstandard reference columns.
   Preserve local-only staged owners such as `graph_batch_results` even though
   that table itself is absent from `SYNC_TABLES`.
3. Apply ordinary prompt deletion using its existing conflict semantics. A
   retention exception never clears an ordinary tombstone, advances a prompt's
   creation timestamp, or fabricates an explicit reinsert. If a retained owner
   needs evidence blocked by an ordinary tombstone, surface the conflict for
   recovery; do not secretly override the ordinary deletion.
4. Apply retention marks conditionally. A locally present prompt protected by a
   surviving owner/reservation remains. A missing prompt may be restored from
   a validated complete incoming row only when such an owner requires it. A
   stale unowned row is blocked by the retention mark.
5. Verify all newly accepted or changed owners have resolvable required prompt
   evidence. Commit owner changes, prompt changes, and marker changes in one
   transaction. Roll back the entire affected import on a missing or malformed
   required closure, with trace ID, owner identity, and a recoverable error.

The exact implementation may stage rows in a private database or a bounded
incoming-row representation. The existing importer already prescans for ID
convergence and does post-import generation reconciliation. Whatever mechanism
is selected must compute protection from the **accepted final owner state**,
including that reconciliation, rather than from raw incoming IDs. Do not build
a second loosely similar LWW implementation whose decisions can diverge from
the canonical merge. Reusing the canonical merge in a staged transaction is
preferable; the final reference closure is the decisive predicate.

Import file order must not alter this result. A retention-only file arriving
first can evict a locally unowned row, then a later owner-with-evidence bundle
restores it. Owner-with-evidence first protects the row against later retention.
An owner-only damaged file is not made safe by hoping a second file arrives
later: leave the canonical state unchanged, report missing evidence, and retry
the valid complete bundle when available.

## Export closure, including partial exports

`export_knowledge` currently exports exactly the requested tables and filters
each independently by `since`. `prompt_runs` ranks by `created_at`; a recent
report can reference a prompt older than the cutoff. Full exports are therefore
not evidence that either partial route is safe.

An export containing a prompt owner must automatically include its complete
required prompt rows even when `tables` omits `prompt_runs` or `since` omits
their old creation dates. This is a documented dependency closure, not a global
promotion of every restricted export to a full database dump. Selecting only
prompt runs still must not manufacture owners, and unowned prompt rows remain
blocked by retention markers on import.

All selected owners and their closure must be read from one SQLite snapshot.
Otherwise owner replacement or producer publication between two reads can
produce an internally inconsistent bundle. Writing already uses a temporary
file plus `os.replace`; preserve that atomic publish path and make validation
failure remove the temporary file without replacing the last valid snapshot.

The prompt row includes `source_ids` and `source_span_ids`, not just hashes.
Existing sync translates source integer IDs and may drop unresolved elements
of provenance arrays (`_translate_source_id_arrays`, `provenance_dropped`).
Calling a row "complete" before that translation does not ensure complete
retained inspection afterward. Required source identity/span dependencies must
be carried or resolved losslessly under the existing source deletion semantics.
Do not quietly empty provenance arrays to get a partial prompt closure accepted.
Precisely enumerate that transitive closure in the master plan; do not hide it
behind the phrase "include the prompt row." Existing legitimately deleted
source/span provenance needs an explicit representation under the existing
deletion contract, rather than accidental resurrection of deleted sources.

## Compatibility and migration boundary

Current schema is 14. Direct import rejects any unequal schema version
(`db_sync.py:1118`), and autosync skips unequal versions until a peer re-exports
(`db_sync.py:2764`). Bump the version for the entire prompt-lifetime contract.
Old and new peers must reject or defer each other's exports; do not provide a
down-conversion that converts revisable markers back to ordinary prompt deletes.
The new contract preserves offline work when the peer eventually upgrades and
exports valid closure. Mixed-version synchronization is temporarily unavailable,
as already required by the repository's exact-version transport contract.

An old runtime reopening a **new local database** is a separate hazard: current
`db/schema.py:_stamp_schema_version` unconditionally changes a mismatched stamp
to its own version, and `connect` executes schema setup before stamping. A new
version check alone cannot retrofit refusal into already installed old binaries.
The migration rollout must stop old writers before upgrade, require compatible
backend/plugin service versions, and prohibit reopening that database with old
code. Add refusal of future versions before schema mutations in the upgraded
runtime to avoid repeating this defect. Test with a disposable copy and an old
binary; do not claim transport header rejection solves shared-file downgrade.
If preventing arbitrary old executables from reopening the same writable file
is a requirement, that needs a separate concrete enforcement design; a version
number in the file cannot accomplish it by itself.

Legacy `deleted_records` rows have no origin. Even though the only direct local
writer found today is GC, historic imports or callers of the generic API can
have authored ordinary prompt deletion. Migrate these as legacy ordinary
tombstones, not retention marks. Existing prompt rows and intact owners can be
adopted; ambiguous already-deleted evidence needs authorized recovery from a
known intact peer/backup. A read-only count of prompt tombstones and dangling
owners determines whether this is an actual vault issue or only a historical
compatibility case. Do not infer prompt contents from an owner ID.

Historic v14 archives cannot simply have their headers edited to claim the new
contract. If archive recovery is required, rehearse an explicit offline
conversion against a private database copy, preserving legacy deletion meaning
and checking closure before offering an importable result. Actual production
migration/recovery still requires user authorization.

Parent's read-only check on 2026-09-13 found zero local prompt tombstones, zero
dangling references across all nine scalar owner columns, and zero malformed
query-trace JSON values. The local cap is unset. This supports a clean local
adoption rehearsal; it does not establish that offline peers or archives are
equally clean, or that valid JSON necessarily contains valid string IDs.

The production rollout must be a concrete separately authorized operation:
inventory known writers/peer versions; preserve a restorable coherent backup;
quiesce old writers on the database being upgraded; rehearse conversion on a
copy and validate owner/evidence closure; upgrade the corresponding backend and
plugin service; perform the authorized transaction; verify all retained rows,
references, and production configuration; then resume local work and publish a
new-version snapshot. A disconnected peer can keep its own old database and
work offline until it upgrades, but its exports are deferred across versions.
Do not let an old runtime write the upgraded database and do not pretend an
unknown offline peer acknowledged migration. Preserve old snapshots for an
explicit compatible conversion/re-export path. Before new writes, rollback can
restore the coherent backup; after new-contract writes, downgrade is a recovery
operation that must preserve those writes, not blindly restore yesterday's
database. This operational coordination is not a reason to replace recoverable
retention with an acknowledgement-dependent permanent-deletion design.

## Malformed and conflicted state

The current JSON reference scan silently skips invalid JSON and accepts broad
string coercions. That behavior is unsafe for a deletion authority: malformed
references must make destructive GC unavailable for the affected database,
with an actionable error. Do not interpret unreadable ownership as absence.
The same strict decoder should be used by GC, export closure and import checks.

Reject invalid retention tokens, timestamps, duplicate conflicting evidence,
missing required fields, and unknown ownership/marker variants at the contract
boundary. A duplicate prompt identity with incompatible immutable provenance
must not be accepted merely because both rows share `created_at`. Completion
updates to a legitimate pending record require explicit monotonic lifecycle
merge rules; the existing prompt LWW key ignores `finished_at`. Ownership
restoration must not accidentally restore the pending version over a completed
record or let a stale snapshot regress completion metadata.

Previously dangling local references must be diagnosed separately from newly
introduced ones. A blanket import rejection on any historical defect can halt
unrelated sync forever; the master plan must define targeted validation plus a
repair report, while keeping destructive GC fail-closed when it cannot prove
ownership. This is error recovery for pre-existing damage, not permission to
accept a new owner without evidence.

## Minimum release verification

- Run the original two-device reproduction in both import directions and both
  arrival orders, for a scalar report and JSON query-trace owner.
- Cover accepted owner versus superseded owner, an owner deleted in the same
  snapshot, ordinary tombstone plus newer retention marker, and protection by a
  local-only graph batch or live producer reservation.
- Verify restoring one owned row does not restore stale unowned rows from the
  same file; owner removal followed by GC can reclaim it again.
- Cover `tables=[community_reports]`, `--since`, full exports, missing prompts,
  missing source identity/span dependencies, unknown retention variants,
  malformed reference JSON, and rollback after late validation failure.
- Cover pending/completed evidence convergence, identical-ID conflicting
  provenance, stale owner snapshots, import retries, interrupted export, and
  resumability after restoration rather than only successful import counts.
- Rehearse clean v14 adoption, legacy prompt tombstones, damaged old archives,
  both cross-version transport directions, and old code against a disposable
  upgraded database. Verify production paths and settings remain unchanged.

## Remaining genuine fork, if any

Membership and acknowledgements become necessary only if the user requires
irreversible prompt erasure to be final before every offline peer has revealed
its references. Then immediate useful reclamation and preservation of arbitrary
offline referenced evidence cannot both be guaranteed without another durable
copy. No such finality requirement has been established here. Treat revisable
retention as the engineering default for the existing referenced-run promise.

The remaining design burden is concrete but significant: lossless prompt
provenance closure, accepted-owner merge ordering, and producer lifecycle. If a
minimal implementation drops any of those, it is not a complete fix. Escalate
only an actual unresolved capability choice, such as insisting on ordinary
deletion finality for historically ambiguous GC tombstones while also requiring
automatic recovery from them; do not escalate schema versioning itself.
