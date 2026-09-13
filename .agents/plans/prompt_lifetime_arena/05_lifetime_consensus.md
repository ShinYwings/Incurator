# Closed Local Lifetime and Fleet Contract

Date: 2026-09-14 | Synthesis: lifetime/fleet closer

This closes the implementation choices from `01_proposal_producers.md`,
`02_fleet_design_extension.md`, and their independent critiques. It incorporates
the user's saved-chat ownership decision. It is a design record; no application
code or production data was changed. Session persistence and response transport
are specified by the parallel session/handoff closure records.

## 1. Small schema and one prompt evidence representation

The lifetime release uses schema 15 and a minor product version. Its local/fleet
core needs three additions, beyond the session records identified separately:

1. `prompt_run_owners(owner_id TEXT, trace_id TEXT, db_binding TEXT,
   PRIMARY KEY(owner_id, trace_id))`, with a trace index. `db_binding` identifies
   the canonical DB path and file identity when the owner was registered. This
   relation is local only and never a sync table. Pins are not user history.
2. `prompt_retention_marks(trace_id TEXT PRIMARY KEY, evicted_at TEXT NOT NULL)`
   is synced. Merge the maximum validated UTC timestamp. It contains only
   revisable retention intent; it never shares a key or overwrite path with an
   ordinary `deleted_records` tombstone. One marker per trace suffices because
   trace identity is never reused and every marker has the same predicate.
3. `prompt_runs.provenance_json TEXT NOT NULL` preserves capture observations
   for source arrays. It is versioned JSON, validated by one shared backend
   codec. Existing trace columns remain present and available to their current
   consumers; the new field is additive and transported with every full row.

The evidence capsule is the complete decoded prompt row, including all existing
columns and this provenance field. There is no second chat-specific reduced
trace model, source-text archive, raw response archive or shared blob store.

Each provenance capture observation contains a capture ID, its DB namespace,
the recorded ordered `source_ids` and `source_span_ids` arrays, and a positional
source identity list containing the known source `sync_key` or explicit
unresolved status. Preserve duplicates and array order. Missing historical span
IDs remain recorded IDs. Do not embed source text or require deleted source/span
rows to reappear. A capture says where these values were observed; it does not
invent where a pre-v15 run originally happened.

New runs capture once in the run-creation transaction. A quiescent v14 adoption
captures each extant row once. Normal export/import forwards the capture bytes;
it does not create another observation on every hop. Two devices independently
adopting the same v14 trace can have different honest observations. Merge those
by capture ID as a sorted deduplicated set; conflicting bytes under one capture
ID are invalid. Different capture namespaces alone are not conflicting prompt
inputs. The set grows only when independent legacy observations actually exist,
not with every save or sync. This small, explicit legacy exception avoids either
inventing original provenance or rejecting valid migrated peers.

Operational `source_ids`/`source_span_ids` may follow existing identity-remapping
rules for current local consumers. The immutable captured arrays preserve values
that cannot map, so an origin integer never silently aliases an unrelated local
source. Trace APIs expose captured values and resolution status alongside their
current local projection. Partial prompt exports carry source identity metadata
inside provenance; they need not resurrect source documents to convey identity.
Any current live identity mapping used by the canonical remapper must be carried
as its existing source dependency or resolved from the capsule's `sync_key`.

Do not introduce span-list deduplication in this release. The additive capture
can increase storage, especially for large span arrays. Measure the private
rehearsal output and document this cost; the previously measured lossless
deduplication opportunity remains a separate release.

## 2. Exact producer lifetime

Introduce an explicit `PromptLifetime` context object in a small dedicated
module. It owns a UUID token, creating and locking its file before exposing the
scope. Nested helpers borrow the same object. A thread/context convenience may
only forward that explicit owner and must never silently create an unowned run.

The scope boundaries are fixed by the actual publishers:

- `compile_source_l2`: through all recursive L2 siblings, optional graph staging,
  `_persist_units`, `persist_graph_data` and final generation commit/unwinding.
- report/synthesis generation: through every report/node commit/unwinding.
- `QueryOrchestrator.run`: through successful or failed QTR publication,
  including the failure-path trace lookup.
- MCP feedback handler: through classification, action planning and possible
  candidate insertion. Plugin/CLI feedback additionally transfers evidence at
  its response boundary according to the handoff protocol.
