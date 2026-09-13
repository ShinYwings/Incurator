# Retention Cross-Critique of the Fleet Extension
Date: 2026-09-13 | Reviewer: Retention Capability / Storage

## Accepted design direction

The extension correctly selects accepted-final-owner closure, keeps revisable
retention markers distinct from ordinary deletion, and preserves those markers
after restoration to suppress stale unowned copies. The existing cap excludes
arbitrarily many references already; restoration of a valid offline owner does
not inherently reduce that capability. No irreversible-erasure demand has been
established and no product escalation is needed just to change the stored
contract. Lossless list deduplication remains a separate optimization.

Computing closure from the canonical staged merge, including reconciliation,
is essential. Raw incoming owner IDs would let a superseded report defeat the
cap even though no surviving artifact needs its run. Temporary import staging
must also use the proposed lifecycle merge so a pending copy cannot overwrite
a completed trace merely because current LWW keys use `created_at`.

## Confirmed missing-parent case: closure cannot assume intact source history

Independent `mode=ro` / `query_only` production scan on 2026-09-13 found:

| Historical prompt provenance | All prompt rows | Currently DB-referenced rows |
|---|---:|---:|
| Contains span IDs absent from `source_spans` | 184 | 48 |
| Contains source IDs absent from `sources` | 120 | 4 |

There are 2,053 distinct absent span IDs and two distinct absent source IDs.
Only counts were emitted. These are existing unresolved historical references,
not an allegation that this session deleted anything. The reference subset uses
the current GC registry; active producers and external text are outside it.

Consequently, “include all existing parent rows and reject missing parents”
would block exporting some retained traces on the actual vault immediately.
The extension already mentions this concern, but the master plan must resolve
it concretely before claiming full evidence preservation:

- Distinguish an intact trace whose historical source/span was removed from a
  newly malformed trace or export that omitted a still-existing dependency.
- Preserve existing unresolved span IDs as historical audit evidence without
  recreating source/span rows or falsely claiming their content exists.
- A missing numeric source ID cannot safely be copied into a destination's
  local integer namespace: the same number can name an unrelated live source.
  Preserve the original value with explicit originating namespace/unresolved
  provenance, or another equally lossless representation; do not silently drop
  it, invent a canonical source key, or claim it resolves locally.
- Already missing source content cannot be reconstructed. “Full trace
  preservation” means preserving the recorded evidence and its honest missing
  status, not manufacturing missing source text or reverse-hashing output.

The bounded recommendation is an immutable ordered provenance envelope in the
new prompt-lifetime contract, alongside operational references. For a resolvable
source, preserve portable `sync_key` identity and the recorded local integer;
for an already unresolved source, preserve a token containing a durable
**capture namespace**, the original integer and its list position. Preserve
unresolved span IDs and their positions similarly. Decoded trace inspection
must expose these original values and their unresolved status; operational
source links contain only identities that actually resolve. Never reinterpret
an unresolved integer in the importing database's namespace.

“Capture namespace” is deliberate: migration cannot know the original producer
device of every historic prompt. It identifies the database adoption event that
captured this evidence, not an invented historical origin. Generate/persist it
once in the private migration rehearsal and then in the separately authorized
real migration, carry it unchanged through snapshots/restoration, and do not
derive it from a filesystem path, mutable device display name or the current
exporting peer. New records capture portable source identity when available at
creation. Envelope ordering preserves duplicate list elements. No token by
itself proves that a source existed or was deliberately deleted: report missing
versus known-tombstoned honestly from available evidence.

Legacy copies of the same trace on two peers may receive different capture
namespaces during independent upgrade. Merge identical unresolved raw evidence
as multiple capture attestations, or a comparably lossless deterministic form;
do not classify different capture namespaces alone as contradictory prompt
inputs. Incompatible original values remain a conflict requiring recovery.
This is bounded engineering work within the full-trace transport contract and
must be specified/tested before implementation, not hidden under the existing
integer-array remapper. If the synthesis instead drops those original values,
that is the actual capability reduction and requires the user to choose it.

## Registered owners versus external transcript links

See the proposal's added external ownership section. The plugin correction
command can return `traceId` without recording a candidate. Chat tool-result
display can also persist PTR IDs in transcript content, which is stored outside
the DB registry. The extension's accepted-owner algebra must define the owner
universe precisely. Returning a diagnostic may legitimately publish an unowned
run subject to the cap, but “all artifacts” is too broad if the implementation
protects only registered rows. Preserving chat replay does not by itself
guarantee dereferencing every historical diagnostic link forever.

Do not try to repair this by scanning arbitrary strings: scans cannot prove
absence of an in-flight external writer or disconnected peer. If retained
sessions themselves are intended protective owners, register that relationship
as part of their durable publication and transport closure. This may couple to
the pending session-writer design; do not claim that coupling has been solved by
the SQL owner registry alone.

## Old local client reopening

The extension accurately distinguishes transport mismatch rejection from an old
binary opening the same local file. Upgraded code can refuse future schemas
before mutating them, but cannot retroactively change an already-installed old
binary's unconditional stamping behavior. A rollout must quiesce and replace
known old writers, document downgrade refusal and test the old binary on a
disposable copy. A compatible minimum-version marker read only by new code is
not protection against old code that ignores it.

This is an operational migration constraint, not a reason to remove offline
capability. An offline peer on its own old database can continue working and
upgrade/re-export later. Claims of transparent mixed-version synchronization or
safe arbitrary old-binary shared-file access would exceed the evidence.

## Conclusion for synthesis

Proceed with the recoverable-retention engineering design only after resolving
the two explicit boundaries: historical unresolved provenance and the durable
owner universe. Both are concrete design work; neither currently proves an
unavoidable user-level fork. Add the measured missing-parent cases, pending-to-
completed merge and external diagnostic publication paths to verification.
