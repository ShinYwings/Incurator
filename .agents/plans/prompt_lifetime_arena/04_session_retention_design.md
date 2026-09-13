# Saved-Chat Prompt Ownership: Retention Design and Independent Audit
Date: 2026-09-13 | Scope: user's choice to protect saved chat links

## Decision and observed surfaces

The user chose **“Protect saved chat links too; retain diagnostics while those
chats exist.”** This closes the previous owner-universe ambiguity: a saved chat
containing a prompt trace link is a retained owner, including an otherwise
unowned correction diagnostic. A pure SQL owner registry is incomplete.

Verified current paths:

- Actual generated IDs use `PTR-` plus eight hexadecimal characters
  (`db/_entities.py:34–36`). They occur as ordinary text, JSON string values and
  arrays, not only Markdown hyperlinks. Examples in the code are
  `prompt_trace_ids`, camel-case `traceId`, and a CLI `wiki prompt trace` ID.
  The query trace panel displays IDs as plain spans, capped at eight displayed
  IDs (`ui/incuratorQueryTrace.ts:154–167`); visible panel truncation cannot be
  the ownership extraction source.
- Query-tool result display preserves the complete `prompt_trace_ids` array
  and nested `trace` (`agent/llm/messageUtils.ts:241–263`). Streaming turns that
  result into assistant message content (`agent/llm/LLMClient.ts:1966–1986`).
  The sidebar appends stream chunks to message content and persists complete
  messages at turn boundaries (`ChatSidebarView.ts:1309,4774–4791`).
- The correction plugin command returns a `traceId` without a candidate
  (`commands/plugin.py:1038–1075`). Unlike the MCP route, no durable candidate
  may protect that returned diagnostic. Session attachment must cover it.
- `ChatMessage.content` survives persistence. Sanitization removes selected
  auto-context payloads and device paths but retains content and thumbnails
  (`utils/sessionData.ts:63–136`). The session store is
  `.curator/sessions.json`, independent of SQLite (`plugin/main.ts:1638–1652`).
- Session merge unions `deletedSessionIds`, then chooses the newer whole
  session using `updatedAt` (or `createdAt`), breaking ties by message count
  (`utils/sessionData.ts:15–52`). Absence in an input is not deletion. Explicit
  delete writes a tombstone (`ChatSidebarView.ts:4900–4952`); GC does the same
  (`gc.py:455–488`). Selected sidebar messages are a separate clone, so a
  background session change requires reconciliation bound to the original
  session ID before the next save.
- Plugin writes serialize only inside one JS process and use
  `adapter.process`; Python GC separately rewrites the file. The existing
  serialization does not coordinate both writers. Session writer/prune
  correctness is now a prerequisite of this expanded ownership contract.

A read-only aggregate inspection of the current canonical production session
file found 18 sessions, 65 session deletion IDs, and zero message-content
occurrences matching the actual generated PTR format. No message text was
emitted and no files were changed. This says nothing about offline peers,
archives, future chats or arbitrary imported IDs. It does establish that the
current local canonical history does not require recovering a known PTR link
under this exact token scan. Test fixtures also use IDs outside the generator's
hex format; imported valid identifiers must follow the versioned trace-ID
contract rather than accidentally making fixture-specific assumptions.

## Smallest complete ownership representation

Each accepted saved session revision should carry:

1. Its existing session identity, revision identity and full messages.
2. An explicit set of linked prompt IDs, derived from structured tool results
   plus the full saved content. A narrowly specified token lexer catches pasted
   plain/JSON/Markdown PTR links as well. Treat each well-formed exact ID as a
   link regardless of prose context; do not let an LLM decide whether it counts.
3. Complete portable prompt evidence for each linked ID, keyed once per trace
   in that session revision. Reuse the fleet contract's evidence representation,
   including unresolved provenance. Do not invent a second smaller chat-only
   trace format. A single trace linked by multiple messages needs one bundle.
4. Explicit unresolved-link records when the trace was already unavailable
   before adoption/attachment. Preserve the ID, report the missing diagnostic,
   and allow later intact evidence to repair it. Do not fabricate hashes or
   claim that a missing historical trace was successfully protected.

