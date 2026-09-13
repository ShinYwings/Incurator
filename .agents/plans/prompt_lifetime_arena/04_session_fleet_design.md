# Session-Owned Full Diagnostics: Fleet Protocol Extension

Date: 2026-09-13 | Distributed-state design review

The user has selected the product behavior: saved chat trace links retain full
diagnostics for as long as their chats exist. This extends ownership beyond DB
artifacts. No code or live writes were performed for this proposal.

## Actual storage and writer contract

`plugin/main.ts:1638–1756` stores `.curator/sessions.json` through the Obsidian
vault adapter. It is synchronized independently from per-device DB exports.
Saving is available without a backend CLI/service: `saveSessionData` coalesces
snapshots and `writeSessionData` calls `writeMergedSessionStore` directly.

`plugin/src/utils/sessionStore.ts` serializes operations per adapter/path and
uses `adapter.process` to merge against current bytes for an existing file.
The missing-file route publishes through a temporary sibling/rename. Neither
the JavaScript queue nor `adapter.process` is a demonstrated interprocess lock
against Python GC or an external sync writer. Do not describe either as such.

`sessionData.ts:mergeSessionData` unions permanent `deletedSessionIds` and picks
one entire revision of each non-deleted session, ranked by `updatedAt`/creation
time and message count on a tie. It does not merge message histories. Deletion
always suppresses even a later stale in-memory revision of that session ID.
`ChatSidebarView.ts:4774` saves cloned current messages; deletion methods replace
the active view/messages before persisting deletion IDs. Backend `gc.py` writes
session JSON separately, without joining these queues or refreshing the view.

`ChatMessage` has no typed diagnostic ownership field today. Historical query
panels recover a partial tool response embedded in message text through a regex
at `ChatSidebarView.ts:3053`; it is not a full prompt evidence bundle. Current
query trace CLI returns diagnostics from DB, and the prompt CLI also needs the
DB. A scan of visible `PTR-` strings cannot establish recoverable ownership.

## Recommended bounded design: evidence travels with its saved owner

Each message owning trace links carries a versioned, typed **diagnostic capsule**
inside that same message/session revision. It contains the linked trace IDs,
complete actual prompt rows and their agreed portable provenance envelopes,
and full query diagnostic rows when the saved link names a QTR whose diagnostics
must remain available. This is a retained copy of real diagnostic records, not
a skeleton reconstructed from IDs and not raw model output that was never
recorded. Capture only the diagnostically required closure, not the historical
source corpus or unrelated DB rows.

The capsule is part of the same serialized session revision as the transcript,
so an offline save, delayed sync file, or surviving conflict copy carries both.
Put it at message/session scope; the current normalization explicitly rebuilds
the top-level object and strips unknown top-level fields. Stable typed capsule
ownership replaces regex matching as authority for new writes. A legacy scanner
can discover migration candidates, but must validate actual payload availability
before reporting those links protected.

Use an immutable complete terminal capsule for a completed trace. A streaming
placeholder or pending trace may carry an explicit pending capture state, but
must not falsely claim its diagnostics are durably complete. Later completion
supplies the real terminal record. Where a backend operation produces the trace
and response, construct the complete capsule **before releasing its producer
reservation** and include it in the response/tool result. That closes the gap
between DB cap eligibility and plugin saving the returned result. A second
best-effort fetch after the backend returned does not close that gap.

For existing trace references newly inserted into a message, capture the real
evidence from the DB or an already verified capsule before asserting protected
ownership. If the backend is unavailable, allow the chat save and preserve its
explicit unresolved capture state; do not fabricate diagnostics or report the
link as protected. Existing capsule-bearing chats remain fully saveable and
inspectable offline. Migration/adoption must identify legacy links whose
payloads are already missing before enabling a destructive cap; those require
actual evidence recovery, not a silent weakening of the user's selection.

## Why a mandatory DB-intent-first save is not the narrow complete answer

A full recoverable session intent committed to the DB before JSON can protect
the local crash interval, provided recovery knows exactly which session revision
to replay. It does not by itself protect a remote JSON file arriving before its
DB export, an offline plugin save with no backend, or a peer whose evidence was
already evicted. Requiring the backend for every save would remove existing
offline availability. Adding a second plugin-local journal to rescue offline
DB intents creates another ownership authority and a larger recovery protocol.

The capsule makes session persistence self-contained, using the existing JSON
commit point. A DB owner mirror is useful for keeping immediately accessible
prompt rows and avoiding repeated restoration, but it is a rebuildable index,
not the only surviving copy. There is no need for a distributed transaction
between SQLite and JSON to guarantee retention of diagnostics once the owning
session revision is durably saved.

Do not call a save successful while the newest coalesced snapshot remains only
in memory. The existing writer's promise already represents its committed batch;
preserve that ordering. A crash before commit loses the unsaved message as today;
a crash after commit retains both transcript and capsule even if indexing never
happened. Durable provider reservations cover work before capsule delivery; no
claim is made that an OS pipe alone is persistent storage after client failure.

## Accepted-session owner reconciliation

The backend stores derived owners keyed by session ID and the exact accepted
session revision/content digest, with a set of capsule-backed prompt IDs.
Reconcile the actual accepted session content after merges, at startup/explicit
sync, before DB-backed trace lookup, and before destructive prompt GC. The
message payload is the recovery authority; the mirror is not an independently
synced peer lease. A metadata version/hash match is a cache check, not proof of
fleet acknowledgement.

