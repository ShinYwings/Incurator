# Inspector Report: `session_state` (Observation B)

Domain: `.curator/sessions.json` — 15 MB, 11 sessions, 236 messages, 292
`contextRefs`. Read-only investigation. No code, docs, config, vault, or DB
writes made (one throwaway Node/esbuild probe script executed against the
live file's *content* to time real JSON round-trips and simulate the merge
function; the script and its intermediate compiled module were written and
deleted entirely inside the scratchpad, never inside the repo or the vault —
verified with a post-run `ls` that showed no stray file in `plugin/`).

## Method

Read `plugin/src/utils/sessionStore.ts` (115 lines), `durableJsonStore.ts` (68
lines), `plugin/src/utils/sessionData.ts` (94 lines, the merge/sanitize
logic), the session-persistence half of `plugin/main.ts` (`_sessionsPath`,
`loadSessionData`, `saveSessionData`, `writeSessionData`, lines 1562–1657),
and every `contextRefs`/`persistCurrentSession`/`saveSessionData` call site in
`plugin/src/ui/chat/ChatSidebarView.ts`. Cross-checked against
`docs/specs/plugin_schema/PLUGIN_SCHEMA.md` §2.2 (`SessionData`) and §6.1–6.2
(`ContextRef`), and against `plugin/src/utils/sessionData.test.ts`,
`sessionStore.test.ts`, and `mainSecurity.test.ts`.

For ground truth I read the **live** vault file directly (not a copy):
`/Users/shin/shinywings/second_brain/.curator/sessions.json`, confirmed
`15,085,579` bytes on disk (`ls -la`) / `14,054,949` bytes of UTF-8 text
content. I then:

1. Timed `readFileSync` / `JSON.parse` / `JSON.stringify` / a
   parse-then-stringify deep clone on that real file with `performance.now()`
   in Node, to get real (not estimated) per-round-trip costs.
2. Walked the parsed object to reproduce the byte breakdown by `ContextRef`
   type, find the single largest `imageBase64`, and count re-attachment
   frequency per `filePath`.
3. Extracted `mergeSessionData` and `normalizeSessionData` from
   `sessionData.ts` via `esbuild.buildSync` (no repo files touched — output
   captured to an in-memory string, only briefly written to a scratchpad
   `.mjs` file that was `import()`-ed then immediately deleted) and drove
   them with a synthetic 30-session disk state to test whether the
   30-session cap in `ChatSidebarView.ts` actually bounds what gets written.

## Ground-truth measurements

```
file bytes (raw):              15,085,579   (ls -la, live file)
file bytes (utf8 text length): 14,054,949
chatSessions:                  11
deletedSessionIds:             50   (851 bytes serialized — trivial today)
total messages:                236
total contextRefs:             292
```

`ContextRef` breakdown by type (measured by re-serializing each parsed ref):

| type | count | bytes | avg |
|---|---:|---:|---:|
| `pdf-page` | 125 | 8,879,405 | 69.4 KB |
| `file` | 145 | 3,222,903 | 21.7 KB |
| `line-range` | 16 | 9,363 | 0.6 KB |
| `text` | 6 | 1,249 | 0.2 KB |

Total `contextRefs` bytes: **12,112,920** (80.3% of the file). Total message
`content` bytes: **490,388** (3.3%). The rest is JSON structural overhead.
(These numbers are close to, but not identical to, the briefing's snapshot —
the file has grown since the briefing was written; both point at the same
80%+ `contextRefs` dominance.)

`imageBase64` fields: 9 present, 6,223,752 bytes total. Largest single one:
**1,392,136 bytes** — `pdf-page`, label `"2D Gaussian Splatting for
Geometrically Accurate Radiance Fields2024 - Huang et al. - .pdf p.11
(Crop)"`, page 11. (Matches the briefing's 1,392,138-byte figure to within 2
bytes — same ref, measured independently.)

Top re-attached `filePath`s by raw occurrence count across all persisted
`contextRefs`:

| occurrences | total bytes | filePath |
|---:|---:|---|
| 52 | 577 KB | `03_Notes/Papers/PoseEst/Camera Pose Estimation from Lines using Plücker Coordinates.md` |
| 24 | 1,106 KB | `03_Notes/Vision/Silhouette Based Reconstruction.md` |
| 24 | 131 KB | `01_Workspaces/COLMAP free GS/00_Project/milestones.md` |
| 23 | 873 KB | `03_Notes/Vision/MultipleViewGeometry.md` |
| 22 | 434 KB | `03_Notes/Vision/Auto Calibration.md` |

This is a **plain markdown note re-embedded whole 52 separate times**, not a
PDF — the duplication problem is not image-specific.

Real JSON round-trip cost on the live 14,054,949-byte text, measured with
`performance.now()` in Node on this machine:

| operation | time |
|---|---:|
| `readFileSync` | 34.0 ms |
| `JSON.parse` | 21.5 ms |
| `JSON.stringify` (compact) | 32.6 ms |
| `JSON.stringify(obj, null, 2)` (matches the actual on-disk pretty format) | 34.8 ms |
| deep clone via `JSON.parse(JSON.stringify(obj))` (matches `saveSessionData`'s snapshot step) | 46.3 ms |

## Findings

### F1 — [P2] The only apparent size cap on `chatSessions` is provably a no-op; sessions.json cannot shrink via normal use

**My measurement:** `createNewChatSession` (`ChatSidebarView.ts:4559–4577`)
and `persistCurrentSession` (`:4618–4635`) both cap the **local, in-memory**
session list with `.slice(0, 30)` (`:4566`, `:4632`) before calling
`saveSessionData()`. I extracted the real `mergeSessionData` /
`normalizeSessionData` from `plugin/src/utils/sessionData.ts` with
`esbuild.buildSync` and ran them directly (not a reimplementation) against a
synthetic disk state of 30 sessions (`S1`..`S30`) plus a local, freshly
30-capped array (`S0`..`S29`, i.e. the codebase's own "new chat evicts the
oldest" behavior). Result:

```
disk sessions before write: 30  (S1..S30)
local (30-capped) sessions to save: 30  (S0..S29, S30 evicted)
MERGED result written to disk: 31 sessions
Was S30 (evicted by the 30-cap) dropped from disk? false
```

The cause is structural, not a fluke of my synthetic data:
`mergeSessionData` (`sessionData.ts:22–53`) does `for (const session of
remote.chatSessions) sessions.set(...)` **unconditionally** (line 29–31) for
every session on disk not in `deletedSessionIds` — and `writeMergedSessionStore`
(`sessionStore.ts:66–114`) always re-reads the canonical disk file as
`remote`/`current` before merging (`:80`, `:90–96`). Evicting a session from
the local array via `.slice(0, 30)` never adds that session's id to
`deletedSessionIds` — I grepped every write site
(`ChatSidebarView.ts:4743–4745`, `:4777–4779`, `sessionData.ts:24–26`) and
the **only** two places that append to `deletedSessionIds` are
`deleteChatSessionById` and `deleteCurrentChatSession`, both explicit
user-initiated deletes. So on the very next save, the union-merge reads the
evicted session back off disk (it's still `remote.chatSessions[30]`) and
re-adds it, because "not present in `local`" is not the same as "deleted."
Net effect: the "cap" makes the local UI list show ≤30 recent sessions, but
the **persisted file's session count only ever increases** — by one net
session per "New chat" click, forever — unless the user explicitly deletes a
session (which correctly tombstones it; see F1 vs. F4 below).

This is unreachable from `sessionData.test.ts`'s existing coverage: its four
`mergeSessionData` tests (`:29–65`) all exercise 1–2 sessions, never a
30-boundary eviction scenario, so nothing pins today's (broken) behavior as
either intended or forbidden.

**Failure scenario:** A daily-driver user who starts >30 new chats over the
project's lifetime (trivial — the live vault already has 11 in under a
month) will never see `chatSessions` actually bounded at 30 on disk, even
though the UI drawer only ever shows the 30 most recent. Every unique
"New chat" click nets +1 persisted session forever; the only thing that
actually removes a session from disk is an explicit trash-icon delete. The
one piece of code that looks like a size guard against the exact growth this
domain is investigating does not provide that guard.

### F2 — [P2] Auto-attached context is re-embedded at full size on every message send, with zero dedup across messages — this is 80% of the file and the direct cause of the N× re-attachment pattern

**My measurement:** `buildAutoContextRefs` (`ChatSidebarView.ts:2095–2201`)
is called **fresh on every `sendMessage()`** — twice per send, in fact:
once at `:1052` (chip render) and again at `:1125` (the "final" refs that
actually get persisted). For every currently open markdown tab it builds a
`file`-type ref carrying the **entire truncated file content** (`:2107–2128`);
for every open PDF tab on a scanned/vision page it carries the **entire
page's `imageBase64`** (`:2168–2188`, specifically `:2187`:
`imageBase64: tab.pdfPage.selectedImageBase64 || (tab.pdfPage.isScannedLike ?
tab.pdfPage.imageBase64 : undefined)`). The only dedup is a `seen` `Set`
scoped to the single function call (`:2101`, `:2193–2196`) — it prevents the
*same open tab* appearing twice in *one* `buildAutoContextRefs()` call, but
nothing prevents the next message's call, five seconds later, from building
and persisting an entirely new, byte-identical copy of the same
content/image if the tab is still open. `materializeContextRefs`
(`:2244–2274`), which runs right before the refs are written into
`userMsg.contextRefs` and persisted (`:1123–1129`), never compares against
prior messages in the session — it only resolves `pendingCropBase64` and
refreshes pinned refs.

This matches the measured data exactly: the live file's top offender is a
12 KB-ish markdown note re-embedded **52 separate times** (577 KB total, see
Ground-truth table) purely because it was left open across 52 sends; the
125 `pdf-page` refs average 69.4 KB each for the same reason.

Regarding "is the image needed after the message is sent": tracing
`imageBase64` forward, its only two consumers after persistence are (a) the
LLM payload builder (`:1557–1618`, sent once, at send time) and (b) chat
history re-render as a `<img src="data:image/png;base64,...">` thumbnail
(`:2851–2854`, `:4365–4368`). Consumer (b) is a scrollback thumbnail, not a
re-usable prompt artifact — nothing downsamples, compresses, or strips the
base64 after the LLM call completes, so every historical message keeps a
full-resolution PNG (up to 1.4 MB, per the largest measured ref) purely to
render a thumbnail that could be reconstructed at a fraction of the size or
re-captured on demand.

**Failure scenario:** any user who works with the same 3–5 notes/PDFs open
across a research session (the exact, observed pattern in the live vault —
Silhouette-Based Reconstruction.md alone accounts for 1.1 MB across 24
re-embeddings) accumulates storage as **O(messages × open_tabs × content
size)** instead of **O(unique content)**. This is the direct, measured
mechanism behind "same file re-attached up to 43–52×" and behind
`contextRefs` being 80% of a 15 MB file for only 236 messages of actual
conversation text (490 KB).

### F3 — [P2] Every save is a full-file, synchronous read-parse-merge-stringify-write cycle; a single message send chains four of them serially with no debounce, and the cost is linear in total file size

**My measurement:** `saveSessionData()` (`main.ts:1622–1630`) does
`JSON.parse(JSON.stringify(this.sessionData))` — a full deep clone of the
**entire** in-memory session state — before it ever touches disk. It then
calls `writeSessionData` → `writeMergedSessionStore`
(`sessionStore.ts:66–114`), which (a) calls `readSessionStore`
(`:50–64`) — one full `adapter.read` + `JSON.parse` of the **whole file** —
purely to classify `missing`/`valid`/`corrupt`/`unreadable`, then (b) calls
Obsidian's `adapter.process(path, fn)` (`:90–102`), which internally does its
**own** full read and hands the raw text to `fn`, which does a **second**
full `JSON.parse` (`:92`) plus one full `JSON.stringify(..., null, 2)`
(`:97–101`) before the atomic write. So one `saveSessionData()` call = 1 deep
clone (parse+stringify) + 2 full reads + 2 full parses + 1 full
`mergeSessionData` walk + 1 full pretty-stringify — all synchronous,
O(total file size), not O(what changed).

`sendMessage()` chains **four** of these sequentially (not in parallel — both
`sessionPersistPromise` in `main.ts:1626` and the adapter-scoped queue in
`sessionStore.ts:41–48,71–113` serialize them): `persistCurrentSession()` at
`ChatSidebarView.ts:1067` (after the user message is pushed), `:1085` (after
the empty streaming placeholder is pushed), `:1129` (after context refs are
materialized), and `:1155` (in the `finally` block after the answer
completes). `onSessionChange` (`:4579–4600`) similarly fires **two** full
saves back to back: one inside `persistCurrentSession()` (`:4584`→`:4633`)
and a second, separate `saveSessionData()` call right after (`:4595`). By
contrast, per-keystroke cost in the composer is **zero** — the `input`
listener (`:369–373`) only resizes the textarea, it never persists.

Using the real per-operation timings measured on the live 14.05 MB file
(Ground-truth table above): one `saveSessionData()` round trip ≈
34.0(read)×2 + 21.5(parse)×2 + 46.3(clone) + 34.8(stringify) ≈ **192 ms** of
synchronous main-thread JS. One `sendMessage()` (4 sequential saves) ≈
**~770 ms** of blocking work today, at 15 MB. Because every step here is
O(file size) — nothing is incremental or append-only — this scales linearly:
at 100 MB (≈6.6× today's size) the same single message send would cost
**~5 seconds** of synchronous, unyielded JS execution split across four
separate stalls in Obsidian's single-threaded Electron renderer, silently,
with no progress indicator beyond the existing "Thinking…" text.

To be fair to the implementation: the **atomicity** claim in
`PLUGIN_SCHEMA.md:891,903–910` and `sessionStore.ts` is correct and already
covered by `sessionStore.test.ts:101–191` (concurrent-write and
corrupt/unreadable fail-closed tests pass) — I am not re-reporting that as a
defect. The problem is exclusively that "atomic" here means "atomic and
O(whole file)," and nothing bounds "whole file."

**Failure scenario:** as the vault owner continues normal use (the file is
"actively built," per the briefing, growing daily), every future message
send gets slower in lockstep with total history size, not with that
message's own size — a user who has a long conversation about a *small*
question pays the *same* four-full-file-round-trip tax as a user attaching
a 1.4 MB image, purely because the file itself has grown. There is no
incremental write path anywhere in `sessionStore.ts` or `durableJsonStore.ts`
to fall back to.

### F4 — [P3] `deletedSessionIds` is a monotonically-growing, never-pruned tombstone list — currently negligible in bytes, but structurally identical to the F1 growth-without-bound pattern

**My measurement:** every write site is a union, never a shrink:
`ChatSidebarView.ts:4743–4745` (`deleteChatSessionById`) and `:4777–4779`
(`deleteCurrentChatSession`) both do
`Array.from(new Set([...(deletedSessionIds || []), id]))`;
`sessionData.ts:24–26` (`mergeSessionData`) does the same union across
local/remote. I grepped the entire plugin source and `main.ts` for
`deletedSessionIds` and found no read site that ages out, caps, or removes
an entry — ever. Measured on the live file: 50 entries, 851 bytes
serialized (~17 bytes/id) — today this is genuinely negligible against the
15 MB total, unlike F1/F2/F3.

**Failure scenario:** a vault that is actively curated over years (deleting
stale test chats, experiments, etc. — a normal workflow, not an edge case)
accumulates one tombstone per delete, forever, with no expiry mechanism
anywhere in the codebase. At today's ~17 bytes/id this needs ~60,000
deletions to reach 1 MB, so it is not an urgent contributor on its own — I
am flagging it at P3 specifically because it is the *same defect class* as
F1 (a collection with a union-only merge and no corresponding prune/GC path)
and would compound if a future fix to F1/F2 starts routing more session
lifecycle events through tombstones.

### F5 — [P2, contested — flagging for red-team adjudication] `PLUGIN_SCHEMA.md:1308` says PDF context must never be written to `.curator/` without explicit approval; auto-attached PDF context is written into `.curator/sessions.json` on every send with no approval prompt

**Quoted spec text:** `docs/specs/plugin_schema/PLUGIN_SCHEMA.md:1308`,
under "PDF Quality Fields" rules: *"PDF context must never be written to
`.curator/` without explicit user approval."* The following two bullets
(`:1309–1313`) clarify: *"Normal chat over an open PDF must use viewer-local
page/selection/crop context first and must not require source registration.
Purple context chips and `Add to Incurator` are the durable refinement
controls: they register the source, create instant L1, and queue L2/L3 build
jobs."*

**What I measured against it:** `_sessionsPath` is literally
`.curator/sessions.json` (`main.ts:1564–1566`). `buildAutoContextRefs`
(`ChatSidebarView.ts:2095–2201`) auto-attaches PDF page context — including
full-resolution `imageBase64` for scanned pages (`:2187`) — to every message
sent while a PDF tab is open, with `sourceViewType: "auto"` (`:2182`), no
approval dialog, no opt-in click. That ref is persisted into
`.curator/sessions.json` on the very next `saveSessionData()` call. Read
literally, this is PDF context written into `.curator/` with zero explicit
approval, on the default/normal chat path the next two spec bullets describe
as *not* requiring source registration — which suggests the two rules may be
talking about different things (durable DAG registration vs. transient chat
session storage) without the spec ever saying so explicitly.

**Failure scenario, if the literal reading is intended:** a user having a
completely ordinary chat about an open PDF — never clicking "Add to
Incurator," never seeing a purple chip — nonetheless gets that PDF's
page image and text silently written into `.curator/sessions.json`, which
(per §2.2) is a file the spec itself says must tolerate multi-device sync —
i.e., this "not written without approval" content can propagate to every
synced device. I am marking this P2 rather than higher because the intent
is genuinely ambiguous from the surrounding text (the adjacent bullets read
as being about the L1–L4 DAG, not chat history) and because per ground rule
5 this counts as a finding either way — the spec and the artifact disagree,
or the spec is unclear enough that two reasonable readings produce opposite
verdicts, and it should be reconciled explicitly rather than left silent.

## Tests checked (ground rule 4)

- `sessionData.test.ts` (all 6 tests): covers id-based merge dedup,
  tombstone non-resurrection for **explicitly deleted** sessions, "keep
  newer copy" by `updatedAt`, and `filePath`/`backendStatus`/`revertData`
  sanitization. **Nothing exercises the 30-session eviction boundary** (F1)
  or cross-message content/image dedup (F2).
- `sessionStore.test.ts`: covers `missing`/`corrupt`/`unreadable`
  classification and concurrent-write atomicity — confirms the write path
  **is** safe under concurrency, which is why F3 is scoped to cost, not
  correctness.
- `mainSecurity.test.ts` ("Session sync path hygiene", `:183–198`): asserts
  `saveSessionData` uses the typed store and never calls
  `adapter.write(` directly — a wiring/regression guard, not a size or
  growth guard.
- `chatSidebarSource.test.ts:399–457`: pins `addContextRef`'s **pending
  queue** dedup (before send, comparing `imageBase64` to avoid double-adding
  the same manual attachment) and the vision-vs-non-vision
  `pendingCropBase64` resolution in `materializeContextRefs`. This is a
  different code path from `buildAutoContextRefs` (F2) and does not cover
  persisted cross-message duplication.

No existing test contradicts any finding above; none of the five findings
are already pinned as correct/intentional behavior.

## Summary of severities

| # | Finding | Severity |
|---|---|---|
| F1 | The 30-session cap is a no-op against the persisted file (verified by executing the real merge code) | P2 |
| F2 | Auto-attached file/image context re-embedded at full size on every send, zero cross-message dedup — 80% of file bytes | P2 |
| F3 | Every save is a full-file O(size) read×2/parse×2/clone/stringify cycle; 4 chained per message (~770 ms today, ~5 s projected at 100 MB) | P2 |
| F4 | `deletedSessionIds` unions forever, never pruned — same defect class as F1, currently negligible bytes | P3 |
| F5 | `PLUGIN_SCHEMA.md:1308`'s "never written without approval" vs. auto-attached PDF context landing in `.curator/sessions.json` unprompted | P2 (contested) |

F1, F2, and F3 share one root cause worth flagging to the synthesis debate
explicitly: **the persistence layer treats `sessions.json` as a small,
whole-file-serializable blob (correct for its original size) with no
incremental write path, no content-addressed dedup, and — despite one
visible attempt at a bound (the 30-session slice) — no mechanism that
actually survives the union-merge it is written through.** The atomicity and
multi-device-merge correctness work exactly as `PLUGIN_SCHEMA.md` §2.2
promises (and is well tested); nothing in this report contradicts that. The
gap is purely on the growth-bound axis, which the spec never promises a
number for and the code never enforces one.