- query derivation: through result/fallback disposition. Bare external response
  IDs do not themselves become indefinite durable owners.

Every `run_prompt` requires the owning scope. Run creation and its pin insert
share one DB transaction before the provider is called. The scope tracks every
started run, including failed parents and recursive siblings. Completion checks
that its owned row exists, updates audit fields, and does not release ownership.
No SQLite writer transaction lasts across a provider call or arbitrary caller
work. All reference-publishing helpers validate required prompt rows in the same
write transaction as their artifact insertion; use their existing optional
connection form instead of opening an independent publication connection.

On final committed publication or actual abandonment, remove only this owner's
pins in a short transaction, then release its token. Durable artifact/session
references protect surviving evidence independently. Do not release at a nested
runner return, model completion, last-trace return value or first sibling write.

## 3. Process token implementation and recovery

Use a dedicated non-synced token directory under repository/cache runtime state,
with canonical DB-path hash subdirectories and fresh UUID token names. Avoid
system temporary directories. Files are created exclusively and never reused.
Each contains at least one byte, allowing byte-range locking on Windows.

- POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on the unique file descriptor.
- Windows: seek to byte zero then `msvcrt.locking(fd, LK_NBLCK, 1)`; hold the
  open handle through lifetime. Unlock only the owned byte after DB cleanup.
- Use non-inheritable descriptors. An `os.register_at_fork` child hook closes
  inherited handles without calling `LOCK_UN`, which could unlock the parent's
  shared open-file lock. Every scope operation checks its originating PID and
  refuses use by a child. Do not rely on PID reuse or heartbeat age for liveness.

The reaper opens existing token files without create, attempts the nonblocking
exclusive lock and proceeds only on success. Under that lock and
`BEGIN IMMEDIATE`, it rechecks the owner's registered DB binding and removes
only those owner rows. It then performs the reference-aware cap in the same
transaction. Missing token, unexpected file type, unreadable file or binding
mismatch preserves the affected pins and reports recovery needs. None proves
abandonment. No global token serializes providers or prevents useful reclamation
of unrelated runs.

Bind each owner to the resolved DB path plus available file device/inode
identity. A copied/replaced database cannot borrow the old runtime's ownership
proof accidentally. Explicit recovery of a relocated backup must classify and
rebind local metadata on a quiescent copy; ordinary import never transfers it.
Scope operations revalidate binding so an old owner cannot keep publishing into
a replacement database under a former token.

After reservation removal commits, the UUID token has no future owner and may
be unlinked. Windows may require closing first; that is safe because no owner
row remains and no future producer reuses the name. Competing reapers always
recheck rows after locking. Cleanup-transaction failure leaves the file/rows for
the exact same reaper protocol after handle release. Token files without owner
rows are small local housekeeping, not grounds to delete retained user data.

## 4. Local GC and ordinary deletion boundary

One strict reference decoder serves GC, export closure, import validation and
session ownership. Include all nine current scalar columns, strict string-array
QTR references, accepted saved-session links and active producer pins. Malformed
ownership is an actionable failure for destructive prompt GC, not an empty set.

Acquire `BEGIN IMMEDIATE` before deriving the eligible set and deleting it.
Choose newest N by the existing `created_at DESC, trace_id DESC` order among
unreferenced, unowned rows. Delete each candidate and upsert its separate
retention mark in that transaction. Do not write an ordinary prompt tombstone.
Read-only preview keeps unknown/stale pins protected and reports conservative
eligibility; apply reports actual committed deletions after reaping/recomputation.

Retained owners may exceed N indefinitely; active producers may exceed it while
running. This is an unreferenced-history cap, not a total row or byte cap.
Deleting rows does not promise immediate SQLite file shrinkage.

Existing ordinary and legacy-ambiguous prompt tombstones retain their existing
precedence. A chat capsule cannot clear deliberate deletion. Diagnose an ordinary
deletion conflict explicitly rather than silently report restored diagnostics.
Local producer protection and delayed-owner restoration defeat retention-only
eviction, not a separate deliberately authored deletion authority.

## 5. Canonical import ordering and lifecycle merge

