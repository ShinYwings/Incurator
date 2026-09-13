# Session Producer Design: A Saved Chat Owns Its Complete Prompt Evidence

Date: 2026-09-13 | Producer lifecycle follow-up after explicit user decision

User decision: **"Protect saved chat links too; retain diagnostics while those
chats exist"**. This supersedes the earlier pending/DB-only scope. No application
or live data changes were made for this proposal.

## Actual writer and consumer boundaries

`plugin/src/utils/sessionStore.ts` uses a per-adapter `WeakMap` promise queue,
then `adapter.process` to merge a fresh file read with a local snapshot. Those
are useful plugin-local safeguards, but they do not coordinate with Python.
The initially missing-file path uses an independent temporary write/rename.
`backend/src/curator/gc.py:456–493` independently reads sessions, selects old
ones, writes `deletedSessionIds`, and atomically replaces the entire file. It
does not use the plugin adapter queue or a shared interprocess writer protocol.
A plugin process can therefore publish the state it read before backend prune,
overwriting the new deletion markers, and backend prune can similarly overwrite
newly saved messages. Adding DB prompt owners after either file write does not
close that race.

`main.ts:1720–1758` coalesces full session snapshots and replaces in-memory
`sessionData` with the merged result. `ChatSidebarView.ts:4774–4791` independently
holds active view messages and persists them into the session selected by
`sessionData.activeChatSessionId`. After a remote/backend delete changes the
selected session, old view messages must never be copied into the newly
selected session. A save needs the view's explicit session ID and observed
revision, with a tombstone conflict result that makes the view reconcile.

`ChatMessage` has no structured prompt-evidence field (`types.ts:325–352`).
`messageUtils.ts:241–263` retains query trace IDs in displayed results but
truncates other tool results; `LLMClient.ts:1966–1986` appends the formatted
text to the transcript. Ownership metadata must be captured from structured
results before formatting/truncation. Deriving ownership solely from the final
display string misses saved links, and a GC-time regex scan cannot repair a
run deleted during the provider-to-save interval.

## Recommendation: make the durable session commit self-contained

There is no atomic transaction between SQLite and the Obsidian adapter. The
complete design must use a recoverable commit record carrying both the saved
chat and its required prompt evidence. The narrowest defensible invariant is:

> A committed session revision contains the complete replayable session and
> the portable prompt-evidence closure for its protected trace IDs. A DB
> session-owner index is derived from accepted committed revisions. Losing or
> delaying that index cannot destroy the only recoverable prompt payload.

This also preserves offline plugin saves if a backend service is unavailable.
Do not quietly make all chat saving dependent on a live Python/MCP process just
to acquire a lock. A lock helper alone cannot solve loss of its process while
the plugin still owns an unpublished result, or the independent sync writer.

I recommend immutable, versioned **session commit bundles** in a synced
session-state namespace, plus `.curator/sessions.json` as a compatible materialized
view. This is more work than adding one owner table, but it removes the false
atomicity promise and does not hold a lock across streaming, user pauses, or
provider latency. It is the same stored prompt-lifetime release, not a separate
claim that session coordination can be postponed.

Each bundle has a unique operation ID, session ID, parent/observed revision,
deterministic revision key, full sanitized session content, explicit structured
trace IDs, and complete portable evidence capsules for the session's protected
IDs. A deletion commit instead contains the session ID and a terminal deletion
marker. Full message content and thumbnails are preserved. The producer/fleet
proposal defines the capsule fields, source identity handling, and prompt
completion rules; do not invent a second reduced representation here.

Bundle writes use an exclusive temporary file and atomic rename to an immutable
operation path. A reader ignores temporary/uncommitted names and validates the
bundle digest/schema before accepting it. Two devices/processes write distinct
paths, so they do not overwrite each other's durable commits. Syncthing can
transport bundles in arbitrary order without requiring SQLite and file arrival
to be atomic. Unknown/incomplete bundles are preserved and reported, never
treated as empty owner sets.