The evidence is serialized in the **same atomic session record** as its owner.
A separate JSON sidecar plus a session ID does not establish closure: Syncthing
can deliver one file without the other. Metadata embedded at session level is
not injected into provider replay or visible assistant prose. Full messages,
manual attachments and thumbnails retain their existing behavior.

This deliberately adds copies of referenced diagnostic records. That cost is
required for a session arriving after its prompt was evicted elsewhere to
restore the diagnostic independently. It is bounded by retained linked
diagnostics, not an archive of every successful prompt. Unreferenced history
still obeys the cap; deleting the last owning chat makes its bundle reclaimable
subject to other owners. Optional content deduplication across sessions is a
separate optimization; introducing shared sidecar payloads here would add a
second transport-closure problem without being necessary for correctness.

## Local publication and crash semantics

The producer handoff must provide a full evidence bundle before it releases
the reservation that prevents prompt deletion. Capturing only a trace ID and
calling `getPromptTrace` after the turn leaves a race in which GC removes the
record before the chat saves it. The current plugin getter returns only seven
metadata fields; it is not sufficient evidence for full trace reconstruction.

For a new backend-generated result, finish the row, obtain its full portable
evidence and bind the handoff to the originating session/message/producer
identity before releasing ownership. The plugin persists the bundle with the
resulting saved transcript. The producer protocol must retain a durable
reservation until that save is acknowledged, or durably transfer complete
evidence to a recoverable handoff inbox first. An in-memory bundle alone does
not close the crash-after-return/before-save gap. An abandoned handoff may be
released only through the producer recovery semantics, not a time grace period.

For a pasted link, acquire available evidence before committing the saved
session revision; use a short DB transaction/reservation during acquisition.
If the diagnostic is already missing, save the chat with an explicit unresolved
link and report it. Do not block ordinary transcript persistence forever merely
because the local backend is unavailable: carry already acquired evidence and
durably save unresolved link intents for later hydration. While a known local
unresolved intent could refer to existing prompt data, destructive GC must
reconcile it before deleting that candidate. Backend unavailability must not
erase messages or silently drop the link from ownership.

After an atomic session write, the complete diagnostic is durable even if the
process crashes before updating the DB mirror. The backend can reconstruct
the mirror from the session record. Conversely, a pre-save reservation that
survives a failed session write is a recovery item, not evidence that the chat
successfully exists. Distinguish the two states explicitly.

## Enumeration, reads and garbage collection

The backend's prompt-owner registry gains saved-session owners derived from
accepted session revisions. Store session identity, accepted revision and trace
identity, so diagnostics identify the protecting chat. Reconcile canonical
session evidence before planning/applying the cap and before fulfilling a
missing trace lookup. A prompt evicted locally can be restored from an accepted
saved-session bundle; inspection must not report “unknown” when that complete
owned diagnostic remains available in the canonical session store.

Do not clear session owners because a file is missing, unreadable, corrupt,
partially synced or omitted from a particular export. Keep known owners and
make candidate deletion unavailable when ownership cannot be established.
Release ownership only for an accepted session tombstone or an accepted newer
revision whose retained content no longer links that diagnostic. A merely
older, losing revision cannot pin unrelated runs forever.

Final-state session acceptance must be shared with the canonical merge. Two
loosely similar Python/TypeScript interpretations of LWW ties would compute
different owners. The selected session writer design must serialize writes and
prune decisions coherently and bind the saved snapshot to the originating
session ID. Updating a DB mirror and rereading the file immediately before SQL
deletion is not an atomic writer protocol. Complete embedded evidence supplies
recoverability across the file/DB boundary; it does not excuse losing the
session file itself to a concurrent backend overwrite.

## Fleet schedules and deletion

The new saved-session schema needs an explicit compatibility boundary. The
existing schema-less normalizer cannot safely establish old/new cooperation:
an old writer may preserve some unknown object keys accidentally, but cannot
compute evidence for its new links or participate in the new writer protocol.
Version handshake plus coordinated upgrade of known writers is required;
merely adding a top-level field ignored by the old plugin does not enforce it.