Use one canonical import transaction with `BEGIN IMMEDIATE`. Materialize and
validate incoming prompt evidence/retention marks, then run the existing source,
artifact LWW, ordinary-deletion and generation-reconciliation logic. Reuse that
logic; do not build a second approximate winner calculator. Defer prompt
retention application and final prompt acceptance until the final owner set is
known. A superseded/deleted incoming report is not an owner merely because its
raw JSON names a trace.

A surviving owner or local producer pin protects a present prompt from retention
marks. A newly accepted owner may restore a missing prompt only from complete,
compatible incoming evidence or an accepted saved-session capsule, and only if
ordinary deletion permits it. Ownerless rows covered by a retention mark stay
suppressed. Keep the mark after restoration so later stale ownerless snapshots
cannot resurrect the run after its last owner ends.

Validate closure for newly accepted/changed owners before commit. Missing full
evidence rolls back the import with exact owner and trace identities. Existing
historical damage is reported separately, so one unchanged old dangling row
does not permanently prevent unrelated imports. Do not fabricate a PTR row from
an ID or hash, ignore a late import error, or publish partially accepted owners.

Prompt identity fields are immutable: trace ID, prompt contract/version, family,
role, input hash, curate-spec hash, query identity and creation time. Captured
source provenance is validated as above. Completion fields include output hash,
validation result/errors, retry count, latency, actual provider/model and
`finished_at`. A completed row wins over an otherwise compatible pending row;
pending can never regress completion. Two different completed versions under
one trace ID are a conflict, not arbitrary LWW; legitimate execution completes
once. Equal completed evidence is idempotent. A native capture ID with divergent
values is invalid, while distinct honest legacy capture observations may merge.

Exports start one consistent SQLite read transaction before choosing owners and
rows. `tables` and `--since` selections automatically include complete required
prompt rows regardless of their creation cutoff, without exporting unrelated
prompt history. The same codec serves full export and session capsules. Preserve
temporary-file plus atomic-replace publication, leaving the last valid export
untouched when closure validation fails.

## 6. Saved-session integration constraints

Agree with a complete capsule embedded in the accepted whole-session revision;
the DB owner index is a mirror. A session arriving after local eviction restores
its own required diagnostics. Source/runtime sidecars alone do not supply this
property because sync may deliver them independently.

The smallest feasible writer design should retain existing `sessions.json`
when the parallel session review establishes its ownership and conflict rules.
Backend prune requests must not compete by rewriting the file. If requests are
deferred to the plugin writer, report them as pending requests until an actual
deletion commits; do not report request submission as deleted chats. Accept
whole-session capsules only from the canonical winner, with deterministic tie
fixtures shared by Python and TypeScript. A losing revision's capsule cannot
independently acquire permanent ownership.

Eager response owners need exact session/turn/result identity. A later session
snapshot missing a link cannot release an in-flight result that may still be
saved. The handoff protocol must supply a committed consumed/abandoned turn
decision or a terminal session tombstone. Missing files, absent links in an old
revision, provider completion and elapsed time are not such decisions. A saved
capsule is genuine recoverable chat data; a pin to a response nobody can recover
is not. This boundary is the parallel handoff review's concrete implementation
gate, not a reason to weaken the user's selected preservation behavior.

## 7. Finite verification and rollout

Required schedules are already enumerated in the proposals; implement one
targeted regression suite covering: live provider; completed-unpublished run;
recursive sibling; graph staging failure; failed-QTR publication; process death;
fork; two reapers; cleanup DB failure; relocated DB; both retention/owner import
orders; stale/losing/deleted owner; ordinary deletion conflict; partial export;
pending/completed convergence; conflicting evidence; unresolved historical
provenance; and actual resume behavior. Session/handoff tests add their real
provider routes and writer crash schedules. Use disposable DBs/files throughout.

The v0.82.7 future-schema guard is a useful independent prerequisite, reviewed
in `06_schema_guard_review.md`. It cannot fence older installed binaries until
they upgrade. Schema15 production adoption must quiesce old writers, preserve a
coherent backup and rehearse all DB/session conversion on a private copy before
requesting authorization for the actual migration. Offline peer databases can
upgrade separately; exact-version transport defers their incompatible exports.
Preserve legacy ordinary tombstones and historical missing-evidence reports.
No production adoption, deletion or reindex is authorized by this design record.
