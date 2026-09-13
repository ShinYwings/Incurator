# Session Writer Consensus: Keep the Current Store and Lock Its Local Writers

Date: 2026-09-14. Closing review of the three `04_session_*` proposals.
No application code, production session files, or live databases were changed.

## Decision and scope

Keep `.curator/sessions.json` as the saved transcript authority. Add typed,
versioned full diagnostic capsules to its retained session revisions; deduplicate
the same PTR within a session. Capsule references belong to actual messages or
durable diagnostic attachments of a saved turn. A losing session revision does
not independently union its capsule set into the winner. Preserve full replay,
all retained message fields, and thumbnails.

Do not introduce an immutable full transcript bundle for every save. The
existing writer coalesces six save calls per send because repeated full-file
serialization was already expensive (`main.ts:1709–1730`). A second authoritative
transcript revision history would need compaction, winner witnesses, recovery,
and extra synchronization for no additional diagnostic durability once the
capsule is in the same committed session. Narrow response receipts for provider
routes that hide tool results are different: they contain newly saved diagnostic
attachments, not another copy of every transcript revision.

Preserve immediate `wiki gc run` session removal. A backend prune request that
only the next running plugin can consume is a reduction of the current CLI
capability. It can be made honest with a pending count, but is not selected.
Instead, put the existing plugin writer and backend prune under a shared local
kernel lock. The plugin remains able to save without a running backend service.
Only the actual read/merge/write commit holds the lock; provider calls and UI
pauses never do.

This is an engineering implementation requirement, not another unresolved
product question. The user's chat protection choice is already explicit.

## Lock primitive and delivery obligation

The plugin is desktop-only (`plugin/manifest.json`), so native filesystem access
is available. Node's ordinary `fs` API does not supply the required advisory
lock. A promise queue, `adapter.process`, exclusive-create marker, or stale-time
lock directory is not a substitute for a process-owned kernel lock.

Use a narrow Node-API binding whose only job is acquiring/releasing a nonblocking
whole-file lock on an already-open descriptor. Match Python's implementation:
`flock(LOCK_EX | LOCK_NB)` on macOS/Linux; `LockFileEx` with one fixed documented
range on Windows. Hold the descriptor in the process doing the file mutation.
Python's Windows wrapper must use that same range and primitive. Do not use a
child helper as the lifetime owner: it may die while the plugin still writes.
Do not mix Linux `flock` with an unrelated `fcntl` record-lock family.

The lock path is stable and machine-local under the resolved vault cache; its
identity is shared by Python and the plugin through the existing canonical
vault/cache identity calculation. Never unlink or rename an active or idle lock
file during routine release. Removing it lets two writers lock different
inodes under the same name. Reject symlink/unknown lock paths. Kernel release on
descriptor close/process exit handles crashes without lease expiry, PID reuse
guesses, or orphan-marker reaping. Poll nonblocking acquisition asynchronously;
waiting may be cancelled but cancellation never steals another owner's lock.

Native packaging is a real release gate. Current `esbuild.config.mjs`, setup,
and the plugin updater distribute only `main.js`, `manifest.json`, `styles.css`.
The shipped lock binding must be carried by those supported delivery paths,
including self-update, with a deterministic platform/architecture manifest and
verified binary digest. Test the installed artifact, not merely a development
`node_modules` import. A missing/unloadable binding yields a visible save/GC
error before canonical mutation; it never quietly switches to unlocked writes.

