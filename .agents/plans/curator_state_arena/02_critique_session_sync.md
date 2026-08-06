# Red-Team Critique: `session_state` + `sync_journals`

Role: red-teamer. Goal: refute, not ratify. Read-only — no code, docs, config,
vault, or DB writes. This document is the only write. All measurements below
were re-derived independently against the live code and, where DB-backed, the
live read-only DB / live journal files — not copied from the inspector
reports.

Sources re-read in full: `plugin/src/utils/sessionData.ts` (94 lines),
`plugin/src/utils/sessionStore.ts` (115 lines), `plugin/main.ts:1560-1657`,
`plugin/src/ui/chat/ChatSidebarView.ts:1020-1160, 2095-2201, 4555-4650,
4739-4790`, `plugin/src/utils/sessionData.test.ts`,
`docs/specs/plugin_schema/PLUGIN_SCHEMA.md` (§1, §2.2, §6.1-6.2, line 52,
line 221), `backend/src/curator/db_sync.py` (in full, re-read the export/
import/autosync/maybe_auto_export/peer-file sections),
`backend/src/curator/ingest_worker.py:240-292`,
`backend/src/curator/commands/core.py` (`add`, `build`, `update`, `sync`),
`backend/src/curator/commands/db.py:99-154`, `backend/src/curator/db/schema.py`
(`query_traces`, `deleted_records` DDL), `docs/specs/curator_schema/SCHEMA.md`
§11.11.1, §11.12, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` §13.1-13.3.
Independently re-ran: a read-only query against
`file:/Users/shin/shinywings/Incurator/.cache/vaults/13ed51f8b06cb88e/state.sqlite?mode=ro`
for `deleted_records` table-name breakdown and `query_traces` size stats, and
`gzip -9` on the live `dev-28e419df29f2.jsonl`.

---

## SESSION F1 — "30-session cap is a provable no-op" — **CONFIRMED (P2)**

Traced the exact code path instead of trusting the inspector's synthetic
harness result:

- `persistCurrentSession()` (`ChatSidebarView.ts:4618-4635`) and
  `createNewChatSession()` (`:4559-4577`) both `.slice(0, 30)` the **local**
  `this.plugin.sessionData.chatSessions` array, then call
  `this.plugin.saveSessionData()`.
- `saveSessionData()` (`main.ts:1622-1630`) deep-clones and forwards to
  `writeSessionData` → `writeMergedSessionStore(adapter, path, snapshot)`
  (`sessionStore.ts:66-114`).
- `mergeSessionData(local, remote)` (`sessionData.ts:22-53`): line 29-31 does
  `for (const session of remote.chatSessions) { if (session?.id &&
  !deleted.has(session.id)) sessions.set(session.id, session); }`
  **unconditionally** — every session physically present on disk and not in
  the tombstone set is re-added, full stop. `local` (the 30-capped array) is
  then layered on top at line 33-37, but layering on top of a superset never
  shrinks it.
- **The decisive line I checked that the inspector didn't cite explicitly**:
  `sessionStore.ts:1642` in `main.ts` — `this.sessionData = await
  writeMergedSessionStore(...)`. After every save, the plugin's in-memory
  `sessionData` is **replaced by the merge result**, which re-includes the
  just-evicted session (it was still on disk, nothing tombstoned it). So the
  "cap" doesn't even hold locally past the next merge — the evicted session
  flows straight back into memory on the same tick that evicted it.
- Grepped every write site of `deletedSessionIds`: only
  `deleteChatSessionById` (`:4739-4745`) and `deleteCurrentChatSession`
  (`:4767-4779`), both explicit user-initiated deletes. Eviction via
  `.slice(0, 30)` never touches `deletedSessionIds`. Confirmed independently
  — I did not need to re-run the inspector's esbuild harness to see this; it
  falls directly out of reading the three files together.
- Test coverage: `sessionData.test.ts`'s "preserves remote sessions when
  saving local sessions" test (lines ~28-42) pins the **exact mechanism**
  that defeats the cap — it exists specifically so a session absent from
  `local` (because another device never had it, or here, because local
  evicted it) is NOT lost. No test exercises the 30-boundary. Confirmed gap.

**One correction to the inspector's framing, not the mechanism:** the merge
behavior itself is not a bug — `PLUGIN_SCHEMA.md:944` mandates it explicitly:
*"When synchronized, separate sessions from different devices must be
preserved."* The inspector's own summary already scopes this correctly
("atomicity and multi-device-merge correctness work exactly as
`PLUGIN_SCHEMA.md` §2.2 promises... The gap is purely on the growth-bound
axis"). I re-emphasize it here because it changes what a correct fix looks
like (below) — this is a **missing feature** (no eviction-safe pruning
primitive exists), not a defective merge algorithm that needs "fixing."

**The inspector's implied fix would be wrong if it's "tombstone on
eviction."** Reusing `deletedSessionIds` for silent, non-user-initiated
eviction would make an auto-evicted session **permanently and
irrecoverably** unmergeable on every synced device, including a device that
hasn't seen it yet or a user who scrolls the drawer looking for it later —
tombstones are defined (`sessionData.ts:24-26`, spec line 916) as permanent,
cross-device, no-undo. Silently tombstoning session #31 because the user
happened to click "New chat" 30 times is a data-loss footgun disguised as a
size fix.

**Better fix:** decouple "recency window for the UI drawer" (harmless, keep
`.slice(0, 30)` exactly as-is for display) from "storage bound" (the actual
problem). Two independent, non-destructive options, either or both:
1. Bound growth at the content level, not the session-count level — this is
   literally F2's fix target (dedup/trim `contextRefs`, which are 80% of
   bytes; a 30-session cap was never going to matter while `contextRefs`
   dominate). A session with resolved/trimmed context is cheap to keep
   forever.
2. If session-count bounding is still wanted, make it an explicit,
   user-visible archive action (not a silent side effect of "New chat"): a
   "clear old sessions" affordance that routes through the *same* explicit
   `deletedSessionIds` tombstone path as manual delete, so the user opts in
   knowingly instead of double 30-click roulette.

---

## SESSION F2 — auto-attached context, zero cross-message dedup — **CONFIRMED (P2)**

Re-read `buildAutoContextRefs` (`ChatSidebarView.ts:2095-2201`) directly.
Confirmed line-for-line: `finalContent`/`imageBase64` are rebuilt at full
size from the live open-tab state on every call (no cache keyed on
file+content-hash anywhere in the function or its caller); `seen`
(`:2101,2193-2196`) is a `Set` local to the function invocation, provably
scoped to one call by JS closure semantics — it cannot dedup across the two
calls in the same `sendMessage()` (`:1052` chip-render, `:1125` final), let
alone across different messages. Confirmed call sites at both line numbers
the inspector cited. No further correction needed; this finding is solid as
stated.

---

## SESSION F3 — 4 chained full read/parse/merge/stringify cycles per send — **CONFIRMED, but the inspector's own arithmetic UNDERCOUNTS the cost (severity holds at P2, possibly conservative)**

### Call count: verified "4" is correct for the common path, not a double-count

Re-read `handleSend()` (`ChatSidebarView.ts:1023-1158`) directly:
- `:1067` — after user message push.
- `:1085` — after streaming placeholder push.
- `:1129` — after context refs are materialized (**only reached on the
  non-git, LLM-answer path** — the `gitCommand` branch returns early at
  `:1110` after its own third save at `:1108`, so a Git sidechat command
  triggers **3** saves, not 4).
- `:1155` — in the `finally` block.

So "4" is accurate specifically for a normal LLM-answered message (the
majority case); a Git-sidechat message is 3. The inspector's text says
"sendMessage chains four of them" without carving out the git-branch
exception — technically imprecise but not a double-count, and the more
common path is exactly 4 as claimed.

### Debounce/batching: confirmed absent

`saveSessionData()` (`main.ts:1626-1628`) chains onto
`this.sessionPersistPromise` and `writeMergedSessionStore`'s per-path queue
(`sessionStore.ts:71-113`) — both are **serialization** queues (prevent
concurrent corruption), not debounce/coalescing queues. Every call still
executes its own full round trip; nothing is dropped or merged with a
sibling call. Confirmed off any explicit "hot path" exemption — there is no
special-cased lightweight save anywhere in this file.

### The cost model itself: I recomputed it and it's **short**, not right

I traced every `JSON.parse`/`JSON.stringify`/disk-read call in one
`saveSessionData()` invocation, which the inspector's own formula
undercounts by missing two full round trips:

1. `main.ts:1623-1624` — `JSON.parse(JSON.stringify(this.sessionData))`:
   1 stringify (compact) + 1 parse. *(inspector counted this — "1 deep
   clone.")*
2. `sessionStore.ts:73-75` — `parseSessionStoreText(JSON.stringify(
   sanitizeSessionDataForSync(local)))`: **another** full stringify
   (compact) + parse, over the *same* already-cloned object, purely to
   re-validate/re-sanitize it into `localSnapshot`. **The inspector's
   report never mentions this line.** It is a second, complete,
   structurally redundant deep-clone pass — `snapshot` passed in from
   `main.ts` is already the output of `normalizeSessionData`, which already
   calls `sanitizeSessionDataForSync` internally (`sessionData.ts:3-9`), so
   this second sanitize+stringify+parse is 100% redundant work done on
   every single save, not just occasionally.
3. `readSessionStore` → `readJsonObjectState` (disk read #1) +
   `parseSessionStoreText` (parse). *(inspector counted the read, undercounts
   parses — see below.)*
4. `adapter.process(path, fn)`: Obsidian's own internal disk read (read #2)
   + `fn`'s `parseSessionStoreText(currentRaw)` (parse) + the pretty
   `JSON.stringify(..., null, 2)` that becomes the atomically-written bytes.
   *(inspector counted this correctly as "1 full pretty-stringify.")*
5. `sessionStore.ts:103-107` — `result = parseSessionStoreText(committedRaw)`:
   **a fifth parse**, of the just-written text, purely to hand back a fresh
   `SessionData` object as the plugin's new `this.sessionData`. **Also not
   in the inspector's formula.**

Total real ops per `saveSessionData()`: **2 disk reads, 5 full `JSON.parse`
calls, 3 full `JSON.stringify` calls** (2 compact, 1 pretty). The inspector's
formula ("34.0×2 + 21.5×2 + 46.3 + 34.8 ≈ 192ms") accounts for 2 reads, 3
parses (1 inside "clone," 2 explicit), 2 stringifies (1 inside "clone," 1
pretty) — it is missing exactly the `localSnapshot` round trip (item 2:
≈32.6+21.5 = 54.1ms) and the final `committedRaw` reparse (item 5: ≈21.5ms),
**≈75.6ms per call unaccounted for**. Using the inspector's own measured
per-op timings:

```
2 reads:              34.0 × 2  =  68.0 ms
5 parses:              21.5 × 5 = 107.5 ms
2 compact stringifies: 32.6 × 2 =  65.2 ms
1 pretty stringify:    34.8 × 1 =  34.8 ms
                                 ---------
                                  275.5 ms  per saveSessionData()  (not 192ms)
