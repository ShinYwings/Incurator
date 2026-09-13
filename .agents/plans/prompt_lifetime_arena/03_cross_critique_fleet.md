# Fleet Cross-Critique of Producer and Retention Proposals

Date: 2026-09-13 | Independent distributed-state reviewer

Reviewed `01_proposal_producers.md` and `01_proposal_retention.md` against the
fleet reproduction and `02_fleet_design_extension.md`. This is design review;
no implementation, live migration, or production deletion was performed.

## Conclusion

Proceed to a bounded master plan for one versioned prompt-lifetime contract:
explicit local producer reservations, per-owner process-lifetime tokens,
separate retention markers, accepted-owner-backed prompt restoration, and
partial-export prompt closure. The proposals preserve the requested useful cap
and retained prompt evidence. They do not establish a product trade requiring
the user to choose between permanent erasure and offline history. Permanent
erasure was not requested as an independent guarantee.

Actual production migration remains a user-authorized operational boundary.
Implementation and disposable rehearsal can proceed before that boundary.
Quiescing/upgrading old writers is a rollout requirement, not an alternative
retention product design or a reason for another open-ended Arena.

## Producer proposal: accepted with concrete test obligations

The proposed per-owner lock is substantially different from holding one global
lock through provider latency. Independent producers continue, GC can reclaim
other eligible records, and paused owners do not falsely expire. This avoids
the useful-reclamation loss of a global lock that continuous provider work can
starve. Durable reservations make the affected set observable in the same DB
transaction as GC. Process tokens supply the exact abandonment witness missing
from timestamps and job status.

Outer scopes explicitly cover L2 recursive sibling traces, unpersisted graph
results after staging failure, query error recovery before its final reference
write, and MCP classification before candidate publication. I found no omitted
producer path in the presented call-site inventory. Do not optimize scope
release per batch in the first release; that expands the proof unnecessarily.

The existing `durable_io.locked_path` is not sufficient: it has no nonblocking
probe, uses a normally cleaned temporary directory, and degrades to an in-process
lock on Windows. A small dedicated per-owner primitive can use platform kernel
locking, with actual subprocess tests. Correct lock inode/path ownership and
non-inheritance are implementation requirements, not a reason to replace the
design with membership/acknowledgement waits. Unknown or lost token state must
stop reclamation of affected pins and report repair needs.

In addition to the producer's proposed schedules, test two competing reapers,
owner cleanup racing a reaper, a failed cleanup transaction followed by process
exit, cancellation while nested callers unwind, and a cache-copy database whose
owner rows refer to another runtime's tokens. The reaper must never delete a
token file before the associated reservation removal commits. A caller cannot
continue publishing under a released or stolen owner token.

The migration begins with no old producer scopes only after old writers are
stopped or drained. After that proof, legacy pending rows need no invented
permanent pin solely because their validator status is pending. Existing staged
artifact references still protect recoverable work. The normal cap can govern
the remaining ownerless legacy history once actually authorized; no migration
itself needs to delete it.

## Retention proposal: correct separation of capabilities

The field audit supports preserving the entire prompt record. Its measured
lossless span-list deduplication opportunity is valuable, but it neither fixes
lifetime nor substitutes for an ownerless row cap. Keep it in a later separate
storage release; including deduplication now adds another migration, reference
namespace, and closure rule with no safety benefit to this fix.

The proposal correctly rejects dropping source/span diagnostics or preserving
all successful rows as silent substitutes. It also correctly refuses to infer
irrevocable fleet erasure as a user requirement from the existing cap wording.
Preservation of delayed referenced runs is the existing promise made complete.

## Correction to this reviewer's earlier closure language

The phrase “source/span dependency closure” in the fleet extension is too broad
if interpreted as requiring every historically named source/span row to exist
or be reintroduced. Parent reports that actual retained prompt rows contain
unresolved historical source/span references. Those references must not make
every new export fail or cause ordinary-deleted source data to resurrect.

Separate these two obligations explicitly:

1. **Prompt restoration closure:** an accepted retained owner requires its real,
   complete prompt record. Missing prompt evidence cannot be fabricated. This
   is the new retention safety invariant.
2. **Portable provenance handling:** currently resolvable source integer IDs
   need the existing source identity translation; stable span IDs can remain
   historical references even when their target rows no longer exist. Prompt
   restoration does not give permission to restore ordinarily deleted source
   or span rows. Known live source mappings needed by a partial export should
   accompany it, but unresolved legacy provenance must be treated under an
   explicit existing-history policy, not erased merely to satisfy validation.

The master plan must inspect and preserve the existing provenance contract for
unresolved source integer IDs. Merely including all prompt columns does not
prevent `_translate_source_id_arrays` from dropping unmapped IDs; conversely,
copying another device's numeric IDs verbatim can alias unrelated local sources.
Do not promise exact raw integer-array equality across devices where IDs are
already machine-local. Test semantic preservation for resolvable identities,
stable preservation for historic span IDs, and the existing explicit reporting
behavior for unresolved source identities. If changing that pre-existing
behavior is needed, scope and document it explicitly rather than quietly
expanding this lifetime release into source-history reconstruction.

None of this permits weakening the core check from a complete prompt record to
an invented ID/hash skeleton. It narrows what completeness means: complete real
prompt evidence, not restoration of the entire historical source corpus.

## Rollout: smallest complete boundary

Use the existing exact schema-version transport gate for old/new peer separation;
no membership system is required. Offline old peers may continue working on
their own old databases until upgraded, while cross-version imports defer.
Retain old snapshots and provide the rehearsed compatible re-export/conversion
path. New retention events must never be down-converted to ordinary tombstones.

Old binaries unconditionally stamp their own schema version when opening an
existing DB. A future-version check added only to new code cannot stop them.
Thus the actual production upgrade must quiesce all writers of that particular
DB before migration, upgrade the corresponding service/backend/plugin, and
prevent old code from reopening that file. Independent offline peer DBs do not
need to acknowledge a globally final deletion before local useful GC works.

Two-stage deployment of a future-version refusal may improve subsequent rollout
safety, but is not retroactive protection against unupgraded binaries. Do not
claim a universal on-disk downgrade fence without demonstrating it against the
old runtime. The bounded supported rollout is coordinated local-writer upgrade,
with backup, private-copy rehearsal, and user authorization for the real data
migration. That is the concrete stop if reached; do not ask the user to approve
schema design merely because a schema is involved.

Local read-only checks found no prompt tombstones or dangling scalar owners,
which supports clean local adoption. They do not establish the state of absent
peers or archives. Preserve legacy ambiguous tombstones as ordinary deletions;
repair any actual pre-existing missing prompt evidence only from intact known
evidence through an authorized recovery operation.