Primary-source reconnaissance confirms the primitives are available in an
existing portable implementation: [`fs-native-extensions`](https://github.com/holepunchto/fs-native-extensions)
uses [`flock` on macOS](https://github.com/holepunchto/fs-native-extensions/blob/main/src/apple.c)
and [`LockFileEx` on Windows](https://github.com/holepunchto/fs-native-extensions/blob/main/src/win32.c).
Its current [build](https://github.com/holepunchto/fs-native-extensions/blob/main/CMakeLists.txt)
targets Node-API 9. The project manifest permits Obsidian 1.1.0; adopting that
binary without checking its runtime would silently narrow supported versions.
Therefore the master plan must implement/package the narrow binding at a
Node-API level supported by the declared minimum runtime, or demonstrate the
chosen dependency's actual compatibility. Do not claim this reconnaissance was
an Electron/macOS/Windows runtime test. No dependency was installed here.

## Exact local commit and prune ordering

The existing per-adapter queue remains useful for coalescing. Every queued
write, first-file creation, import of a conflict snapshot, interactive deletion,
and Python prune must acquire the same local lock before reading canonical
state, and release it only after the atomic canonical replacement completes.
Under it, validate schema, read accepted conflict candidates, merge complete
sessions and permanent deletion IDs, apply the requested mutation, and write.
Corrupt/unreadable canonical or required conflict data blocks mutation and
preserves its bytes. Do not replace malformed state with an empty store.

`gc.prune_sessions` re-evaluates its configured age cutoff against this freshly
merged locked state. A separate earlier preview is not its deletion authority.
If an updated session was committed before GC acquires the lock and its current
timestamp is inside the retained window, GC keeps it. If prune obtains the lock
first and commits a terminal deletion, a later stale save of that same session
ID receives a deleted-session conflict. That is the existing deletion-wins
policy with a defined local serialization point. Different sessions' new
messages cannot be overwritten by a stale whole-file backend snapshot.

If the lock cannot be acquired, report busy/cancelled, not successfully removed.
Return the number of newly committed logical deletions. Physical JSON bytes and
SQLite page reclamation remain separately measurable facts.

Take no SQLite transaction while waiting for this filesystem lock. The shared
order for operations requiring both is session lock, snapshot/capsule validation,
then SQLite write transaction. Provider scopes never hold either while waiting
on a model. Derived owner indexing may lag a committed JSON write because the
committed capsule already preserves the record; replay restores the index.

## External synchronization and deterministic acceptance

Syncthing does not obey the local lock. Do not call local exclusion a fleet
transaction. Keep whole-session LWW and terminal deletion semantics. Add an
explicit deterministic revision identifier for new sessions, using the existing
updated-time and message-count ordering followed by that identifier on a tie.
Legacy revisions need a fixed shared canonical encoding/digest with Python/TS
golden fixtures; no language-default JSON serialization may decide a tie.

Add the currently missing discovery and validation of session conflict copies
next to `.curator/sessions.json`; the existing DB conflict code only examines
`.curator/sync/`. Merge each complete valid candidate through the same policy.
Do not union message histories or evidence from an unaccepted losing revision.
Preserve conflict bytes until their result has been committed and verified.
Late offline activity that was unseen by a committed terminal deletion remains
subject to deletion-wins, as it is today. The local lock does not claim to rescue
an unseen remote update from that policy.

The backend's owner mirror records the latest accepted session revision witness
and its validated diagnostic set. A stale canonical replacement, whole-file
absence, read failure, or a missing conflict file cannot prove that a known
session was deleted and must not clear those known owners. Only an accepted
replacement of that session or its terminal deletion does so. A late accepted
capsule restores diagnostics across a retention-only eviction, subject to the
fleet rules; ordinary deletion is not silently cleared. Before reporting a
trace absent, its lookup must reconcile/fall back to accepted saved evidence.

## Stale view and overlapping saves

`ChatSidebarView.persistCurrentSession` currently chooses the destination from
mutable `plugin.sessionData.activeChatSessionId` at save time. Give the view its
own explicit loaded session ID and observed revision. Every snapshot/save carries
that ID. A committed merge may change the app's selected session, but must never
retarget old view messages into it. A deleted-session result cancels that stream
and preserves an unsaved draft for explicit recovery into a new ID.

There is a second concrete queue hazard: `main.ts:1742` assigns the entire result
of an in-flight write to `this.sessionData`, although a newer mutation may have
arrived since that write's snapshot. Preserve a monotonic local mutation epoch
or equivalent pending edit set; rebase the committed result with edits newer
than the captured epoch. A save promise covers its own captured mutation and
earlier mutations, never a still-pending newer snapshot. Integration tests must
exercise this real plugin state flow, beyond testing the generic coalescer.

## Offline evidence and provider boundary

An existing capsule-bearing session remains saveable and inspectable offline.
For new generated diagnostics, capture complete evidence while the producer
scope still owns its PTR. A response field alone is insufficient for routes
that expose only summarized tool output. Follow `05_handoff_consensus.md` (or
the closing handoff record) for route-specific transport.

The reviewed hidden-route shape pre-saves a user message plus assistant turn
placeholder, then saves full-capsule receipts under that explicit session/turn
while the producer is still protected. Such a receipt is a visible/recoverable
diagnostic attachment of an already-saved turn. It is not an unacknowledged
forever lease. Read/save/reload joins valid attachments for the accepted turn;
session deletion suppresses them. Never infer their identity from the active
session at result-arrival time or modify shared MCP config with a turn token.

Historical/manual links without retrievable records preserve their message and
explicit unresolved state. Do not fabricate diagnostics, block all offline chat
saving, or claim that unresolved historical evidence is fully protected.

## Acceptance gates

1. Spawn actual Node/Electron and Python actors using the shipped binding.
   Hold the lock in either process, prove the other cannot write, kill the
   holder, and prove the survivor acquires without timeout-based stealing.
   Run matching tests on each supported desktop platform/architecture.
2. Race a current-session update with prune in both lock orders, plus a separate
   session update, missing-file initialization, multiple queued saves, and a
   corrupt canonical file. Assert exact final transcripts and deletion IDs.
3. Delete a selected session during streaming and switch sessions during an
   in-flight save. Assert old messages cannot appear in the replacement session
   and newer local edits survive completion of an earlier save.
4. Deliver capsule-bearing session snapshots and retention imports in both
   orders; include a real session conflict filename, deterministic tie fixtures,
   stale file replacement, missing file, and one-of-two/final-owner deletion.
5. Stop the backend after evidence capture and save/reload through the real
   plugin path. Rebuild the DB mirror and compare every diagnostic field.
6. Rehearse legacy adoption using copied sessions/DB only, preserving full
   normalized messages and thumbnails, and report already-missing evidence.
   Actual user-data migration remains a separate final authorization boundary.

The lock binding's supported-runtime build and installed-artifact smoke test
are concrete implementation gates, not finished work. This closes the storage
shape without claiming that a new native binary has already shipped.