Only a winning retained session revision protects/restores its actual diagnostic
set. A rejected stale revision must not reintroduce removed message references.
A session tombstone removes its derived ownership and suppresses every stale
capsule for that session ID. If another surviving session or DB artifact needs
the same prompt, that other owner continues protection. A newer accepted
revision replacing messages releases the old revision's references after its
new diagnostic set is validated. Whole-file absence, a truncated snapshot,
parse error or an unavailable adapter is not a deletion event.

Prompt restoration still crosses **retention** markers only. An ordinary DB
prompt tombstone is not silently cleared. If a saved capsule remains available,
the chat can inspect its captured diagnostics without pretending the canonical
DB record has been resurrected. A future explicit “erase every diagnostic copy”
operation would need to address session-owned copies too; the existing generic
DB tombstone API is not such a fleet/session erasure protocol.

If a session arrives before its DB snapshot, its capsule permits immediate full
inspection and eligible restoration. If GC or a retention marker arrives first,
the later accepted session restores the same real evidence. If the session
arrives first, its derived owner keeps the DB row, or a GC race can at worst
evict a recoverable redundant DB copy; it cannot erase the complete diagnostic
capsule inside the saved chat. Trace lookup must read the capsule or reconcile
it before returning “missing.” Mere periodic owner scanning cannot make that
last guarantee.

This maintains a finite count cap for genuinely ownerless diagnostic history.
Saved chats exempt their linked evidence exactly as the user selected. Embedded
capsules duplicate some metadata but are bounded by retained chat-owned evidence;
they do not retain every successful run. Do not introduce a global archive of
all unreferenced traces or indefinite response-delivery pins to simplify this.

## Session merge, deletions, and writer coordination

The diagnostic capsule must move atomically with whichever entire session wins
the existing LWW merge. Do not union capsule sets independently across losing
session revisions: that preserves diagnostics for removed messages forever.
Within one accepted revision, duplicate trace references can share one capsule
representation as a straightforward encoding choice, without inventing another
independently deleted shared payload store.

External sync and Python session pruning are still writers outside the adapter
queue. The capsule solves evidence lifetime even when indexing lags; it does
not fix lost session revisions or stale UI overwrites by itself. Before enabling
session GC, route pruning through the same session-operation authority as
interactive deletion, or define and test a shared process-level mutation
protocol. Backend JSON read/modify/rename plus another last-minute reread is not
that protocol. The active view must consume the committed merged state and stop
persisting deleted-session messages under a replacement active session ID.

Syncthing conflict files are not currently automatically merged by sessionStore;
the DB conflict discovery concerns only `.curator/sync/` exports. A session
conflict copy that contains a surviving owner must carry the full capsule so
that explicit/automatic accepted-session conflict recovery can recover its
diagnostics. Do not discard conflict files or release ownership based on their
temporary absence. The retention release must state whether conflict recovery
is already supported or add the narrow session conflict merge path; do not
claim the existing DB importer handles those files.

## Compatibility and actual rollout stop

`sessions.json` currently has no schema-version rejection, and older plugins
normalize/save files without understanding diagnostic ownership. Simply adding
a `schema_version` field does not make old binaries respect it. Although spread
operations preserve unknown message fields in several current paths, legacy
reconstruction, different branches, and old response production can still omit
capsules. Preservation by incidental object spread is not a compatibility proof.

Rehearse an explicit session-format/API version handshake and upgraded writers.
For the coordinated rollout, stop old writers of the shared session store,
preserve a coherent backup, hydrate/validate existing protected links on a copy,
upgrade backend and plugin together, and only then apply the authorized real
adoption. Offline incompatible peers keep their existing data but must not
write the upgraded shared canonical file until they upgrade; otherwise a new
field cannot enforce the contract. If maintaining simultaneous old-plugin writes
is required, version-isolated per-device stores and an explicit merge bridge are
necessary additional work. Do not silently reduce offline functionality merely
to avoid designing that bridge.

Actual modification/migration of the user's saved chats is the concrete
authorization boundary. Producing code and an isolated rehearsal does not need
another product decision about whether saved diagnostics matter: the user has
already decided that they do.

## Required acceptance schedules

- Backend returns a new prompt plus complete capsule; local cap runs before the
  plugin saves; saved chat still opens the complete trace, even offline.
- Stop the backend after capsule delivery; update/save/reload that chat through
  the actual adapter path; assert complete capsule values and transcript remain.
- Import a capsule-bearing chat before/after prompt retention eviction and
  before/after its separate DB snapshot; inspect full diagnostics each way.
- Save during a coalesced write, crash after JSON commit before owner indexing,
  restart and rebuild owners from the accepted revision.
- Delete on A while offline B keeps an old revision; merge both orders and
  verify deletion dominates and no stale derived owner/capsule revives the chat.
- Two chats reference one prompt; deleting one releases only its ownership;
  deleting the last makes an otherwise unreferenced DB run cap-eligible.
- Replace message content in a newer accepted session revision; obsolete
  capsules do not survive through independent set union.
- Malformed capsule/JSON, legacy missing evidence, unknown versions and session
  conflict recovery produce explicit recoverable states without deleting chat
  bytes or synthesizing diagnostics.
- Race session GC with actual active-view persistence and external-file update;
  verify committed deletion is not overwritten or old messages copied into the
  replacement active session. Do not substitute a standalone JSON unit test for
  this integration schedule.