```

At 4 calls per send: **≈1,102 ms**, not the reported "~770ms" — a ~43%
undercount. This does not weaken the finding; if anything it strengthens it
(the true synchronous-block cost today is worse than reported, and the
projection to 100 MB scales the same way, proportionally worse too — closer
to 7s than 5s). **Verdict: CONFIRMED, P2, with a corrected/higher cost
estimate.** The stated fix direction (need an incremental write path) is
right, but I'd add a concrete, immediately-available partial fix the
inspector didn't surface: **drop the redundant `localSnapshot`
re-stringify/re-parse in `sessionStore.ts:73-75`** — since `local` arriving
into `writeMergedSessionStore` is already a normalized+sanitized clone from
`main.ts:1623-1624`, that second round trip can be replaced with a direct
(cheap, no serialization) object copy or even used as-is, cutting ~54ms
(≈20%) off every save with no architecture change, before the harder
incremental-write work is undertaken.

---

## SESSION F5 — PDF-context-in-`.curator/` spec conflict — **ADJUDICATED: REFUTED as a literal-reading violation; DOWNGRADED to P3 (spec-clarity gap, not a contract violation)**

This is the one item the briefing asked me to definitively resolve, not just
score. I read `PLUGIN_SCHEMA.md` §1 (lines 42-75), §2.2 in full (876-962),
and §6.2 in full (1286-1360), plus grepped every other place the doc uses
the string `.curator/`.

**The decisive evidence is `PLUGIN_SCHEMA.md:52`**, in the "Plugin Authority
Boundary" list (§1), which the inspector's report never cites:

> - `SessionData` — stored separately in `sessions.json`; may be synced
>   through Syncthing when session merge-on-save is enabled...
> - ...
> - Transient PDF.js extraction for open documents **(never written to
>   `.curator/`)**

This is the spec's own author drawing the exact line the inspector's finding
turns on, in the same document, in the section whose entire job is to
enumerate what the plugin owns and where it's allowed to write. It lists
**`SessionData`/`sessions.json`** and **"transient PDF.js extraction"** as
two *separate* bullets with *different* persistence rules. "PDF context"
under discussion at line 1308 (the `PdfTextQuality`/PDF-viewer-technical
extraction machinery in §6.2) is downstream of that second bullet — the raw
PDF.js parse/render pipeline, not the `ContextRef` objects that get attached
to a chat message and persisted via §2.2's `SessionData` path.

Corroborating evidence from the immediate surrounding bullets at §6.2
(1302-1320), read as one policy statement rather than in isolation:

- `:1308` "PDF context must never be written to `.curator/` without explicit
  user approval."
- `:1309-1313` "PDF viewer chat and durable PDF knowledge refinement are
  separate workflows. Normal chat over an open PDF must use viewer-local
  page/selection/crop context first and must not require source
  registration. Purple context chips and `Add to Incurator` are the durable
  refinement controls: they register the source, create instant L1, and
  queue L2/L3 build jobs."
- `:1318-1320` "Provider-context assembly must never import/register an
  untracked PDF as a side effect. Passive viewing and read-only backend
  fallback leave source rows, reference stubs, CTX pages, assets, and
  ingest jobs unchanged."

Bullet 1318-1320 is the *backend-DAG* restatement of bullet 1308 in
concrete terms: source rows, CTX pages, ingest jobs — i.e. `.curator/
Collections/`, `.curator/state.sqlite`-backed registration. Bullet 1308 is
the same rule stated once, generically, at the top of the same run of
bullets. If 1308 meant "chat session storage," it would flatly contradict
1310-1313 in the very next sentence, which says normal chat "must not
require source registration" and describes precisely the
`sourceViewType: "auto"` behavior the inspector flagged — the spec cannot
simultaneously mandate that normal chat needs no approval AND that normal
chat's context needs approval before being written to `.curator/`. Reading
1308 as scoped to durable DAG registration removes the contradiction
entirely; reading it as scoped to session storage creates one. The
"transient PDF.js extraction (never written to `.curator/`)" boundary item
at line 52 additionally confirms the doc's author does distinguish, in this
exact document, between raw/ephemeral PDF technical state and the persisted
`SessionData`/`ContextRef` object that carries PDF page content into chat
history — the latter is explicitly allowed to persist (§2.2's rules,
940-957, describe unconditional persistence rules for `ContextRef` with
zero mention of an approval gate).

**Verdict:** the literal "auto-attached PDF context violates 1308"
reading is **refuted** — 1308 is about durable backend/DAG registration
("written to `.curator/`" = registered into the knowledge base), not the
physical `.curator/sessions.json` file. Code conforms to spec on this axis.
What I do **not** refute, and where I side with the inspector's underlying
instinct: the term "written to `.curator/`" is genuinely overloaded in this
document — it's used as shorthand for "durably registered in the knowledge
base" at 1308/1318, but used **literally** to mean the physical directory
at line 221 ("plugin `data.json`, and `.curator/sessions.json` contain no
absolute locator") and line 50 (`.curator/zotero_profiles.json`). A spec
that uses the same phrase to mean two different things in the same document
is a real defect — just a **documentation clarity defect (P3)**, not the
P2 contract violation the inspector filed it as. **Fix:** reword line 1308
to name the scope explicitly, e.g. "PDF content must never be
auto-registered as a tracked source (source row, CTX page, ingest job)
without explicit user approval" — removing the ambiguous "`.curator/`"
shorthand from this specific bullet while leaving the correct, literal usage
at lines 50/221 untouched.

---

## SYNC F1 — full uncompressed snapshot on every mutating command; 9.86× unused — **CONFIRMED as a real, worse-than-stated problem; the "every mutating command" framing needs a precision correction**

### Compression measurement: independently reproduced, exact match

Ran `gzip -9 -c dev-28e419df29f2.jsonl | wc -c` on the live file myself:
**1,663,943 bytes**, vs. the source's 16,402,744 bytes = **9.857×**,
matching the inspector's 9.86× to 3 significant figures. Confirmed
`export_knowledge()`'s `compress` param (`db_sync.py:686,712-715`) and that
`export_for_device()` (`:1465-1492`) calls `export_knowledge(db_path, out)`
with no `compress` kwarg (`:1485`) — defaults `False`. Confirmed
`commands/db.py:30,41,44` is the only caller that ever passes
`compress=True`, and that's the manual `wiki db export --compress` path,
never invoked by autosync/CLI-hook/plugin triggers. This part of the
finding is solid.

### "Every mutating command": traced actual call sites — the real mechanism is *more* frequent than the inspector's framing implies, and it isn't the CLI hook they mostly attributed it to

I read `commands/core.py`'s `add`, `build`, `update`, `sync` in full, plus
`ingest_worker.py:240-292`.

- `wiki add` (`core.py:608-770`): processes **all** pending sources in one
  synchronous loop (736-762), then calls `_maybe_auto_export(paths)`
  **once**, at the very end (`:770`). Matches the inspector's claim exactly
  for this command.
- `wiki build` (`core.py:777-897`) — **this is where the inspector's
  framing breaks down.** The *default* invocation (no `--wait`, which is
  the common case per the docstring: "By default the work is queued to the
  background worker") hits `enqueue_l2_l3_for_sources(...)` and **returns
  immediately at line 850 without ever calling `_maybe_auto_export`.**
  There is no CLI-hook export for default `wiki build` at all. The export
  the inspector measured instead comes from a **different, uncited call
  site**: `ingest_worker.py:282`, inside `run_next_job`'s `finally` block —
  `db_sync.maybe_auto_export(paths)` fires **once per individual queued
  job**, not once per CLI command. `run_queued_jobs` (`:293-308`) loops
  `run_next_job` until the queue drains, so a `wiki build` that queues, say,
  6 L2/L3 jobs and is later drained by `wiki jobs run` or an active MCP
  worker triggers **up to 6 separate exports**, each independently gated by
  `local_has_unexported_changes()` (`db_sync.py:1658-1672`) — and since
  every job mutates job-status/page rows and therefore bumps some table's
  `updated_at` past `last_export_ts`, that gate will almost always pass, so
  in practice most/all of those 6 jobs really do trigger their own full
  snapshot write. `--wait` mode (`:852-897`) is the only `build` path that
  matches the inspector's "once, at command end" model, and `--wait` is the
  *non-default* option.
- `wiki update`/`wiki sync` (`:900-1319`): each calls `_maybe_auto_export`
  once at the relevant point(s) in its own synchronous flow — matches the
  inspector's claim.

**Net correction:** "every mutating command" undersells the frequency for
the single most common growth path (`wiki build` → background worker
draining a job queue) — the real trigger density there is *per completed
job*, via `ingest_worker.py:282`, a call site the inspector's report never
names. This makes the finding **worse**, not weaker: a vault doing active
L2/L3 build work via the background worker (the default, recommended path
per the command's own docstring) can produce many more full-snapshot writes
per user-visible "build" action than the "once per command" model suggests.
**Verdict: CONFIRMED, P2, severity if anything understated; cite
`ingest_worker.py:282` alongside the CLI hook as the dominant real-world
trigger.**

### Would enabling `compress=True` on `export_for_device` "just work"? — No. Verified it would break both same-fleet compatibility and rolling upgrades if flipped naively

This is the part of F1 the inspector's report leaves as an implied freebie
("a 9.86× compression win sitting unused") without checking the consumer
side. I traced the read path:

- `export_knowledge(out_path, ..., compress=True)` writes gzip bytes but
  **does not rename the output** — the caller (`export_for_device`) still
  constructs `out = sync_dir / f"dev-{device_id}.jsonl"` (`:1484`), a
  literal `.jsonl` name, regardless of `compress`. Nothing in
  `export_knowledge` enforces a `.gz`-suffixed name for compressed output.
- Every reader gates gzip-vs-plain-text **purely by filename suffix**, never
  by content sniffing: `_read_export_id` (`db_sync.py:1526-1527`,
  `if path.suffix == ".gz"`) and `import_knowledge` (`:800-801`, identical
  check). A file named `dev-xxx.jsonl` containing gzip binary would be
  opened with plain-text `open(..., encoding="utf-8")` by both functions,
  which raises a `UnicodeDecodeError` (caught as `ValueError` in
  `_read_export_id`, surfaced as an `AutosyncError`) — i.e. **every peer,
  including a peer running the exact same code**, fails to read the file at
  all unless the naming is fixed in lockstep with the `compress` flag.
- `_peer_files()` (`:1495-1514`) globs `sync_dir.glob("dev-*.jsonl")` — this
  pattern does **not** match `dev-xxx.jsonl.gz` (glob is a literal suffix
  match, not "starts with `dev-` and ends with content resembling jsonl").
  So even after fixing the naming to `dev-xxx.jsonl.gz`, the **peer
  discovery step itself** needs a matching update, or compressed files
  become invisible to `_peer_files()` and are silently never imported by
  anyone — a second, independent way to reproduce exactly the "stale peer,
  zero signal" failure mode SYNC F4 already documents, this time
  self-inflicted by the compression rollout rather than a stale device.
- **Rolling-upgrade hazard**: `.curator/sync/` is a Syncthing-replicated
  directory read by every device in the fleet, which — unlike a
  single-writer server upgrade — cannot be atomically flipped to a new
  format across all peers at once. A naive `compress=True` flip is the same
  class of hazard the existing `schema_version` gate
  (`SYSTEM_BEHAVIOR.md:1293-1295`) was built to handle for schema changes,
  but there is currently no equivalent negotiation for *transport encoding*
  — only for *row schema*.

**Verdict on the sub-question: CONFIRMED that gzip is not a safe drop-in.**
**Better fix:** don't flip a global default. Either (a) name compressed
output `dev-{device_id}.jsonl.gz` unconditionally going forward, widen
`_peer_files()`'s glob to `dev-*.jsonl*` (matching both extensions) so old
and new-format peers are mutually discoverable, and let `_read_export_id`
/`import_knowledge`'s existing suffix check handle the rest (this is nearly
free — both already branch on `.gz`, only the writer + peer-discovery glob
need to change) — this is safe for a rolling upgrade because a device that
hasn't upgraded yet simply won't find peer `.gz` files with today's glob,
which degrades to "stale peer, same as any old device" (already a known,
albeit under-signaled, failure mode) rather than a hard crash; or (b) gate
compression behind the same `schema_version` bump machinery so an old
device explicitly knows to skip a peer file it can't decode instead of
silently missing it via glob non-match. Given the code for (a) is a
5-10-line change once the glob and one write-site update are done, (a) is
the pragmatic fix; the write-up should not imply it's a bare `compress=True`
toggle.

---

## SYNC F3 — `query_traces` up to 186 KB/row, 22.5% of journal bytes at 57 rows — **CONFIRMED, and independently sharpened into a stronger, differently-scoped finding: this table is misclassified relative to its own documented sibling tables**

### Numbers: independently reproduced against the live read-only DB

```sql
SELECT COUNT(*), MIN(...), MAX(...), AVG(...) FROM query_traces
```
against `file:.../state.sqlite?mode=ro` returned **57 rows**,
column-length-sum range **1,900–166,189 bytes**, avg **57,269** — consistent
with the inspector's JSONL-row byte range (2,768–186,240, median 52,366; the
JSONL figures are larger because they include the `{"type":"row","table":
"query_traces","row":{...}}` wrapper and every other column, not just the
two JSON blob columns I summed). Same order of magnitude, same conclusion:
a handful of rows dominate. Confirmed real.

### Is "should it be in the sync payload at all" the sharper finding? — Yes, and I can now ground it in evidence the inspector's report didn't cite

`docs/specs/curator_schema/SCHEMA.md` §11.12 ("Search Engine Tables",
1272-1287) explicitly classifies `query_traces` alongside
`search_documents`, `search_chunks`, `search_embeddings`, and
`search_index_meta` as **"derived retrieval state in repo-cache
`state.sqlite`... must be rebuilt from Curator records by `wiki
reindex`."** And `db_sync.py`'s own `EXCLUDE_TABLES`
(`:67-79`) confirms the *other four* members of that exact same documented
group — `search_embeddings`, `search_index_meta`, `search_documents`,
`search_chunks`, `search_documents_fts*` — are all excluded from sync as
"tables that must never appear in an export file." `query_traces` is the
**one member of its own documented category that isn't excluded**, and is
instead the single largest contributor to journal bytes (22.5% from 0.2% of
rows).

**But I also checked the "just exclude it" instinct and it's not quite
right either** — I read `wiki reindex`'s actual implementation
(`commands/core.py:1486-1539`, `materializer.materialize_search_documents`)
and it **only rebuilds `search_documents`/`search_chunks`/embeddings — it
never touches `query_traces` at all.** So despite SCHEMA.md §11.12 grouping
it with the rebuildable search tables, `query_traces` is **not actually
regenerable**; it's an append-only historical log of real `wiki query`
retrieval traces (route, ranking, evidence). SCHEMA.md §11.11.1's
"Synthesis Audit Payload" (1221-1258) hydrates `query_trace` by `trace_id`
for `kind="answer"` audits of synced `SYN-`/community-report artifacts —
meaning a trace generated on Device A is a legitimate, load-bearing part of
Device B's ability to audit a synced synthesis node's evidence trail if
Device B never ran that query itself. That's the plausible reason it's in
`SYNC_TABLES` today, and outright exclusion would silently degrade that
audit feature on peer devices (though gracefully — SCHEMA.md:1263 confirms
"Missing references are represented as warning strings," not a hard
failure, so this degradation is safe, just lossy).

**Verdict: CONFIRMED, P2, and the "wrong table classification" angle is the
sharper root cause** — but the correct fix is **retention/truncation, not
blanket removal from `SYNC_TABLES`.** Concretely: either (a) cap
`query_traces` export to the N most recent rows per workspace (or rows
still referenced by a live `artifact_dependencies`/`synthesis_nodes` row,
pruning the rest) while keeping `deleted_records`-driven tombstone
propagation so old rows age out of every peer's copy too, or (b) split the
row at export time — sync the lightweight identity/metadata columns
(`trace_id`, `workspace_id`, `route`, `created_at`, id-list columns) needed
for audit-payload hydration but exclude the two heavy blob columns
(`retrieval_trace_json`, `evidence_json`, which are the actual 22.5%) from
the cross-device payload, keeping them device-local only. Either preserves
the audit-linkage use case this table is actually serving while fixing the
measured byte problem; a bare "move to `EXCLUDE_TABLES`" copy-pasted from
the four sibling search tables would be the wrong fix here specifically
because, unlike those four, this one isn't reindex-regenerable.

---

## SYNC F2 — `deleted_records` tombstones never expire, 33% of rows, re-ingestion-driven — **CONFIRMED, no correction needed**

Independently reproduced the exact table-name breakdown against the live
read-only DB:

```
source_spans      8696
source_pdf_pages   673
claim_supports     199
artifact_dependencies 5
synthesis_nodes      3
sources              1
source_pages         1
```

Matches the inspector's numbers exactly (I ran the query myself, not copied
theirs). Also independently confirmed `source_spans` live count = 2,363,
matching the cited 3.7:1 dead:live ratio math. Grepped `db_sync.py` for
`DELETE FROM deleted_records` and found the same two call sites the
inspector cites (`:539`, `:1259`), both undelete-only, no age-based purge
anywhere. No refutation available; this finding stands as filed at P2. The
inspector didn't propose an explicit fix; a reasonable one given
`SYSTEM_BEHAVIOR.md:1259-1261`'s full-snapshot design is a tombstone
retention window keyed off `deleted_at` age *once all known peers have
confirmed import past that timestamp* (recorded per-peer high-water marks
already exist in `sync_state.json`'s `peers` map, `db_sync.py:1584-1585` —
this is close to being wired for exactly this purpose already) rather than
an unconditional age cutoff, which would risk dropping a tombstone before a
long-offline peer has ever seen it.

---

## SYNC F4 — stale schema-mismatched peer file silently orphaned, zero signal — **CONFIRMED, no correction needed**

Re-read `_read_export_id` (`db_sync.py:1517-1563`) and `import_all_peers`
(`:1566-1609`) directly: schema mismatch → `logger.info(...)` (not raised)
→ `return None` → caller does `if export_id is None: continue` — the file
name never enters `results`. Re-read `commands/db.py:99-154`'s
`db_autosync` directly: `summary["imported_files"] = len(res.imported)` —
since the skipped file was never added to `res.imported`, it's invisible to
both the human-readable line and the `--json` output; there is no "N peer
file(s) skipped" message anywhere in this function or in
`AutosyncResult`. Confirmed the older file's actual state independently via
`ls -la` on the live `.curator/sync/` directory: `dev-bd8d7f0753da.jsonl`,
schema_version 12, last written 2026-07-19 — genuinely stale relative to
the newer file's 2026-08-06 v13 export, exactly as claimed. No refutation
available. Fix direction proposed by the inspector (surface a "skipped"
line) is correct and sufficient; I'd add that the skip reason (schema
version delta) should be included in that line since it's already computed
and discarded at `logger.info` level.

---

## SYNC F5 — spec silent on lifecycle/retention at 24 MB scale — **CONFIRMED as a fair observation, P3 holds**

Read `SYSTEM_BEHAVIOR.md` §13.1-13.3 in full. Confirmed: full-snapshot
semantics, conflict resolution, schema gate, loop prevention, triggers, CLI
hook, export gate, dry-run, Syncthing conflict files, and device-local sync
state format are all documented in real detail — and none of compaction,
tombstone GC, per-table size/row bounds, or peer-file staleness
signaling appear anywhere in that range. This is consistent with what F1-F4
above independently establish are the actual code gaps, so the spec's
silence is accurately characterized, not overstated. No refutation; P3 is
the right severity since (per the briefing's own rule 5) this is a
documentation-completeness finding riding on top of already-filed P2 code
findings, not an independent contract violation.

---

## SESSION F4 — `deletedSessionIds` never pruned — **CONFIRMED, P3 holds**

Re-read the two union-only write sites (`ChatSidebarView.ts:4743-4745,
4777-4779`) and `mergeSessionData`'s union (`sessionData.ts:24-26`)
directly; grepped for any read site that ages out or caps entries and found
none. Inspector's own severity framing (negligible today, same defect class
as F1, would compound only if F1/F2 fixes route more lifecycle events
through tombstones) is accurate and appropriately conservative — I have no
correction to offer here. Confirmed as filed.

---

## Verdict Table

| # | Finding | Inspector severity | Red-team verdict | Notes |
|---|---|---|---|---|
| SESSION F1 | 30-session cap is a no-op on disk | P2 | **CONFIRMED** (P2) | Mechanism verified via direct code trace (not the inspector's harness); merge behavior itself is spec-mandated, not buggy — gap is a missing eviction-safe pruning primitive. Proposed "tombstone on evict" fix would be actively harmful (permanent cross-device data loss); better fix is content-level bounding (F2) or an explicit user-initiated archive action. |
| SESSION F2 | Auto-context re-embedded, zero cross-message dedup, 80% of bytes | P2 | **CONFIRMED**, no correction | Verified `buildAutoContextRefs` directly; `seen` Set is provably call-scoped. |
| SESSION F3 | 4 chained full R/P/M/S cycles per send, ~770ms | P2 | **CONFIRMED, cost UNDERSTATED** | Real op count is 2 reads / 5 parses / 3 stringifies per save (inspector counted 2/3/2) — true cost ≈275ms/save, ≈1.1s/send, not 192ms/770ms. Found one concrete free win the inspector missed: the redundant `localSnapshot` re-stringify+re-parse in `sessionStore.ts:73-75` (~54ms/save, ~20%) is removable today with no architecture change. |
| SESSION F5 | PDF-context-in-`.curator/` spec conflict | P2 (contested) | **REFUTED as a violation; DOWNGRADED to P3** (spec-clarity gap) | Adjudicated using `PLUGIN_SCHEMA.md:52`'s explicit "SessionData" vs. "transient PDF.js extraction (never written to `.curator/`)" split — literal reading of 1308 would contradict 1310-1313 in the same bullet list. Rule scopes to durable DAG/source registration, not chat/session storage. Code conforms; the doc's overloaded use of "`.curator/`" (literal path at :221 vs. shorthand for "the knowledge base" at :1308) is the real, lower-severity defect. |
| SYNC F1 | Full uncompressed snapshot every mutating command; 9.86× unused | P2 | **CONFIRMED, frequency UNDERSTATED; compression fix is not a free flip** | `wiki build`'s default (non-`--wait`) path does NOT export via the CLI hook at all — real trigger is `ingest_worker.py:282`, once per completed queued job, uncited by the inspector, and likely fires more often than "per command." Independently reproduced the 9.86× gzip ratio exactly. Verified naive `compress=True` breaks import: filename stays `.jsonl` while content becomes gzip, both readers gate strictly on `.gz` suffix, and `_peer_files()`'s glob (`dev-*.jsonl`) won't discover a renamed `.jsonl.gz` file either — needs a coordinated writer-rename + glob-widen, not a one-line toggle. |
| SYNC F2 | `deleted_records` never expire, 33% of rows | P2 | **CONFIRMED**, no correction | Table-name breakdown and live `source_spans` count independently reproduced against the live DB, exact match. |
| SYNC F3 | `query_traces` unbounded, 22.5% of bytes at 57 rows | P2 | **CONFIRMED, and sharpened** | Row-size stats independently reproduced. Grounded the inspector's own suggested "sharper finding" in hard evidence: SCHEMA.md §11.12 classifies `query_traces` alongside 4 sibling tables that are ALL in `EXCLUDE_TABLES` — it's the one outlier still fully synced. But verified it is NOT reindex-regenerable (unlike its siblings) and IS load-bearing for cross-device synthesis-audit hydration (§11.11.1) — so the correct fix is retention-capping or blob-column truncation at export time, not blanket exclusion. |
| SYNC F4 | Stale schema-mismatched peer silently orphaned | P2 | **CONFIRMED**, no correction | Mechanism and live file staleness (v12, 2026-07-19) independently reproduced. |
| SYNC F5 | Spec silent on retention/lifecycle at scale | P3 | **CONFIRMED**, no correction | Read §13.1-13.3 in full; the described gaps are real and match F1-F4. |
| SESSION F4 | `deletedSessionIds` unbounded union, same defect class as F1 | P3 | **CONFIRMED**, no correction | Union-only write sites verified directly; no read site ages out entries. |

**Findings surviving to synthesis, unchanged in substance:** SESSION F2,
F4; SYNC F2, F4, F5 (5 findings, no corrections needed beyond confirming).

**Findings surviving with a corrected severity, cost model, or root-cause
scope (the debate should use my corrected version, not the original):**
SESSION F3 (cost is higher than stated, + one free fix identified), SYNC F1
(trigger mechanism is per-job not per-command, + compression fix requires
coordinated changes, not a flag flip), SYNC F3 (root cause reframed as
category misclassification vs. its own documented sibling tables, fix must
be retention/truncation not exclusion).

**Findings overturned:** SESSION F5 — the literal "spec violation" reading
is refuted by the spec's own line 52 and by the internal contradiction it
would otherwise create with lines 1310-1313; it survives only as a P3
wording-clarity item, not a P2 contract violation.

**One finding I'd add for the synthesis debate to consider (not in either
proposal, surfaced as a byproduct of verifying SESSION F1):** the "cap"
pattern (local truncation feeding into an always-preserving remote-union
merge) is a design footgun that could recur anywhere the plugin tries to
bound a synced collection client-side without a corresponding
server-authoritative bound — worth a one-line callout in the synthesis so a
future contributor doesn't reach for the same `.slice(N)` pattern to "fix"
`contextRefs` growth (F2) the same broken way.