The existing session merge chooses whole-session winners by updated time, then
message count. Preserve that whole-session conflict policy, adding a deterministic
operation-ID tie breaker so replicas agree. A terminal session deletion outranks
every old/new revision for that session ID, as existing `deletedSessionIds`
already does; a new chat uses a new ID. Do not turn this retention fix into
message-level CRDT semantics or silently merge incompatible assistant streams.

## Exact producer → saved revision → DB owner choreography

### New trace-bearing tool/CLI responses

1. The ordinary local producer scope starts and protects every run through
   provider completion and the caller's durable artifact publication.
2. At a trace-bearing response boundary, capture the full **portable diagnostic
   capsule** while the run is still protected. Serialize it as structured
   metadata, not visible transcript prose. Keep the scope until response
   serialization/handoff is complete. A self-contained serialized result is
   recoverable even if local retention later evicts the unowned DB copy.
3. The plugin's result parser attaches capsule metadata to the actual message
   object before truncating/formating its human-readable text. Coalesced saves
   snapshot that metadata with message content. An in-memory message owns its
   capsule bytes; it does not need an OS lock across every UI pause.
4. Saving writes the full immutable session bundle first. This is the durable
   commit, and the save promise resolves only after that commit succeeds. If
   a backend is available, it can consume/index the bundle immediately, but
   its availability does not decide whether chat bytes were saved.
5. The backend reconciles accepted session commits before destructive prompt
   GC, before applying prompt-retention imports, and before serving a prompt
   lookup that may require restored chat evidence. In a DB write transaction,
   it installs the accepted session owner/index and restores/protects required
   compatible prompt rows from capsules under the fleet retention rules.
6. Only after durable bundle commit may any temporary delivery reservation be
   released. Existing QTR or graph owners remain independent. No whole-row or
   reduced-field substitution is made: the registered chat owner resolves to
   the same complete diagnostic representation.

Because the durable payload travels with its owner, a GC pass racing a newly
arrived bundle cannot permanently erase its diagnostics. The pass may operate
on an earlier local owner snapshot; the accepted later bundle restores the
evicted row. This is the same revisable-retention ordering as a delayed peer
artifact, not a grace period. Once the bundle has been accepted into the DB
index, local reference-aware GC must exempt that row normally.

**Route coverage is a release gate.** Every integration that can place an
Incurator PTR link in chat must deliver this metadata or use a durable response
handoff identified by its turn/session. Some external provider processes expose
only formatted/truncated tool results; do not assume adding a response field
automatically reaches every `LLMClient` route. For such a route, the backend must
write a durable full response handoff/capsule before returning the ID, identified
by an explicitly propagated turn token. The plugin imports it into the saved
bundle, then acknowledges it. The handoff itself must carry enough session
message/result content to replay after a crash; an indefinitely pinned PTR
without recoverable publication is not a valid alternative.

Do not release unacknowledged response handoffs merely because a timer expired.
They are either consumed by an accepted session commit or explicitly abandoned
by a closed turn whose persisted session state has been reconciled. If the route
cannot expose a full capsule or support such a deterministic handoff, its design
is unfinished; do not silently weaken protection for that provider. Auditing the
actual provider adapter branches is required before the master plan calls this
step implementation-ready.

### Existing/manual links and missing evidence

When a user pastes a previously existing PTR link into a saved message, resolve
its capsule before committing the new protected reference, using the backend
trace API or already-known local committed bundle. If the prompt has already
been deleted with no recoverable copy, preserve the chat content and mark that
link explicitly unresolved; no implementation can manufacture historical
diagnostics. Report this as pre-existing unavailable evidence, not successful
full protection. This same issue exists during migration and is not solved by
permanently pinning an empty ID.