- **Session arrives before prompt DB export:** accept the session with embedded
  evidence, register its owner and restore/protect the trace. No DB-export wait.
- **Retention arrives before offline session:** evict the locally unowned trace;
  later accept the saved session and restore exactly its required evidence.
- **Retention arrives after saved session:** surviving session ownership wins
  over retention-only eviction. Ordinary prompt deletion remains a separately
  reported conflict under the fleet proposal.
- **Deleted session reappears in an old peer snapshot:** the retained session
  tombstone defeats it; its evidence must not resurrect a prompt. Do not prune
  session deletion IDs without an acknowledgement/recovery design.
- **Offline session update conflicts with an explicit deletion:** preserve the
  existing deletion-wins contract. The explicit deletion removes that chat
  across devices; it does not silently delete another surviving chat's evidence.
- **Owner replacement removes a link:** release that revision's ownership only
  after canonical acceptance. A surviving different chat or DB artifact still
  protects the diagnostic. Historical losing session revisions do not create
  infinite ownership beyond the current retained-history contract.
- **Old session with bare IDs arrives:** preserve the full transcript, register
  unresolved link intents, hydrate from a matching intact local row or valid
  evidence bundle, and expose still-missing IDs. Historical exports that lack
  evidence cannot promise recovery of data already absent everywhere.

No all-peer acknowledgement is required for revisable retention with bundled
evidence. An offline peer retains complete evidence in its saved session, so
newly receiving devices can repair an earlier local eviction. This preserves
offline capability while keeping the unreferenced cap meaningful.

## Provenance: preserve recorded trace, do not replicate an entire source graph

The existing trace records source integer IDs and span IDs, not source text.
“Complete trace evidence” means every recorded trace field plus enough identity
context to interpret those values honestly across devices. It does not require
embedding full source documents or every span's text in every chat. That would
invent a larger historical replay guarantee than `prompt_runs` currently has.

Reuse the fleet immutable envelope: preserve the original ordered arrays,
resolved source `sync_key` identities, and explicit capture-scoped unresolved
values. Operational local source IDs can be translated separately. For span
IDs whose rows no longer exist, preserve the original token and missing status;
do not drop it or revive removed sources. Identical recorded bytes plus an
origin/capture context preserve diagnosis even when a clickable source target
is unavailable. Existing tombstones and missing content remain visible facts.

This is smaller and more accurate than requiring transitive copies of the full
source graph to save a diagnostic link. It is also more complete than merely
copying the raw source integer array into a peer's namespace, where the same
number may identify an unrelated source. The current measured missing-parent
cases (48 referenced runs with missing spans, four with missing source IDs)
must be migration fixtures. Do not simplify the design by dropping them.

## Required adversarial verification

- Plain PTR text, nested JSON arrays, camel-case trace fields, Markdown labels
  and destinations, repeated IDs, truncated display versus full saved result,
  pasted IDs and malformed tokens; ownership derives from complete saved data.
- Correction result with no candidate: start, finish, handoff, session save,
  crash at every boundary, and concurrent cap/imported retention.
- Session-only arrival after prompt deletion restores exact metadata; no intact
  row is invented from bare ID/hash. Missing old diagnostics stay visibly
  unresolved while their transcript still saves and replays fully.
- Failed save, coalesced writes, concurrent save/prune, active-session switch,
  stale selected-message clone, reopened writer and backend unavailability.
- Losing versus accepted session revision, delete versus stale offline save,
  last owner removal, multiple chats sharing one trace, and malformed stores.
- Independently delivered session/DB exports, both retention arrival orders,
  old writer rejection/rollout, legacy session conversion and existing missing
  parent provenance, all on disposable copies.

## Bounded recommendation

Use saved-session evidence bundles as durable owners and a rebuildable DB
mirror; couple producer handoff and the session writer fix to the same lifetime
contract. Keep session replay unchanged. The user has already selected the
capability, so implementation planning and isolated rehearsal can proceed
without another preference question. Real production session/DB migration is
still a concrete final authorization gate. No production writes occurred here.