For newly produced links through supported routes, missing capsule metadata is
a contract failure and must be visible. Preserve user text in a durable pending
save record if resolution is temporarily unavailable; do not falsely label it
a fully indexed/protected save or discard the message. Complete resolution or
explicitly report the unrecoverable gap on resume. This is a recoverable state,
not an exception handler that invents successful diagnostics.

## Failure and retry schedules

- **Death before bundle rename:** the prior accepted saved session remains;
  the temporary file is not a commit. Any capsule not durably handed off is
  unsaved in-memory work, matching the existing process-crash boundary.
- **Death after rename, before DB owner install:** the bundle is a real saved
  chat and carries its own evidence. Startup, trace lookup, GC or sync import
  replays it idempotently. This is not a stale producer lock to reap.
- **Death after DB install, before sessions.json projection:** replaying the
  same operation is a no-op for DB rows and regenerates the view. Full replay
  and thumbnails remain in the bundle, so projection failure loses no chat.
- **DB index unavailable:** plugin saves self-contained bundles; the backend
  reports index/recovery failure and does no unsafe destructive GC. It does
  not rewrite a corrupt canonical file or claim that diagnostics were deleted.
- **Lost acknowledgement:** retry uses the same operation ID/digest. Equal
  content is idempotent; conflicting bytes under one immutable ID are a loud
  corruption/identity error.
- **Late older revision:** the deterministic retained winner/deletion witness
  rejects it. It cannot create new effective owners from an obsolete chat or
  restore arbitrary old unowned prompt rows.
- **Missing/invalid bundle file:** preserve existing indexed owners; do not
  infer chat deletion from filesystem absence. Only a valid deletion commit
  releases the session's ownership.

The protocol has no forever-held OS lock. Durable recoverable commits can
remain after process death because they represent **saved user data**, not
abandoned execution. Reconciliation is deterministic and idempotent.

## Session deletion, backend prune, and stale-view safety

Both plugin deletion and backend retention generate the same immutable terminal
session deletion commit. `gc.prune_sessions` must stop independently replacing
the monolithic file. It selects sessions from accepted committed session state,
then commits deletion markers through the shared session protocol. Its result
reports actual committed logical deletions separately from later file compaction
and SQLite freed pages.

The deletion commit is synced and joined by session ID. On reconciliation it
removes that session's DB owners; other sessions and QTR/artifact owners remain
protective. A response/save already in flight for a tombstoned session ID is
rejected as a deleted-session conflict. The plugin preserves the current draft
for explicit recovery into a **new** session ID and never writes those messages
under whichever different session happens to become active. This fixes the
actual stale-view redirection hazard without a global user-history window.

When the configured age-window prune races a newer save, evaluate the existing
retention contract against the accepted revision used for the prune. The
deletion commit must include that observed revision; reject/recompute if a
newer already-visible revision makes it ineligible. A truly concurrent offline
save remains subject to existing terminal session deletion semantics. Do not
claim an unseen peer's new activity can defeat a terminal deletion without
changing that current policy explicitly.

The monolithic `.curator/sessions.json` becomes a materialized compatibility
view, written only by the plugin's existing queue/adapter process after loading
accepted commits. Backend operations publish immutable authoritative commits
instead of competing to replace that view. Backend session reads and GC must
use committed state, so a stale view does not resurrect history. A later plugin
read/save refreshes the view and reconciles the selected session with its view
messages. Syncing the view can remain supported during transition, but new
clients must not let an obsolete view override accepted commits.

## Bounded storage and ownership release

The first implementation can store complete evidence once per retained session
bundle and deduplicate repeated PTR references within that bundle. A session
keeps the evidence for its saved links for that session's life; do not retain
every producer or every unrelated prompt forever. If the same trace is linked
from two sessions, deleting one does not release the other's ownership.

This is not a proposal to retain every historical full transcript revision.
Once a newer **self-contained accepted** bundle is durable, superseded bundles
may be compacted while retaining the winning revision/deletion witness needed
to reject late stale files. A disconnected peer can submit its own current
revision later and participate in the same whole-session merge policy; no
replayable message in the retained winning session depends on a removed bundle.
Active candidate/recovery bundles must not be removed before their disposition
is decided. Session deletion releases its full payloads after the durable
terminal deletion witness is installed. Tombstone/winner witness retention
still has the existing unbounded-offline acknowledgement limitation; do not
promise a fixed total byte cap.

The new bundle storage adds real overhead and duplicates the temporary
compatibility projection. Measure it on a private copy before claiming disk
savings. Lossless prompt span-list deduplication remains a separate optimization;
it cannot substitute for complete evidence in the session commit closure.

## Existing chat migration and rollout

Quiesce old session writers as well as old backend writers for the authorized
production migration. Preserve coherent copies of the old session file and DB.
On a private rehearsal copy:

1. Parse existing sessions with current fail-closed rules and retain all message
   bytes/fields/thumbnails and deletion IDs. Enumerate structured known trace
   fields and explicitly recognized legacy displayed PTR links once, recording
   where each link came from. This migration extractor is not the runtime GC
   authority and cannot silently claim arbitrary prose matching is exact.
2. Resolve each actual legacy link to its complete portable capsule. Preserve
   unresolved link IDs and report missing diagnostics/source identities rather
   than fabricating or dropping them. Existing deleted sources use the fleet
   historical-identity representation, not coincidentally matching local IDs.
3. Create self-contained initial session commits and terminal deletion commits,
   build DB session owners from them, and verify every existing resolvable saved
   link through the real trace API. Compare entire normalized message records,
   full replay and thumbnail content before/after.
4. Install matching backend/plugin versions and refuse old session contract
   writers. As with old DB binaries, a schema field cannot retrofit refusal
   into a previously installed writer. Do not leave old plugins editing the
   upgraded shared vault file; offline peers upgrade/re-export/convert their
   legacy session state before participating.
5. Keep legacy snapshots for an explicit conversion path. Do not relabel old
   files as new schema or infer that unseen peers have migrated. Production
   migration/deletion remains separately authorized by the user's data rule.

## Acceptance tests that establish the actual boundary

Use separate backend/plugin-process actors and isolated filesystem/DB state:

- Complete a prompt, save its capsule-containing chat while GC/import evicts
  the unindexed DB copy, then reconcile and assert exact diagnostic equality.
- Crash at every bundle write/rename/index/projection boundary; verify replay,
  idempotent operation IDs and no permanently held producer locks.
- Exercise every provider response adapter before formatting/truncation;
  verify saved correction-only traces receive protection as well as QTR paths.
- Save with backend unavailable using a complete capsule; restore backend and
  verify the indexed owner and trace. Do not use a test stub that always calls
  the live backend for what is claimed as an offline save.
- Delete/prune during an active stream and between queued coalesced snapshots;
  assert tombstones persist and old view messages never enter another session.
- Import owner bundle first/deletion first, late stale revision, duplicate
  bundle, changed immutable operation bytes, and both devices' concurrent
  revisions. Assert final accepted owners, complete message replay, and trace
  lookup results, not merely successful file writes.
- Delete one of two sessions linking the same trace; remove the final session
  and run the cap. Ensure reclamation resumes only after all genuine owners end.
- Rehearse old sessions, legacy missing evidence, deleted source identities,
  corrupted store, missing canonical view, mixed-version peers, and storage
  compaction without losing full retained session contents.

## Remaining implementation gate

This proposal is a complete durability shape, but the provider-route response
handoff audit must enumerate real metadata plumbing before code is authorized
as implementation-ready. Do not paper over that boundary with a lease timeout,
an assumption that an external tool result includes all fields, or permanent
pins on every diagnostic. The user's policy is resolved; this remaining work
is a concrete engineering obligation, not another product permission question.
