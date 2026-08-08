# Changelog

All notable changes to Incurator are documented here.

## [0.50.2] - 2026-08-08
### Fixed
- **Device Sync State Was An Unlocked Read-Modify-Write** (B2 / sync_db-4)
  Four sites read the local sync-state file, mutated it, and wrote it back with
  no lock, so two concurrent passes could interleave. Both consequences were
  reproduced against the real code:

  - **Split device identity.** `get_device_id` mints an id when none exists.
    Racing callers each minted a different one — measured: two callers received
    two ids while only one was persisted. The loser then exports as
    `dev-<its-id>.jsonl`, and every other device imports a peer that exists only
    as that filename and never exports again. A permanently stale phantom.
  - **Lost update.** Two sections read the same base and the last writer wins.
    Losing `peers` forgets a checkpoint, so that peer's entire snapshot
    re-imports on the next pass; losing `last_export_ts` re-fires the export
    gate.

  All mutation now goes through `sync_state_transaction`, which holds
  `durable_io.locked_path` on the state file, re-reads inside the lock so a
  caller can never act on a copy captured before acquiring it, and writes once
  through `atomic_write_text` on a clean exit. A failed pass leaves the file
  untouched.

  This also removes a hazard that was previously handled by remembering to order
  two calls: `import_all_peers` had to call `get_device_id` before snapshotting
  state, or a first-run identity would be clobbered by the checkpoint write. The
  ordering requirement is now structural.

  On platforms without `fcntl` the lock degrades to a thread lock, so separate
  processes are not serialized there. Recorded rather than assumed away — it is
  strictly narrower than the unlocked behavior it replaces.

- **Nested State Locking Deadlocked, Then Lost Writes**
  Found while reviewing the change above; both were introduced by it.

  `durable_io.locked_path` was not re-entrant. `flock` is per file descriptor,
  so a nested acquisition opened a second descriptor and `LOCK_EX` blocked
  against the first — from the same process, forever. A hang, not an error, and
  reachable: `_peer_files` calls `get_device_id` (now a transaction) whenever no
  id is passed, and is itself called from inside `import_all_peers`' transaction.
  It survived only because that one call site happens to pass the id.

  Making the lock re-entrant then exposed a second fault: a nested
  `sync_state_transaction` read its own copy of the state, and the outer
  transaction overwrote it on exit with the snapshot taken before nesting —
  discarding a freshly minted `device_id` and failing validation. That is the
  lost update this whole change exists to prevent, reintroduced by nesting.

  The lock now tracks re-entrancy depth per thread and path, taking `flock` only
  at the outermost acquisition; and a nested transaction shares the outer
  state dict, with the outermost `with` committing once.

## [0.50.1] - 2026-08-08
### Fixed
- **`SCHEMA_SQL`'s `sources_set_sync_key` Was A No-Op** (B2 / sync_db-2)
  The trigger was written twice — once inline in `SCHEMA_SQL`, once in
  `_refresh_current_triggers` — and the two drifted. The `SCHEMA_SQL` copy spelled
  the path separator `'\'` inside a non-raw Python string, so the escape ate the
  backslash and the body became `replace(NEW.relpath, '', '/')`. Replacing an
  empty string is a no-op, so a Windows-style path was never normalized.

  `_triggers_need_refresh` could not catch it: it matched a substring
  (`NEW.sync_key IS NULL OR NEW.sync_key = ''`) that the BROKEN body also
  contains, so a database carrying the no-op reported "current" and kept it.
  Verified: a database built from raw `SCHEMA_SQL`, then reopened through
  `db.connect()`, still held the no-op.

  `sync_key` is the cross-device transport identity, so a source registered
  under that body gets `vault:04_Resources\win\a.md` instead of `.../win/a.md`
  and can never match its counterpart on another OS — and only the trigger
  self-heals on reopen, never the rows.

  The three managed triggers now have ONE definition (`TRIGGER_BODIES`) rendered
  into both install paths, with the separator built from `chr(92)` so no escape
  can eat it again, and `_triggers_need_refresh` compares the rendered body
  instead of a substring allowlist.

  No vault is affected in practice: `init_db` calls `_refresh_current_triggers`
  unconditionally, so every vault created the normal way already had the correct
  trigger. The reporting vault has it, with 0 of 36 sources carrying a backslash
  in `sync_key`.

  SCHEMA now states what happens to a key that was already derived wrongly: it
  is **never rewritten**. `sync_key` is the identity peers match on, so a
  retroactive repair on one device and not another would split the source
  instead of converging it. The trigger self-heals on open; the rows do not, and
  correcting them is a deliberate cross-replica action.

## [0.50.0] - 2026-08-08
### Fixed
- **An Import Reported Rows It Had Silently Dropped** (B2 / sync_db-1)
  This is B2's stated hard condition, and it was violated. `_do_insert` used
  `INSERT OR IGNORE`, so a row the database refused — a truncated or malformed
  peer export — was discarded while `_lw_upsert` still returned `inserted` and
  the caller incremented `stats.inserted`. Reproduced directly: importing one
  valid row and one constraint-violating row stored **1** row and reported
  **2 inserted**.

  `INSERT OR IGNORE` stays, but not for the reason it looks like: callers look
  the row up by transport key first, so an identical row never reaches the
  INSERT twice. What it absorbs is a UNIQUE constraint the key lookup cannot
  see. The insert now reports which of the three happened — stored, already
  present under another identity, or refused — and only the last is counted as
  `rejected`.

  That distinction matters more than the original bug. `graph_entities` is
  UNIQUE on `(canonical_name, entity_type)` and `source_spans` on
  `(source_id, content_hash)`, while both transport on a surrogate `id`, so two
  devices that independently extract the same entity mint different ids and
  collide on content. The row is already present; calling that a refusal would
  have fired on every sync forever, since the ids never reconcile.

  Classification asks the schema (`PRAGMA index_list`) which UNIQUE index
  collided, mirroring SQLite's semantics — NULLs are DISTINCT, and a partial
  index applies only to rows matching its predicate. Where it cannot decide, the
  row is reported as refused: over-reporting a loss is recoverable,
  under-reporting one is the silence this feature exists to remove.

  A refused `sources` row no longer raises. It used to, and nothing catches per
  row, so one malformed source rolled back every well-formed row in the file and
  never checkpointed the peer — re-failing on every retry. Its child rows are
  counted as refused too, since nothing can attach them to a parent that is not
  there.

### Added
- **`rejected` In Import Reporting**
  `ImportStats.rejected`, the `wiki db import` summary and its `--json` output,
  and the autosync totals. When it is non-zero the CLI says plainly that those
  rows are NOT in the vault and names the likely cause — a truncated or
  malformed peer export — because claiming a clean import over a silent loss
  removes the only signal that anything is wrong.

  A refused row still does not abort the pass: the rest of the file imports, so
  one bad row cannot wedge a device's sync. `wiki db autosync` reports refusals
  in its console output as well as its `--json`, and the Obsidian plugin raises
  a notice even when sync notifications are off — this is data that did not
  arrive, not routine progress.

## [0.49.3] - 2026-08-08
### Fixed
- **Rows Written During An Export Were Recorded As Already Exported** (B2 / sync_db-3)
  `export_for_device` stamped `last_export_ts` AFTER `export_knowledge` returned.
  `local_has_unexported_changes` treats anything older than that stamp as
  already shipped, so a row mutated while the export was running — not in the
  snapshot, but with a `created_at` earlier than the stamp — was silently
  considered exported. No peer would ever be offered it until an unrelated later
  mutation happened to move the clock past the stamp.

  The window is the export's own duration, so it widens with the vault: it is
  largest exactly when there is most to lose. The stamp is now taken before the
  snapshot is read and written only after a successful export, so a failure does
  not claim to have shipped anything.

## [0.49.2] - 2026-08-08
### Fixed
- **One Un-archivable Conflict File Wedged Sync Permanently** (B2 / CAND-03)
  After merging a sync conflict, `_archive_conflict` moved the file out of the
  synced vault (`<vault>/.curator/sync/`) into the repo-local cache
  (`<repo>/.cache/vaults/<hash>/runtime/sync_conflicts/`) with `Path.rename`.
  Those are different trees by design — the vault lives on synced storage
  (iCloud, Syncthing, a network mount), the cache is local — so they are
  routinely on different filesystems, where `rename` raises `OSError(EXDEV)`.

  `autosync` turns that into an `AutosyncError`, and the file stays in the sync
  directory: every later run re-imports the same conflict and fails again. One
  file wedged sync for that vault forever. It now uses `shutil.move`, which
  falls back to copy+unlink across filesystems.

  The archive name is also made unique instead of overwritten. A conflict file
  holds data not merged anywhere else, so silently replacing one with another of
  the same name destroyed it.

- **A Test That Went Red On A Calendar Boundary**
  `test_span_metadata_sync.py` (added in v0.49.1) hardcoded
  `2026-08-08T00:00:00Z` as a "newer than `created_at`" stamp. The derived
  revision is `max(created_at, metadata stamps)` and `created_at` is `now`, so
  that value was newer when written and older a day later — the suite went red
  with no code change. Timestamps there are now far-future sentinels, with the
  reasoning recorded so the trap is not reset.

## [0.49.1] - 2026-08-08
### Fixed
- **The v0.49.0 Sync Clock Was Applied At Two Sites And Missed Four**
  v0.49.0 derived a `source_spans` LWW revision from `created_at` plus the
  timestamps inside `metadata`, but only wired it into the `_lw_upsert`
  comparison and the `_local_max_ts` export gate. Four other places still ranked
  a span by the immutable column:

  - `_row_is_blocked_by_tombstone` and `_apply_tombstone` — on the **default**
    `wiki db import` path. Every metadata edit looked older than any tombstone,
    so an edit made *after* a delete was silently discarded instead of
    resurrecting the row, and an incoming delete destroyed a locally-newer edit.
  - `clear_row_tombstone_on_connection`.
  - `wiki db export --since`, which filtered on the raw column and so omitted
    exactly the metadata-only writes the derived clock exists to carry.

  Rather than patch a fifth site later, `row_revision()` is now the single entry
  point for "how new is this row", and `_UPDATED_AT_COL` carries a comment
  saying never to rank rows by it directly.

- **`_local_max_ts` Scanned Every Span On A Default-On Path**
  It materialized and JSON-decoded the whole `source_spans` table, and runs once
  per ingest job via `maybe_auto_export` — making a batch ingest
  O(jobs × total_spans). It now scans only rows carrying metadata and keeps the
  indexed `MAX(created_at)` for the rest.

- **The L1 Marker Could Be Cut In Half**
  `[image not extracted]` was three whitespace-delimited tokens, so
  `_section_preview`'s pre-existing word-boundary truncation could leave a
  dangling `[image not` — which reads as ordinary cut-off prose rather than a
  flagged loss, defeating the point of showing it. It is now the single token
  `[image-not-extracted]`, which `rsplit(" ", 1)` drops whole. Being one
  bracketed token also reads as an annotation rather than prose, which matters
  because this preview is quoted to the model as source text.

- **Spec Corrections**
  SCHEMA §20.4a described a "one-shot backfill … the only path for existing
  rows". No backfill was ever built — the shipped mechanism is a `text_preview`
  fallback at read time, exactly as the v0.49.0 CHANGELOG described. §20.4a now
  documents what exists, including that a *missing* `loss` key is not proof
  nothing was lost. Two dangling cross-references are fixed (§20.4a pointed at a
  nonexistent §20.6a; §26.2b cited the unrelated §20.6), and the v0.49.0 sync
  change — a runtime behavior change that had no spec entry at all — is now
  SYSTEM_BEHAVIOR §26.2c.

- **An Unenforced Vocabulary Claim**
  SCHEMA §20.4a states the loss verdict shares
  `formula_recovery.LOSS_VERDICTS`. Nothing checked it. `source_spans` cannot
  import that module without dragging `claim_support` onto the instant-L1 path,
  so a test now enforces the equivalence and a rename on either side fails.

## [0.49.0] - 2026-08-08
### Added
- **Unreadable PDF Regions Are Reported Instead of Silently Dropped**
  Many papers render displayed equations and figures as images. The parser
  cannot read them, so their content never reaches the knowledge base — and
  that happened silently. Measured on a real vault: one 27-page paper discarded
  **158** such regions, and **130** existed vault-wide across 4 sources, with no
  surface reporting any of it. A question about one of those equations could not
  be answered and nothing explained why.

  Three changes make the loss visible:

  - `source_spans.metadata.loss` records the verdict (`image_only`) and whatever
    geometry the parser stated (SCHEMA §20.4a, SYSTEM_BEHAVIOR §26.2b). It is
    additive: it gates nothing, changes no `formula_status`, and triggers no
    provider call.
  - `wiki lint` gains an `extraction_loss` check — one line per source with the
    count and sections, never one per span, and silent for sources that lost
    nothing. `wiki add` reports the same at ingest time.
  - The L1 projection keeps a `[image not extracted]` marker where the region
    was. `_section_preview` had been eliding it to whitespace, and for an
    `on_demand` source that preview **is** the CTX body that
    `_durable_l1_projection` serves as the plugin's chat context — so the one
    surface a reader actually sees had the gap closed, leaving prose that
    stopped mid-sentence.

  Existing vaults are covered with no migration and no re-ingest: the check also
  recognizes the placeholder still present in `text_preview`. That deliberately
  avoids `wiki add --force`, which sets `l2_status` back to `pending` and
  silently triggers a full L2/L3 rebuild across every source.

### Fixed
- **A `source_spans.metadata` Write Was Silently Dropped By Every Peer**
  `source_spans` has no `updated_at`, and `db_sync` used the immutable
  `created_at` as its last-write-wins clock. Any metadata mutation therefore tied
  on import and lost the strict `>` comparison, so the peer discarded it — and
  `_local_max_ts` never moved either, so the writing device did not even detect
  it had something to export. This was live but unexercised: `recover_formula()`
  has mutated `metadata` since v0.8.0.

  The LWW clock for `source_spans` is now derived from `created_at` plus the
  timestamps inside `metadata`, applied identically to both sides of the
  comparison and to the export gate. No new column — this codebase has no
  `ALTER TABLE` path, so an existing vault could not have received one.

### Notes
- This release makes formula loss **observable**; it does not recover a single
  equation. Recovery is blocked on three prerequisites documented in the Arena
  record: the `recover_formula` acceptance gate uses token-tuple equality where
  `validate_claim_support` uses subsequence (so faithful transcriptions are
  rejected), `validator_trace_id` has no producer anywhere in the backend (so
  the `reviewed` state is unreachable), and placeholder spans carry no bbox or
  physical page (so the region cannot be cropped for a vision model).

## [0.48.4] - 2026-08-07
### Fixed
- **`no output produced` Instead of an Answer About a Formula**
  Asking about a numbered equation in a PDF whose displayed math is rasterized
  returned no answer at all, only the provider's own failure text:

  > jetski: no output produced — a tool required the "command" permission that
  > headless mode cannot prompt for, so it was auto-denied

  `buildResolvedReferencesBlock` returned the empty string whenever no
  reference resolved. The user's question ("수식 26 설명좀") therefore reached
  the model with the equation absent *and* with nothing indicating an equation
  had been asked about — the prompt read as though the selection pointed at
  nothing. The model did the reasonable thing and tried to open the PDF with a
  file-reading tool. A headless CLI provider cannot prompt for that permission,
  the runtime auto-denied it, and the turn produced no output.

  Unfindable references are now named in an `<unresolved_cross_references>`
  block whose `note` states the text is genuinely absent from the extracted
  document, directs the model to answer from the context it already has and to
  say which item was unavailable, and forbids it from opening the file itself.
  The block carries labels only and never a snippet, so the existing
  fail-closed guarantee on content is unchanged — no context is still preferred
  to wrong context. `PLUGIN_SCHEMA.md` already required that "the prompt must
  tell the provider when the referenced target could not be located"; this is
  the concrete block that requirement was missing, and the spec now names it.

  Note that this restores a useful answer, not the equation: recovering math
  that was never extracted is a separate defect (`recover_formula()` is
  implemented and specified in SYSTEM_BEHAVIOR §26.2 with zero production call
  sites) and is tracked as its own roadmap item.

- **A Merged Page Reference Was Declared Missing While Being Quoted**
  Found in review of the fix above, before release. `resolveWithNearbyPageHints`
  relabels a successfully resolved page reference `method: "unresolved"` purely
  to suppress a duplicate render once its text has been folded into a nearby
  sibling. That flag never escaped while every unresolved entry was dropped;
  naming them sent it straight into the prompt. Selecting
  `(Section 11.1.2, p281)` produced page 281's text quoted verbatim under the
  section entry *and* `p.281` listed as absent from the document, in the same
  prompt — misleading content, which is worse than the silence it replaced.

  The two meanings are now distinct: `consumedBySibling` records that the text
  was delivered elsewhere, so such a reference appears in neither block, while
  `method` keeps its existing meaning for the fetch and identity-repair paths.

- **The Unresolved Note Claimed a Verified Absence It Never Established**
  The note asserted the text "is absent from the extracted document" and that
  the gap was final. The quick-query popover passes no whole-document locator
  at all, and where one is wired it returns nothing when the backend is
  offline, so "we did not look" was being reported to the model as "confirmed
  absent" — directing it to state a falsehood confidently. It now claims only
  that retrieval failed.

- **The Recency Anchor Did Not Carry the New Rule**
  `buildRecencyAnchor` is emitted last, at the position of strongest attention,
  specifically to survive long-session attention decay, and is appended on the
  same sidechat surface where the failure was reported. It still named only
  `<resolved_cross_references>`, so a long enough session could steer the model
  back into the auto-denied tool call even with the fix in place. It now
  carries the unresolved case and the no-file-read rule.

## [0.48.3] - 2026-08-07
### Fixed
- **"Add source" Stayed Clickable After A PDF Was Already Added**
  Adding a Zotero PDF from the purple pin registered it correctly, but the
  control kept reading "Add source" and remained clickable, so the same source
  could be submitted again with no sign it was already in the knowledge system.

  A Reference-Mode source stores the vault-side **stub** in `sources.relpath`
  (`04_Resources/References/<title>.md`), never the external PDF path. The
  plugin checked status by the PDF path, which matches nothing — verified
  against the reporting vault, where source 37 has all four layers `done` and
  yet `wiki plugin source status --file-path <pdf>` answers "Source not found".
  That `untracked` result renders the "Add source" label, and the
  already-added guard (`isAddedState`) never fires because the state never
  reaches an added value.

  `logical_source_id` (`zotero:<key>`) is the identity that survives, and the
  backend's `get_source_row` already matches on it — confirmed by looking the
  same source up that way and getting id 37 with `l1..l4 = done`. The plugin
  simply never sent it. It now does, on every status check rather than only
  when no local path is known, so a Zotero PDF whose path is unresolved on this
  device also resolves instead of being reported untracked without asking.

## [0.48.2] - 2026-08-07
### Fixed
- **The Sidechat Job Indicator Disappeared**
  The spinner and "N running / N queued" badge in the sidechat header stopped
  appearing entirely. `updateStatusBar` read
  `<vault>/.curator/runtime/jobs.json`. Runtime snapshots moved to the
  repo-local cache in 2026-07 and nothing migrated or rewrites the vault-side
  copies, so that file froze: on the reporting vault it sat at 2026-07-04 with
  `running: []` while the live snapshot showed a job actively running. With an
  empty `running` list the render block is skipped and nothing is drawn, which
  is indistinguishable from the feature having been removed.

  It now reads the snapshot at its real location through
  `plugin.readRuntimeJson("jobs")`, which resolves the hash-keyed cache
  directory (`vaultMachineCacheDir`, mirroring the backend's
  `get_vault_cache_dir`) and is already used in production by the main status
  bar. This stays a cheap file read: `b9a49a1` deliberately left the sidebar on
  the snapshot rather than the live CLI, because unlike the dashboard's
  once-per-render fetch this polls for the lifetime of the view. Polling stays
  at 2 s.

  A missing or unreadable snapshot is treated as "unknown", not "no jobs" —
  whatever is on screen is left alone. Blanking on a read failure would
  reproduce the exact symptom being fixed from a different cause.

  Two source-level tests guard the invariants that let this hide for a month:
  that the poll resolves the hash-keyed path rather than any `.curator` vault
  path, and that the not-readable early return sits before the element is
  emptied.

## [0.48.1] - 2026-08-07
### Fixed
- **Asking About A Formula On A Distant PDF Page Produced No Answer At All**
  Reading page 1 of a 30-page paper and asking about equation (24) on page 27
  returned only a provider error:

  > no output produced — a tool required the "command" permission that headless
  > mode cannot prompt for, so it was auto-denied

  The reference resolver probes for a numbered equation at `currentPage ±2`
  only (`ADJACENT_EQUATION_PAGE_OFFSETS = [1, -1, 2, -2]`). Page 27 was never
  fetched, so the reference failed closed, no `<resolved_references>` block was
  attached, and the provider was left to locate the page with its own tool call.
  A headless CLI provider cannot prompt for tool permission, so it produced
  nothing — the error was the symptom, not the cause.

  The resolver now falls back to a whole-document lookup when the adjacent probe
  comes up empty: the backend already indexes every page of a tracked PDF and
  returns a page number per hit, so the referenced equation is located and its
  page fetched deterministically before the provider is called.

  Deliberately bounded: the lookup runs **only** after the cheap adjacent probe
  fails (verified by test — no backend search for an equation one page away),
  fetches at most 3 located pages so a poor hit list cannot become dozens of
  fetches, and a locator that throws leaves the previous fail-closed behaviour
  intact rather than surfacing a resolved-looking reference with no content.

## [0.48.0] - 2026-08-07
### Changed
- **The Internal Language Boundary Is Enforced By The Backend, Not Requested By Callers**
  v0.47.0 fixed Korean questions failing to reach L3/L4 by adding
  Korean/CJK/Cyrillic alternatives to the route signals and making `seed_terms`
  script-aware. That worked, and it was architecturally backwards: it made the
  system's INTERNALS multilingual, when the contract is that internals are
  English and only input/output carry the user's language
  (USER_GUIDE: "using English only as the internal search/reasoning language").
  Every future internal component would have inherited the same obligation.

  The real defect was that `QueryRequest.english_query` — the slot built for
  exactly this — was never populated on the ContextService path, so
  `working_query` silently fell back to the raw question.

  - Route signals and `seed_terms` are back to English/Latin-only.
  - `fetch_context` derives the English query itself. It is **not** a CLI flag:
    an invariant with no exceptions cannot depend on a caller remembering to
    pass it, and a caller that forgets degrades silently — the original bug.
  - New prompt contract `curator.query_search_terms` extracts a short English
    **search query**, not a translation. Translating is wrong for real requests:
    "이 문장을 한글로 번역해줘: <body>" rendered into English becomes an English
    sentence asking for a Korean translation, which would then be routed and
    matched as a question about the vault; and a long paste would be translated
    in full at cost with none of it usable as a query.
  - The same step returns `is_knowledge_question=false` when a message needs no
    stored knowledge, and retrieval is skipped with a stated reason. This is
    decided by reading intent — never by matching trigger words, which is
    unmaintainable and fails on the first synonym.
  - When derivation is unavailable it falls back to the ASCII terms already in
    the message (a real query for mixed-script input like "ellipsoid 형태의
    quadric") and says so.

## [0.47.0] - 2026-08-07
### Fixed
- **Routing Was Language-Bound: Korean Questions Could Never Reach L3/L4**
  `retrieval/router.py` chose the route with ASCII-only keyword regexes, so a
  non-English question could not match `global` or `explore` and always fell
  through to `local`. Measured on the real vault: all four of a Korean user's
  questions returned 0 of 233 community reports and 0 of 4 synthesis nodes —
  including one that explicitly asked to synthesize across multiple papers. The
  identical questions in English routed `global`. The distilled layers were not
  badly ranked for a non-English speaker; they were unreachable.

  Signals now cover the five languages USER_GUIDE documents as supported. Note
  `\b` is deliberately not applied to CJK alternatives: Python word boundaries
  are defined on `\w` and never fire between Han/Hangul characters, so a
  boundary-anchored CJK pattern silently never matches.

- **Entity Seeding Was Latin-Only**
  `seed_terms` tokenized `[A-Za-z]` only, so a pure-Korean question produced
  zero seed terms and entity resolution returned nothing on every route,
  regardless of graph coverage. It is now script-aware. A lone Hangul/Han
  character is skipped — it is a grammatical particle far more often than a
  term, and seeding on it matches any entity containing that character.

- **The Chat Surface Never Passed A Workspace, So The Curation Lens Never Applied**
  `ChatSidebarView` sent the Obsidian vault ROOT as `workspace_path`.
  `curate.yml` lives only at `01_Workspaces/<project>/`, so the backend found
  none, silently fell back to the empty default policy, and every pack reported
  `workspace_id: "default"` with an empty `policy_hash` — the Artist-persona
  lens of `about.md` §4/§5.6 applied to nothing a user read. The workspace is now
  resolved from the note in focus, through one helper shared by every
  ContextService call so a pack cannot be fetched under one policy and expanded
  under another. It still falls back to the vault base when no project applies,
  because `workspace_path` also selects which vault the backend opens.

- **Entity Descriptions Were Frequently Circular** (`curator.entity_relation_extract`
  v1 → v2) — 12 of 34 entities in served packs (35%) merely restated their own
  name, with a ~10% floor across all 965 entities. The v1 prompt had seven hard
  rules about relations, confidence and span citation, nothing about
  descriptions, and a worked example showing `"description": "..."`. v2 adds a
  description contract with worked bad/good examples. The version bump is
  required rather than cosmetic: `prompt_run_id` and `prompt_contract_version`
  are recorded against generated records.

### Changed
- **Claim Support Now Ranks And Labels Knowledge Instead Of Hiding It**
  `retrieval/materializer.py` selected only `support_status = 'verified'` units
  when building the search index, making claim-support validation an **admission
  gate**. A unit that had not been validated was not ranked lower — it was
  invisible to every route, every ranker, and every reranker.

  Validating an `uncertain` claim requires a calibrated secondary validator, and
  when none is configured the unit stays `unchecked` permanently. So a missing
  provider configuration silently deleted most of a knowledge base, with no
  warning and no way for a user to discover it.

  **Measured on a real 36-source vault: 1,701 of 2,799 live units (61%) were
  unreachable.** 1,117 of those were merely `unchecked` — never validated
  because no validator was configured. The reporting user's own question — how
  an ellipsoid quadric is written as a matrix — had its exact answer
  (`$Q^* = Z \breve{Q}^* Z^T$`) sitting in the database at confidence 1.0 and
  could not be retrieved by any route. After this change the index carries 2,215
  units (+1,117) and that answer is reachable, labelled `unchecked`.

  **`failed` stays excluded, deliberately.** It is not a weaker tier: it means
  the support check ran and found the cited span does not support the claim.
  Such a unit already writes no atom page and never feeds graph extraction, so
  search was the one remaining place ungrounded content could leak back in.
  (498 of the 584 `failed` units carry `formula_status='preserved_in_text'` and
  are prose-gate false negatives — real, but fixable at the gate rather than by
  admitting flagged content to the index.)

  This is the same defect shape as the pre-v0.43.0 relation-corroboration gate,
  and it takes the same resolution:

  - **Ranking**: `verified` is unpenalised; `unchecked` / `uncertain` / `failed`
    are multiplied down so they sort below comparable verified evidence. The
    penalty is applied *before* ranking so it reorders rather than relabels, and
    is deliberately gentle — a strongly matching unverified claim may still beat
    a weakly matching verified one, because the alternative is serving nothing.
  - **Labelling**: every evidence item now carries `support_state`. Serving
    unverified knowledge without saying so would trade a silent omission for a
    silent overstatement.

  The gates that were correct are unchanged: retired units never serve, and
  staged or discarded generations never serve (§26.3).

### Fixed
- **L3/L4 Content Reached Through Search Arrived Anonymous**
  `EngineHit.record_type` was discarded when building the public `SearchHit`, so
  a community report or synthesis node found via search surfaced as a bare
  `search_hit` with an empty `community_report_id` / `synthesis_node_id` — served
  in the pack but invisible to the pack's own L3/L4 counters, which is why an
  audit measured "0 synthesis nodes" on a pack that contained one.

## [0.46.0] - 2026-08-06
### Added
- **Vault File Moves And Deletes Are Tracked**
  Moving a file inside the vault after importing it broke every stored reference
  to it. Reported through the sidechat: after moving a Zotero-imported note from
  `03_Notes/Vision/3DRec/` to `03_Notes/Papers/3DRec/`, an agent edit block came
  back `File not found` against the pre-move path.

  **The plugin subscribed to no vault file events at all** — two `registerEvent`
  calls existed repo-wide and both were workspace layout events. Obsidian
  supplies the old path on rename; nothing listened. It now subscribes to
  `vault.on("rename")` and `vault.on("delete")`.

  **A move preserves everything except the location.** `db.relocate_source`
  updates all three places the path is denormalized (`sources.relpath`, every
  `source_spans` row, `search_documents.projection_path`) in one transaction,
  keeping the content hash, every layer status, `context_id`,
  `logical_source_id`, and the whole derived L1–L4 closure. `sync_key` is
  deliberately NOT rewritten: it is the cross-device identity, minted once and
  matched only by equality, and changing it would make a peer replica see a
  delete plus an insert rather than one moved row.

  **Zotero stubs relocate freely.** `logical_source_id` identifies the document;
  `relpath` is only where the stub sits. This is why the existing
  `rebind_source` was the wrong tool — it keeps `relpath` unchanged, re-points
  the EXTERNAL file, and refuses `zotero:` sources, because Zotero owns the PDF
  path but not the stub's folder.

  **A delete marks the source and keeps its knowledge.** It records
  `error_reason='file_missing'` and retires nothing, so an accidental delete —
  or a file moved out of the vault and back — cannot silently destroy extracted
  knowledge. `wiki source rm` remains the only path that retires a dependency
  closure.

  **Historical chat paths still resolve.** A bounded rename journal follows
  recorded moves, collapsing chains (A→B then B→C means A resolves to C).
  `resolveVaultFile` consults it only after every exact-path candidate fails,
  and still refuses a basename fallback — a same-named file in another folder is
  a different note and retargeting an edit to it would corrupt the wrong file.
  The journal is exact provenance from Obsidian's own event, not a guess.

- **`wiki lint` reports registered sources whose file is gone.** This is how the
  delete mark becomes visible, and it also finally diagnoses the real defect
  behind a pile of `invalid_source_path` errors: on the reporting vault, 48 Atom
  errors all traced to ONE source row registered at a path that no longer
  exists. The finding is never auto-fixable — restore versus retire is the
  user's call.

- New hidden CLI surface: `wiki plugin source relocate --from --to` and
  `wiki plugin source missing --from [--restored]`.

### Known Gap
- Vaults that already carry a dead source row from a pre-v0.46.0 move are
  reported by the new lint check but not repaired automatically. Retro-repair
  needs a content-hash reconciliation sweep and is tracked separately.

## [0.45.0] - 2026-08-06
### Changed
- **A Failed Layer Is Now `error`, Never `skipped` (BREAKING for status readers)**
  `compile_global_l3` recorded `l4_status='skipped'` when synthesis threw.
  SYSTEM_BEHAVIOR §4.1 already required `error` there, so the code was the side
  that was wrong. `skipped` means "this source contributed nothing to the
  layer" — an ordinary non-failing outcome — so recording an
  attempted-and-thrown layer as `skipped` made a broken build indistinguishable
  from an empty one. Observed on a real vault: 10 of 36 sources sat at
  `skipped` across L2/L3/L4 with **both** `layer_error` and `error_reason`
  empty, two of them holding 11 knowledge units each.

- **L3 And L4 Failures Are No Longer Conflated**
  A single `errors` list collected failures from both community-report
  construction and synthesis, so a synthesis failure marked `l3_status='error'`
  even though clustering had succeeded completely. The two are tracked
  separately: L3's status now reflects only L3's own work.

### Fixed
- **Crash Recovery Erased The Post-Publish Projection Marker**
  `sources.layer_error` is overloaded three ways — human error text, the
  post-publish projection marker that `pipeline/compile.py` *reads* to take the
  recovery path instead of recompiling, and sync annotations. `recover_stale_jobs`
  cleared the column unconditionally, so the real crash sequence (worker dies
  after publishing a generation → supervisor restarts → recovery requeues the
  job → retry runs) lost the marker at the recovery step and re-ran the entire
  LLM extraction against an already-published generation. The existing test
  missed it by retrying in the same process with no recovery interposed.

  The `running` → `pending` reset §4.1 requires still happens; `layer_error` is
  preserved when it matches the marker and cleared otherwise, so stale human
  error text still goes away. The marker prefix moved to
  `constants.POST_PUBLISH_PROJECTION_PREFIX` so the SQL and the Python cannot
  drift apart.

- **The L4 Status Write Clobbered The Real L3 Error Message**
  `layer_error` is one column shared by all four layers, and the loop wrote it
  twice per source — first with the L3 cause, then with a fixed L4 string. The
  second write won, destroying the actual reason L3 failed on the same line
  that recorded it. A build that fails at more than one layer now composes one
  layer-tagged message (`"l3: … ; l4: …"`) and writes it once.

  That fixed L4 string was also a lie in the one case it mattered: it read "L3
  prerequisite failed; synthesis not attempted" even when the error had come
  from synthesis itself, which had demonstrably been attempted. It is now used
  only when L3 really did fail first and gate it.

- **`wiki sync` Promoted L3/L4 To `done` From A Filesystem Glob**
  `_mark_clean_sync_status` set `l3_status='done'` for **every** source with
  `l2_status='done'` whenever *any* `CON-*.md` file existed anywhere on disk,
  and the same for L4 against `SYN-*.md`. The promotion was not per-source and
  consulted no record of what a given source contributed, so a genuinely
  `skipped` source came out of sync indistinguishable from a completed one.
  `.curator/Collections/` is a disposable projection; the presence of a file
  there says nothing about provenance.

  The promotion is deleted. `_mark_clean_sync_status` now does what its name and
  docstring always claimed — clear stale `layer_error` — and nothing else.
  SYSTEM_BEHAVIOR §26.3 states the rule explicitly: layer status is computed by
  the compiler and by nothing else.

- **A Second Filesystem-Glob Status Promotion, Reachable From Two Read-Only
  Commands**
  `_mark_existing_l3_done_if_present` was the twin of the promotion deleted from
  `_mark_clean_sync_status` — same glob, same every-source promotion — and it
  ran unconditionally from `wiki sources ls` and `wiki status --refresh`, two
  surfaces that should not mutate the vault at all. Removed along with its
  callers; `--refresh` now only rewrites the runtime snapshot cache, and its
  help text says so.

- **`wiki sync` Erased The Gap Reason It Had Just Recorded**
  `_mark_layer_status_from_sync_gaps` wrote the `sync_logical_gap:` reason with
  the L3 status, then immediately wrote `l4_status='pending'` with no `error=`
  — defaulting to `None` and clearing the shared column. `l3_status` was left
  `error` with no explanation, permanently. The same clobber this batch fixes in
  `compile_global_l3`, one function away.

### Added
- `db.UNSET` sentinel for `set_source_layer_status` / `set_sources_layer_status`,
  leaving `layer_error` untouched, plus `set_source_layer_error` /
  `set_sources_layer_error` for writing the column without touching a status.
  The default stays `None` (clear) — see `.agents/plans/03_b3_roadmap_evidence.md`
  for why flipping it would have traded this bug for its mirror image across
  ~25 call sites. Bulk id predicates are chunked to the module's conservative
  999-variable convention, matching the eight existing `_chunks()` call sites.
## [0.44.1] - 2026-08-06
### Fixed
- **`wiki lint` Reported 70 Errors The User Could Not Act On**
  Audit of a real 37-source vault after the post-v0.43.0 build scored 70 errors
  / 0 warnings, every one of them `invalid_source_path`. Three separate defects
  in the same check produced them.

  **(a) Two Unicode normalizations compared byte-exact.** `lint.py` built its
  set of known source paths from a filesystem walk, which on macOS yields
  decomposed (NFD) names — `Plu` + U+0308 — while the path stored in
  `sources.relpath` and written into page frontmatter is precomposed (NFC)
  `Plü`. Python string equality has no opinion about Unicode equivalence, so
  the two never matched in a `set` lookup even though they name one file that
  `Path.exists()` opens either way. 22 of the 70 errors were this. Both sides
  of the comparison are now NFC-normalized.

  **(b) The repair resolved through a field the compiler no longer writes.**
  `check_atom_source_paths` recovered an Atom's true source by following its
  `parent_source` wikilink to a Context and looking the Context up in `sources`.
  Measured on the same vault: **0 of 1098 Atoms carry `parent_source`** — the
  compiler emits `source_span_ids` instead. So `fixable` was False for every
  modern Atom while the suggestion still said to run `wiki lint --fix`, which
  then did nothing. The repair now resolves through the Atom's own
  `source_span_ids` → `source_spans.source_id` → `sources.relpath`, which is
  the provenance the page actually carries; `parent_source` is still consulted
  second so pre-compiler pages keep working.

  **(c) An unrepairable error advertised a repair.** Even with a resolvable
  source, `--fix` copies `sources.relpath` into the Atom — which helps only if
  that row still names a file that exists. When a source is renamed on disk
  without being re-registered, the "repair" wrote the dead path straight back
  and the identical error returned on the next run: a loop the tool could not
  exit. An issue is now marked fixable only when the repair value resolves on
  disk, and the three cases (repairable / stale source row / no registered
  source) each carry a suggestion naming the actual remedy.

  On the audited vault this takes 70 errors to 48. The 48 that remain are one
  genuinely stale `sources` row whose file was renamed away, and they now say
  so and point at `wiki add` / `wiki source rm` instead of at a fix that cannot
  work.

## [0.44.0] - 2026-08-05
### Removed
- **`wiki query --update` And Its Insight-To-Atom Path**
  The flag created an L2 Atom out of the synthesized answer. It did so by
  writing an `ATM-*.md` file directly into `.curator/Collections/02_Atoms/`
  with **no `knowledge_units` row behind it** — an orphan in a directory the
  system treats as a derived, disposable projection of the database. The node
  was therefore invisible to search, to the graph, and to every integrity
  check, and any re-emission from the DB dropped it. It also contradicted
  SYSTEM_BEHAVIOR §22.2, which requires backpropagation to be
  correction-driven and independent of query artifacts.

  Querying is now read-only with respect to the DAG, which is what the user
  guide already claimed. To feed something learned from an answer back into the
  graph, promote it to `02_Wiki/` (it re-enters as an L1 input on the next
  cycle) or use the insight lifecycle (`wiki insight list` / `show` /
  `promote`). `wiki sync --backward` is unaffected — it still synthesizes atoms
  from *corrections*, which is the sanctioned path.

### Fixed
- **`context_expand` Double-Subtracted The Expansion Reserve, So Every Handle It
  Advertised Was Guaranteed To Be Refused**
  `context_fetch` withholds a reserve (`min(1000, limit // 4)`) so that
  expansion has headroom, and `context_expand` withheld it a *second* time
  against the same `limit_tokens`. Since both paths share a cost function and
  the running total only grows, an item that fetch omitted because
  `used + cost > limit - reserved` could never satisfy
  `already_used + cost <= limit - reserved` afterwards. Every handle offered in
  `next` was therefore mathematically certain to come back as
  `expansion_refused / budget_exhausted` at the budget that offered it, and the
  progressive-expansion surface was inert on its own default path
  (`limit_tokens=8000` for both operations). The admission ceiling on expand is
  now the full `limit_tokens` per SYSTEM_BEHAVIOR §31.1, and an expand response
  reports `budget.reserved_tokens = 0` because nothing is being withheld.

- **A Secret That Cannot Be Decrypted Was Reported As A Missing API Key**
  `secret_store.get_secret` swallowed `InvalidToken` and returned `""`, which
  is exactly what "no secret stored" returns. The Fernet key is machine-local
  and never syncs, so this is the ordinary result of the project's own
  cross-device config sync: the config names a secret whose ciphertext this
  machine cannot open, and DeepSeek then told the user to set
  `DEEPSEEK_API_KEY` — sending them to check an environment variable that was
  never the problem. Reading an undecryptable entry now raises
  `SecretDecryptionError` naming the secret and the fix. `wiki config secret
  list` still succeeds, rendering that row as `<undecryptable>`.

- **Silent Exception Boundaries (SYSTEM_BEHAVIOR §32)**
  `wiki lint --fix` swallowed a failing `search.update_index` with
  `except Exception: pass` — a false success, since the pages on disk and the
  search index had diverged and queries would serve stale text with no
  indication. It now warns with the cause and points at `wiki reindex`. The two
  account-identity fallbacks in `llm_identity.py` log the suppressed cause
  instead of silently degrading to "Authenticated", and the JWT claim decoder
  narrows its catch to the specific parse classes §32 requires. The
  atom-from-insight path (still reachable through `wiki sync --backward`) logs
  which of its three failure modes it hit instead of collapsing them all to a
  bare `return None`.

### Documentation
- SCHEMA §7 MCP payload examples were stale: `check_source_status` gained
  `relpath`, `l4_complete`, and the full `source` record, its three other
  response shapes are now documented, and `get_available_models` shows the `ok`
  wrapper, the `deepseek`/`ollama` providers, and the per-model entry fields.

## [0.43.0] - 2026-08-05
### Changed
- **Relation Corroboration Threshold Lowered To One Independent Source**
  A relation entered authoritative topology only with **≥2** distinct verified
  `source_lineage_hash` values. But the lineage hash already collapses
  copied/duplicated/forked sources to one lineage, so requiring two did not
  exclude fraud — it excluded every proposition that only one source states,
  which in a personal research vault of distinct papers is nearly every
  proposition.

  Measured on a real 37-source vault: **717 of 722 relations were quarantined**
  as `copied_source_only` (every one of them with exactly one lineage), leaving
  5 active relations, 6 community reports, and 3 synthesis nodes. Community
  construction consumes only `active` relations, so it had almost no input, and
  34 of 37 sources reported `l3_status='skipped'` and `l4_status='skipped'`. The
  knowledge graph the product exists to build was effectively empty, which is
  also why sidechat and MCP had no L3/L4 to reference.

  This contradicted the stated philosophy, where a Permanent Note is "a **single**
  idea as an independent Atom" and the value is *linking* such notes across
  distinct sources — Zettelkasten never requires two sources to agree before an
  idea may be linked. Corroboration is now treated as a ranking/confidence
  signal rather than an admission gate: `active` requires **≥1** verified
  lineage, and only **0** is `unsupported`.

  **Existing vaults recover without re-extraction.** Relation lifecycles are
  recompiled for every non-retired relation at the start of graph rebuild, so
  the next `wiki build` re-admits previously quarantined relations. Verified on
  a copy of the affected vault: active relations went from **5 to 651**, with
  the remaining 71 held only by the separate `bridge_risk` structural check.

  `copied_source_only` is retired as an outcome and kept in the frozen reason
  set so historical rows stay decodable and re-evaluable. SYSTEM_BEHAVIOR §27.2
  /§27.3, SCHEMA §21.5/§21.6, and the §27.6 graph-audit assertion are updated to
  match.

## [0.42.4] - 2026-08-05
### Fixed
- **A Cancelled CLI Request Is Actually Cancelled**
  The non-streaming CLI paths returned their promise from inside the request's
  guarded block, so the block settled at launch and the `finally` released the
  request — detaching the owner's abort listener — while the CLI child was still
  running. A Stop or dismiss then reached nothing. Both the primary CLI path and
  the HTTP-auth CLI fallback now await inside the guard.
- **Reposition Listeners No Longer Leak Onto Popout Windows**
  The Quick Query trigger attaches `scroll`/`resize` listeners to the window
  owning the selection, but detached against whichever window was active at
  teardown. Selecting text in a popout and then in the main window stranded a
  capture-phase `scroll` listener on the first one for the rest of the session.
  The attach-time window is now recorded and detached against, and the existing
  trigger is torn down before the active-document reference moves.
- **A Second Vault No Longer Deletes The First One's In-Flight Chat Image**
  The startup sweep for crash-leftover chat images removed the whole
  `chat_images` directory. That directory is scoped to the Incurator repository,
  not to a vault, so opening a second vault in another Obsidian window destroyed
  an image payload the first vault was mid-send with. The sweep is now per run
  directory and skips anything younger than the longest a single request can
  legitimately live; per-request cleanup in the request's own `finally` remains
  the primary mechanism.
- **Auto-Sync No Longer Runs After Unload**
  `SyncScheduler.dispose()` cancelled the debounce timer but left a queued
  follow-up armed, so a pass already in flight re-fired from its own completion
  handler and started a backend subprocess after the plugin had unloaded.
  Disposal now sets a terminal flag that every entry point checks and clears the
  queued flag.
## [0.42.3] - 2026-08-04
### Fixed
- **Quick Query No Longer Answers From The Wrong PDF After A Tab Switch**
  `fetchActivePdfPage` guards document identity only when the caller supplies an
  expected id. The local PDF tool runner opted in; Quick Query did not. Its
  cross-reference resolution issues several sequential backend round-trips
  (~0.2 s each), so switching tabs mid-flight let later fetches read pages out
  of the newly active PDF and splice them into the answer. Because the resolver
  also writes each fetched page back into the index under the document id it was
  given, foreign page text contaminated the original document's BM25 index and
  skewed later queries too. Quick Query now reads the document identity once,
  before the first await, and uses that same pinned id both for every page fetch
  and for the index it writes into — so a mid-flight tab switch fails closed
  instead of answering from the wrong document.

## [0.42.2] - 2026-08-04
### Fixed
- **Quick Query No Longer Crashes On PDF Text Containing Null Bytes**
  Selecting text from certain PDFs and asking a question in the popover threw
  `The argument 'args[11]' must be a string without null bytes`. PDF text
  extraction can embed `\0` characters which are valid in JavaScript strings but
  fatal when Node.js converts CLI arguments to C-strings for `execve`.
  `messagesToCliPrompt` — the single funnel for all CLI provider prompts — now
  strips null bytes before the string reaches `child_process.spawn()`.

## [0.42.1] - 2026-08-04
### Fixed
- **Zotero Import Profile Edits No Longer Vanish After The First Keystroke**
  Changing a profile's template path from `.../book_template.md` to
  `.../paper_template.md` saved `.../boo_template.md` — the value after exactly
  one backspace. `saveSettings()` → `saveZoteroProfiles()` ends by assigning
  `settings.zoteroProfiles = store.profiles`, replacing the array and its
  objects with ones re-read from the merged on-disk store, while the settings
  editor had captured `settings.zoteroProfiles[index]` once at render time. The
  first keystroke's save therefore detached that reference and every later
  keystroke mutated an orphan nothing persists, so the edit looked applied in
  the field and was silently lost. Each write now resolves the live profile
  instead of a captured one. Because the editor has no Save button, fields also
  commit on blur, so leaving a field is always a durable save rather than
  relying on the last keystroke's in-flight write.

## [0.42.0] - 2026-08-04
### Added
- **`setup.sh` Provisions The `wiki` Alias**
  Setup previously provisioned no backend entry point, so users hand-rolled
  one — and a hand-rolled alias carried between machines is how a macOS install
  ended up pointing at a `/home/<user>/…` path that cannot exist there, silently
  degrading `wiki` to an unrelated install found on PATH. Setup now writes an
  alias whose target is derived from its own repository root. Re-running
  REPLACES the previous Incurator block (including the legacy undelimited
  form), so a wrong alias self-heals; other tools' blocks are preserved and the
  rc file is replaced atomically with its mode intact. Both `~/.zshrc` and
  `~/.bashrc` are handled, and a different `wiki` earlier on PATH is reported
  with both paths rather than silently winning. Skip with
  `INCURATOR_SKIP_ALIAS=1`.

### Fixed
- **Quick Query Popover Shows Elapsed Time Instead Of A Frozen Label**
  Measurement first: a CLI-backed provider round-trip costs 8.2–12.2 s for a
  one-word answer regardless of model or effort, while the CLI binary starts in
  0.29 s and an Incurator backend round-trip is 0.20 s — the wait is the
  provider service handshake, not inference and not Incurator overhead. Because
  `agy --print` cannot stream, the popover's static "Thinking…" was
  indistinguishable from a hang for the whole wait (an ambiguity that already
  caused a real crash to be misread as slowness). The popover now ticks elapsed
  seconds like the sidebar, stops on success, error, and teardown, and no longer
  lets the streaming callback overwrite the live readout with static text. The
  PDF reference-fetch path was deliberately left alone: it accounts for at most
  ~0.6 s of a ~13 s action, and its existing tests prove the common case already
  issues a single fetch.
- **Backend Version Checks Read Build Identity, Not Package Metadata**
  The plugin compared the backend's top-level `version` — installed package
  metadata — against its own bundled build manifest. An editable install freezes
  that metadata at the version it was first installed at while continuing to run
  current repository code, so the two could never agree and the "Run Setup"
  banner could never be cleared by running setup. Version checks now gate on
  `build.backend_version`, falling back to the metadata version only when no
  build manifest is present. Package metadata is now not consulted at all — not
  as a gate and not as a fallback, since the backend seeds
  `build.backend_version` unconditionally, so an absent value means the backend
  is too old to state its identity and is reported as exactly that. A mismatch
  message now also names the backend launcher that answered, so "this install is
  out of date" is distinguishable from "you are talking to a different install
  entirely".

## [0.41.1] - 2026-08-04
### Fixed
- **Deferred PDF Tabs No Longer Disable Chat, Popover, And Context Pins**
  Obsidian 1.7.2+ restores workspace tabs as *deferred* views whose `leaf.view`
  reports the real view type while carrying none of the concrete view class's
  methods. The plugin narrowed external-PDF leaves on that type string alone and
  then called `getRuntimePath()`, throwing
  `TypeError: getRuntimePath is not a function` out of the shared leaf resolver.
  Because that resolver feeds both the active-context capture and the open-tab
  inventory, a single restored PDF tab simultaneously blanked the purple context
  pins, made sidechat Send do nothing, and left the Quick Query popover on
  "Thinking" — and restarting Obsidian reproduced it, because a restart is what
  creates deferred tabs. Every external-PDF narrowing now goes through a
  capability-checked guard that also rejects stale instances left by an in-place
  plugin update; a deferred tab degrades to its persisted state instead of
  throwing, and is never force-loaded as a side effect of building context.
- **PDF Pages No Longer Collide On Their Own Canvas**
  Page canvases are reused across zoom, scroll, and document swaps, but the
  PDF.js render task was fire-and-forget, so a re-render could start while the
  previous one still owned the canvas — PDF.js then threw "Cannot use the same
  canvas during multiple render() operations" and left the page blank. Renders
  are now tracked per page and cancelled (and awaited) before the next render
  claims the canvas, including on document swap, reload, and view close. The
  existing render-token guard is unchanged; it stops work scheduled after a
  bump but never a task already inside PDF.js.

## [0.41.0] - 2026-08-03
### Added
- **Ask AI And Sidechat Can Turn PDF Pages**
  The reading assistant already received the document outline with page
  numbers, so it could reason "that result is in Appendix 4, around p.617" —
  but it had no way to get there and could only tell you to navigate yourself.
  It now has a read-only page reader for the PDF you already have open, used
  as a fallback after automatic reference-following: it covers references
  discovered only after reading the target page, targets named in your
  question rather than the selected text, and prose references carrying no
  number. Documents with no embedded table of contents additionally allow
  searching the pages already read, since there is no map to navigate by.

### Changed
- **Popover Tool Boundary Stated Precisely**
  The Quick Query popover's tool policy moved from "no tools at all" to
  "no MCP tools, no filesystem, no scripts, plus the bounded PDF page reader".
  The zero-MCP guarantee is unchanged and is now locked by behavioral tests
  rather than by prompt wording. The reader refuses page numbers outside the
  open document, stops after a bounded number of fetches per question, is not
  offered at all when no PDF is open or the page count is unknown, and refuses
  to read across a document swapped mid-request. CLI providers (Antigravity
  `agy`, Claude, Codex) are excluded and keep the deterministic path, so the
  v0.23.0 sandbox contract is untouched.

---

## [0.40.3] - 2026-08-03
### Fixed
- **Correct Target Pages For PDF Cross-References**
  Ask AI / Sidechat pointer resolution no longer injects the wrong physical
  page for printed-page locators in books with front matter (e.g. selecting
  `From Result A4.1-(p581)` used to inject Appendix A1 tensor-notation text
  from physical page 581 instead of Result A4.1 on printed page 581). Printed
  pages now map through PDF page labels, a consensus front-matter offset
  inferred from printed header/footer numbers, and a printed-header scan; the
  literal identity guess survives only until the fetched page's own header
  disproves it, in which case resolution fails closed and a single bounded
  repair fetch retrieves the correct page. Theorem-family references accept
  appendix-lettered numbers (`Result A4.1`, `Corollary B2.3`), their
  definition lines join the caption index, and `Appendix 4`-style ToC titles
  answer to `A4`-style anchors for outline-range expansion.

---

## [0.40.2] - 2026-08-01
### Fixed
- **Explicit Retrieval Degradation**
  Runtime query-embedding failures now set lexical fallback and emit a stable
  `vector_failed` warning, including for vector-only queries without inventing
  lexical hits. Invalid reranker output preserves the complete RRF candidate
  order and reports `reranker_failed` instead of silently dropping candidates.
- **Exact Finite Provider Results**
  Corpus embedding batches and reranker responses must match request
  cardinality exactly and contain only non-empty finite numeric results.
  Invalid embedding batches persist nothing and count every requested chunk as
  failed.
- **Truthful Prompt Provenance And Versions**
  Prompt traces now finalize provider/model attribution from the provider that
  produced the final response after failover. Prompt versions are validated as
  numeric `vN[.N...]` identifiers, so latest lookup and listing place `v10`
  after `v9`.

---

## [0.40.1] - 2026-08-01
### Fixed
- **Independent Provider Cancellation And CLI Fidelity**
  Overlapping sidebar and Quick Query requests now own independent cancellation
  signals, so closing one popover cannot stop another request and foreground
  cancellation returns to an older still-active sidebar request. Caller-owned
  popovers never replace the sidebar Stop target; cancellation during context
  preparation launches no provider transport, and Ollama preserves normal
  `AbortError` semantics. Streaming and non-streaming CLI children bind to the
  correct request; non-streaming calls also preserve their per-call model and
  GUI-safe PATH/temp environment.
- **Collision-Safe MCP Lifetimes**
  Sanitized model-facing MCP tool names now dispatch through an explicit unique
  route map instead of lossy reverse parsing. Shutdown rejects pending JSON-RPC
  work, clears request timers, waits through bounded TERM/KILL escalation, and
  ignores late exit and stdout events from a replaced server generation. Each
  restarted generation begins with a fresh JSON framing buffer.
- **Bounded Plugin Backend Commands**
  The vault-local backend runner now applies separate normal and long-operation
  timeout/output policies. Hung or overproducing subprocesses fail visibly and
  settle once, while pipeline, import, model, and job commands retain larger
  limits suitable for legitimate long work.

---

## [0.40.0] - 2026-08-01
### Changed
- **Obsidian 1.1.0 Minimum**
  Existing synced session and Zotero-profile commits now use Obsidian's atomic
  adapter processing API. The plugin therefore requires Obsidian 1.1.0 or
  newer; `versions.json` keeps v0.39.2 available to Obsidian 1.0.x users.

### Fixed
- **Fail-Closed Plugin Persistence**
  Chat-session and Zotero-profile storage now distinguishes missing state from
  corrupt or unreadable canonical files. Invalid files remain untouched and
  block ordinary saves. Existing valid files parse and merge the canonical text
  supplied at the atomic commit boundary, preserving peer arrivals and deletion
  tombstones; interrupted commits and initial temp writes preserve canonical
  bytes and clean temporary siblings.
- **Durable Secret And Config Updates**
  Encrypted-secret and YAML-config mutations now hold per-target locks across
  fail-closed read/merge/write operations and commit through flushed temporary
  files. Project saves merge into the freshly locked mapping so peer-only
  nested keys survive. Existing ordinary config modes are preserved, new files
  follow normal umask semantics, and secret temps are private from creation;
  corrupt state and interrupted replacement leave prior bytes and modes intact.
- **Recursive Runtime Credential Redaction**
  Plugin-readable runtime snapshots now remove credential-bearing keys at every
  nested mapping and array depth while retaining non-secret provider, model,
  and feature selections.

---

## [0.39.2] - 2026-08-01
### Fixed
- **Latest-User PDF Equation References**
  Sidechat now recognizes explicit equation pointers in the latest question,
  including `수식 (10)`, and refreshes a bounded next-first adjacent page through
  the existing read-only PDF context API when the loaded window lacks the target
  body. Resolved evidence is supplied before generic PDF context, so external
  Zotero/iCloud PDFs remain outside provider filesystem roots and no native
  `read_file` or `command` permission is needed. Resolution now fails closed
  when the bounded scan finds no exact equation label, and latest-question
  pointers are scoped to the active or explicitly attached primary PDF instead
  of being claimed by background PDF tabs.

---

## [0.39.1] - 2026-07-30
### Fixed
- **Complete Source Lifecycle Closure**
  Local source removal and imported source tombstones now retire/discard the
  complete authoritative generation, claim, graph-support/report, synthesis,
  span, projection, and search dependency closure. Shared graph knowledge
  remains only while another live source supports it, and serving/search paths
  fail closed on missing source provenance.
- **Deterministic Projection Recovery**
  Compiler publication now persists stable Atom ids, DAG edges, and dependency
  rows before writing derived files. A post-publish filesystem/search failure
  or process interruption keeps the authoritative generation and retries
  through DB-backed re-emission without another LLM call or generation.
  Re-emission refreshes only generated ATM/CON/SYN page hashes and removed
  orphan CTX hashes, so preserved CTX edits remain detectable; normal compiles
  update only their source projection instead of rebuilding the whole corpus
  per source.
- **Replica And Autosync Monotonicity**
  Tombstones cannot be backdated, mutable local reinserts advance strictly past
  future-clock deletes, immutable tombstoned rows fail closed, and malformed
  current-schema peer headers stop autosync visibly without checkpointing.

---

## [0.39.0] - 2026-07-30
### Added
- **Authored-Note Graph Topology**
  Registered visible Markdown notes now compile exact internal wikilinks,
  embeds, tags, and frontmatter wikilinks into deterministic `authored` graph
  relations. Exact vault-root/source-relative paths, unique names, and unique
  frontmatter aliases resolve; ambiguous, external, hidden, unsafe, and
  unresolved targets fail closed.

### Changed
- **Active-Only Graph Serving**
  Explore memory paths, graph status, search materialization, and community
  construction consume only active canonical topology. Authored edges may shape
  membership and dependency identity, but only independently supported
  extracted relations enter factual report relation ids and citations.

### Fixed
- **Atomic Lifecycle And Replica Convergence**
  Authored topology publishes and reconciles inside the existing compiler
  generation transaction, including edit/rename/delete retirement and failed
  publish rollback. Unicode-NFC portable IDs converge across devices; import
  restores one authoritative generation per source and retires losing authored
  rows. Relation re-assertion now preserves existing lifecycle metadata unless
  explicitly replaced.
- **Adversarial Authored-Topology Correctness**
  Masked Markdown no longer joins unrelated text into invented links or tags;
  escapes, numeric-only pseudo-tags, fenced blocks, balanced destinations,
  vault-bounded parent paths, `.markdown` notes, and ambiguous resolution obey
  the fail-closed contract. Generation audits retain exact authored membership,
  clock-skewed replica merges preserve shared edges, DB-only/type-change
  republishes cannot leave discarded-generation ownership, topology additions
  invalidate stale reports, and rematerialization removes authored search
  ghosts. Follow-up review hardening also reconciles lone generations after
  source tombstones, enforces exact audit membership at lifecycle admission,
  advances repair/retirement LWW clocks strictly, preserves winner-dependent
  reports, accepts balanced nested Markdown labels, and decodes targets once.

---

## [0.38.0] - 2026-07-30
### Added
- **Grounded Sidechat Vault Wikilinks**
  Every selectable Sidechat provider now shares one exact-path wikilink
  contract. Prompt-included note paths and usable ContextService locators retain
  vault-relative Markdown, PDF, heading, and block targets so answers can open
  the referenced page directly in Obsidian.

### Fixed
- **Fail-Closed Link Grounding**
  Sidechat no longer needs to infer a target from a display label. External,
  stale, unavailable, duplicate-anchor, source-fallback, absolute, and traversal
  locators are withheld from provider link targets, while uncertain plain text
  is left unchanged instead of being post-processed into a guessed link.

---

## [0.37.1] - 2026-07-30
### Fixed
- **Provider Failure Normalization**
  Ollama, Claude, and Codex now reject blank output consistently. Codex rejects
  non-zero processes before reading any partial output file, every `LLMError`
  subtype participates in configured failover, and an exhausted chain retains
  bounded provider-labelled attempt diagnostics with its terminal cause.
- **Traceable Query Failures**
  Provider and structured-output repair failures now retain their query trace,
  failed prompt traces, evidence provenance, warnings, retry count, first-output
  hash, and failed synthesis action. Unexpected runtime and storage defects
  continue to propagate instead of being mislabeled as provider failures.
- **Consistent Query Failure Surfaces**
  `wiki query` prints non-streaming success answers and exits non-zero with a
  concise expected-failure message. MCP and plugin queries share one existing
  response serializer, the hidden plugin command emits one JSON failure object
  before exiting non-zero, and the plugin trace panel preserves and displays
  the failure reason, prompt trace ids, and warnings.

---

## [0.37.0] - 2026-07-30
### Changed
- **Schema-v13 Composite Tombstone Contract**
  Composite-primary-key deletes now use a closed, versioned canonical-JSON key
  registry. Source page keys carry `sources.sync_key` instead of replica-local
  numeric ids, malformed or legacy ambiguous tokens fail closed, and v12/v13
  snapshots never partially interoperate.

### Fixed
- **Cross-Device Delete Convergence**
  All six synchronized composite-key tables now delete by their complete key.
  Equal/newer tombstones block stale rows, strictly newer mutable rows clear an
  older tombstone, immutable rows cannot resurrect, and dry-run remains
  read-only. Local PDF provenance, claim-support, artifact-dependency, relation
  support, and entity-lineage writers clear or emit exact tombstones as rows
  become live or absent. First-import dry-runs now resolve source-scoped keys
  from the incoming source map, so their counts match the real pass without
  writing parent or child rows.
- **Transactional Source Tombstones**
  Imported and local source deletion now share one dependent-cleanup path for
  job events, jobs, ingest runs, page provenance, DAG edges, and PDF pages.
  Delete, tombstone recording, and import statistics remain atomic per file.

---

## [0.36.8] - 2026-07-30
### Fixed
- **PDF Convert-to-LaTeX Antigravity Prompt Transport**
  The backend now sends the complete PDF transcription request as the
  `agy --print` prompt instead of placing it on ignored stdin behind a generic
  placeholder. It also passes the exact selected `--model`; dedicated extraction
  slots use `low` when supported and omit effort for fixed/no-effort models.
  The plugin's Antigravity chat command now forwards its selected model as well,
  and the catalogue uses the live `claude-opus-4-6-thinking` slug. Convert to
  LaTeX therefore preserves the selected prose, rewrites equations with LaTeX
  delimiters, and no longer copies Antigravity scratch-workspace planning
  narration as a successful result.
- **MCP 2.0 Dependency Boundary**
  Fresh validation environments now retain the supported MCP Python SDK 1.x
  line. MCP 2.0 removed the `mcp.server.fastmcp` API used by the current server
  and previously caused fresh GitHub Actions mypy runs to fail before pytest.

---

## [0.36.7] - 2026-07-26
### Fixed
- **Antigravity Hotfix Activation**
  Provider startup now verifies the running Obsidian bundle against the active
  vault's installed `main.js` and manifest before authentication or CLI launch.
  A copied-but-not-reloaded hotfix is blocked with a reload instruction instead
  of silently continuing with stale permission code. The update action requires
  all three plugin artifacts and then performs an actual Obsidian renderer
  reload.
- **Complete Open-Tab Context Inventory**
  The purple context row now enumerates every open Markdown/PDF tab, including
  hidden members of tab groups. Visible tabs default to included; hidden tabs
  default to eye-off and cannot enter tab lists, bodies, outlines, edit targets,
  or continuity context until explicitly included and materialized. Exact
  source/page keys preserve distinct PDF pages and prevent stale cached PDFs
  from returning after tabs close.

---

## [0.36.6] - 2026-07-23
### Fixed
- **Purple Pin Zotero Source Registration**
  Purple Pin's **Add source** action now preserves the Zotero attachment key as
  the portable source identity when the plugin also supplies its already
  resolved local-filesystem PDF path, including linked attachments. Valid
  Zotero references on macOS and Linux no longer fail with `root_unregistered`
  when generic `external.path_roots` is empty, while unregistered non-Zotero
  external paths remain blocked.

---

## [0.36.5] - 2026-07-22
### Fixed
- **Zotero Import Case-Collision Refresh**
  `Import Zotero Item` now updates an existing note when Zotero metadata renders
  a filename that differs only by letter case and the filesystem reports
  `EEXIST`. The existing filename and persisted template regions are preserved,
  while the selected item's current metadata and Zotero parent/attachment links
  replace stale values. Unrelated create failures remain visible.

---

## [0.36.4] - 2026-07-22
### Fixed
- **Antigravity Headless PDF Reads**
  Antigravity CLI 1.1.3+ no longer auto-denies `read_file` when the Obsidian
  Agent summarizes an open PDF. The plugin atomically preserves and merges the
  narrow `$read_file$()` rule into the live
  `~/.gemini/antigravity-cli/settings.json`, refuses to overwrite malformed
  settings, and removes the ineffective v0.36.3 TOML artifact only when it still
  bears Incurator's generated-file marker. Existing `--add-dir` visibility and
  OS write containment remain unchanged.
- **Gemini 3.6 Flash Effort Forwarding**
  Antigravity CLI 1.1.5+ now receives the selected `--effort` value for base
  model slugs such as `gemini-3.6-flash`, which otherwise fail before inference.

---

## [0.36.3] - 2026-07-22
### Fixed
- **Headless `agy` CLI `read_file` Policy Auto-Sync**
  `syncAgyMcpConfig()` now automatically syncs a `read_file` policy to `~/.gemini/policies/incurator-read.toml` scoped to the plugin's allowed roots (vault + Zotero). This prevents headless `agy` (`-p --sandbox`) from auto-denying file reads following the v0.23.0 removal of `--dangerously-skip-permissions`.

### Added
- **Gemini 3.6 Flash Support in Antigravity Model Catalogue**
  Added `gemini-3.6-flash` ("Gemini 3.6 Flash") to the single-source model catalogue (`backend/src/curator/data/models.json`) under the `antigravity` provider options.

---

## [0.36.2] - 2026-07-20
### Fixed
- **Fail-Closed Knowledge Sync**
  Existing unreadable, malformed, or wrong-shaped device-local sync state now
  fails without replacing the device identity or peer high-water marks. Peer
  import and conflict archive failures are surfaced with file context, and a
  conflict is reported as merged only after import and archive both complete.
- **Transactional Tombstone Deletes**
  Imported tombstones no longer suppress target-row deletion errors. A failed
  delete rolls back the input-file transaction instead of recording and
  propagating a deletion that did not occur locally.
- **Workspace Policy Integrity**
  ContextService and QueryOrchestrator now use one validated `curate.yml` policy
  resolver. Existing malformed KRS files, invalid source-scope shapes, semantic
  validation errors, and policy hash/read failures stop before retrieval or
  synthesis rather than widening to the unrestricted default policy.
- **CLI Query Scope And Read-Only Behavior**
  `wiki query --workspace` now forwards the selected workspace into the shared
  policy boundary and reports invalid KRS configuration without starting the
  provider or printing a traceback. Query no longer runs pending ingestion as a
  hidden side effect; `wiki add` and `wiki build` remain explicit operations.
- **Validation Cache Isolation**
  The backend check helper now pins pytest to the backend configuration and the
  repository `.cache/pytest` directory even when callers pass only CLI options,
  preventing local validation from creating a forbidden root `.pytest_cache`.
- **Curation Plan Persistence Guard**
  MCP and hidden plugin planning surfaces validate the KRS before inserting a
  `curation_plans` row; invalid plans return failure and the plugin command exits
  non-zero without leaving a database side effect.

---

## [0.36.1] - 2026-07-19
### Fixed
- **Observable Runtime Degradation**
  Replaced silent broad-exception handlers in decomposed CLI, MCP, and plugin
  API internals with specific catches or logged best-effort fallbacks while
  preserving established command and tool boundaries.
- **MCP False Success And Missing Warnings**
  Synchronous source builds no longer report success when no per-source result
  is produced. Successful builds and knowledge promotions now return warnings
  when their follow-up search refresh cannot run.
- **Provider Model Catalogue Loading**
  Restored `curator_get_provider_config` model discovery after the MCP module
  move by loading `models.json` from packaged resources. This makes the current
  Claude Code and Codex model catalogue visible to Obsidian again.
- **MCP And Guide Contract Parity**
  Corrected the documented provider-setting parameters and recorded the actual
  build, knowledge-promotion, and provider-config result behavior.

---

## [0.36.0] - 2026-07-19
### Changed
- **Plugin Module Ownership**
  Moved the chat sidebar, LLM client, and external PDF view implementations into
  dedicated internal packages while preserving their established import paths,
  class names, view types, persistence formats, provider behavior, and UI flows
  through stable public facades.

### Fixed
- **External PDF Documentation Parity**
  Corrected the English/Korean plugin guides to describe portable Zotero and
  external-reference restoration instead of the removed persisted absolute-path
  behavior.
- **Review Lifecycle Hardening**
  Prevented concurrent abort/stream requests from clearing each other's request
  controllers, invalidated in-flight PDF renders on view close, and guarded MCP
  child stdin plus omitted server argument arrays.

---

## [0.35.0] - 2026-07-19
### Added
- **Current Claude Code and Codex CLI Models**
  Updated the shared backend/plugin catalogue for Claude Sonnet 4.6, Fable 5,
  Opus 4.8, and Haiku 4.5, plus Codex GPT-5.6 Sol, Terra, Luna, and GPT-5.5.
  Model-specific context capacities, effort choices, and defaults now drive all
  model pickers from the same contract.

### Fixed
- **Model-Specific Effort Handling**
  Settings, the chat sidebar, the dashboard, and stored-setting migration now
  normalize effort when a model changes. Models without an effort dimension
  clear stale values and omit the CLI flag; Claude vision calls now preserve a
  configured effort, while Codex supports the current `max` and `ultra` levels.

---

## [0.34.1] - 2026-07-19
### Fixed
- **Endless Obsidian Knowledge Sync**
  Made current-schema full-snapshot import content-idempotent for composite-key
  and immutable rows. Equivalent snapshots with fresh `export_id` values no
  longer report thousands of false updates and trigger cross-device re-export
  ping-pong. Dry-run now honors recorded peer high-water marks, and the plugin
  watcher ignores its known self snapshot instead of treating it as incoming
  peer data.
- **Plugin Lockfile Version Drift**
  Restored `plugin/package-lock.json` parity with the backend, plugin package,
  and Obsidian manifest versions.

---

## [0.34.0] - 2026-07-09
### Changed
- **Command Module Decomposition**
  Split the backend CLI, MCP server, and plugin API god files into modular
  package structures while preserving existing command names, MCP tool
  contracts, plugin API functions, and backward-compatible import facades.

### Fixed
- **PR #85 Review Hardening**
  Closed command-layer LLM clients in persona, workspace, and plugin PDF
  transcription flows; made `wiki models ensure` degrade gracefully when no
  vault exists; and replaced per-row source status resets with batch updates.
- **Extracted CLI Facade Compatibility**
  Restored `curator.cli.list_models_on_host` patch compatibility for extracted
  plugin model commands so CI and legacy tests observe mocked Ollama installs.

---

## [0.33.0] - 2026-07-07
### Changed
- **Strict Sync Schema Enforcement (Removal of Legacy Compatibility)**
  All backward-compatibility logic for parsing pre-v12 database schemas and legacy `last_imported_mtime` / `added_at` timestamps has been strictly removed. The system no longer attempts to automatically migrate or inject synthetic timestamps for malformed rows during P2P sync. Peer snapshots with incompatible schemas or missing `export_id` headers will now be skipped entirely rather than triggering partial imports. 
- **DB Initialization Speedup (Dead Code Removal)**
  The `init_db` and `connect` startup pathways have been significantly simplified by deleting over 700 lines of obsolete `v12` data-migration logic and fallback checks. Vault connections now start faster as they no longer perform redundant schema validation against legacy formats.

---

## [0.32.2] - 2026-07-06
### Fixed
- **`wiki db autosync` no longer crashes on pre-v12 peer export files.**
  After the v0.32.1 schema upgrade (v11 → v12), `_read_export_id` hard-crashed
  with `ValueError: Missing export_id in export header` when encountering legacy
  peer snapshots that lacked the `export_id` field introduced in v12. The plugin
  surfaced this as `"Empty response from backend"` and a persistent
  `"⚠ Sync Failed"` status bar / `"Auto-sync failed"` notice. `_read_export_id`
  now returns `None` for incompatible peer files (wrong schema version, missing
  `export_id`, malformed headers), and `import_all_peers` skips them with a log
  warning. Once peer devices upgrade and re-export v12 snapshots, their files
  are imported normally.

---

## [0.32.1] - 2026-07-06
### Changed
- DB schema upgraded to v12. Sources carry a `sync_key` column — a portable
  transport identity for cross-device JSONL sync. Local integer `id` values
  remain replica-local; imported child `source_id` foreign keys are remapped to
  the receiving device's ids on import.
- `compiler_generations` rows now have an `updated_at` column, making generation
  status transitions participate in monotonic LWW sync and preventing stale
  snapshots from regressing authoritative state.
- JSONL export headers include an `export_id` (UUID). Import rejects snapshots
  without one, preventing same-mtime snapshot confusion across replicas.
- JSONL import validates all table names and column names against an allowlist
  derived from the local schema, rejecting unknown tables and columns.
- Device-local state — `state.sqlite`, runtime, staging, sync reports, event
  log, PDF page/crop caches, and conflict archives — now lives under the
  Incurator repository `.cache/vaults/<vault-key>/` instead of the synchronized
  vault `.curator/`. The vault hash is derived from the resolved vault root. A
  one-time migration moves the existing `.curator/state.sqlite` (and sidecars)
  to the new location; if both old and new DB files exist, the backend aborts
  with explicit recovery instructions.
- Plugin session saves are serialized to prevent concurrent writes from
  corrupting the session store.
- Zotero profile store supports explicit deletion tombstones and serialized
  saves, preventing profile resurrection after cross-device sync.

### Fixed
- Cross-device source convergence no longer relies on integer primary keys.
  Two independently allocated `id=1` sources with different `sync_key` values
  converge to two distinct local sources with correct child provenance.
- Source deletion propagates via `sync_key` tombstones. Deleted sources stay
  deleted even when a stale pre-deletion snapshot is replayed from another
  device.
- Plugin temporary files (CLI output, PDF crops) are written to the repo cache,
  not the vault `.curator/` directory, preventing them from syncing across
  devices.

---

## [0.32.0] - 2026-07-04
### Changed
- External source configuration now accepts only the current
  `external.path_roots` / integration `root_keys` contract. Legacy root arrays
  are no longer converted or used for runtime source discovery.
- Absolute non-reference `sources.relpath` values are no longer treated as
  runtime filesystem paths.

### Removed
- Removed the `wiki paths` command group, the standalone portable-path migration
  service, and the pre-v0.29 `sources.external_path` / `sources.import_origin`
  table converter from DB initialization.

### Fixed
- Normalized the affected macOS device-local `second_brain` DB to schema 11
  before deployment, preserving its three Zotero attachment keys and removing
  the `wiki status` migration error.

---

## [0.31.0] - 2026-07-03
### Changed
- Dashboard L1-L4 density counts now come from authoritative serving DB records,
  not disposable Collection Markdown projections.
- Source rows have a schema-v11 `updated_at` revision, so status-only L1-L4
  changes participate in cross-device LWW sync.

### Fixed
- L3 is no longer reported complete when no live source-grounded community
  report exists; empty successful passes are terminal `skipped`.
- Emitted Zotero reference stubs resolve their `zotero_attachment_key` directly,
  and failed CTX projection repair no longer downgrades valid L1 DB state.
- JSONL snapshots and sync state use atomic replacement; MCP/worker mutations
  export automatically and compound `wiki update` runs export once.
- Zotero profile writes are serialized read-merge-write operations, preserving
  peer-only profiles and recent items.

---

## [0.30.0] - 2026-07-02
### Added
- **Zotero import profiles now sync across devices.** `zoteroProfiles` and the
  `recentZoteroItems` LRU moved from the plugin's device-local `data.json` to
  `.curator/zotero_profiles.json` inside the vault (the `sessions.json`
  pattern), so a profile created on one machine appears on the others after
  Syncthing sync. Existing profiles are migrated automatically and
  non-destructively on first load; `data.json` never carries profiles again.
- `wiki db autosync --dry-run` now reports whether an export is pending
  (`would_export`, text + `--json`), making a stale never-shipped snapshot
  visible without mutating anything.

### Changed
- **Cross-device knowledge auto-sync is now default-on (opt-out).**
  `auto_sync.enabled` defaults to `true`, and the snapshot export hook runs
  after every mutating CLI command — `wiki add`, `wiki build` (both `--wait`
  branches), `wiki sync`, `wiki update`, and `wiki jobs run` (covering the
  detached daemon spawned by background builds) — LWW-gated so unchanged state
  is never re-exported. Set `auto_sync.enabled: false` in
  `.curator/settings.yml` to opt out.

### Fixed
- **Dashboard on a second device showed a stale, smaller source count (e.g. 5
  instead of 31).** Root cause: every autosync export trigger was opt-in — the
  hook was wired only into `wiki update`, `auto_sync.enabled` defaulted to
  `false`, and disabling the plugin (`incuratorEnabled: false`) on a
  CLI-primary device silently killed all plugin-side triggers — so the device
  that ingested sources never re-exported its snapshot and peers kept
  converging on an old one. Mutating CLI commands now always publish the
  snapshot (see Changed above).
- **Zotero import profiles differed per device** because they lived in the
  unsynced `data.json` (see Added above).

---

## [0.29.1] - 2026-07-02
### Fixed
- **Side chat sidebar is blank after upgrading to v0.29.0.** The v0.29.0 portable
  path storage changes introduced four interacting regressions that collectively
  prevented the chat sidebar from rendering:
  - `isRetainablePersistedDoc` silently dropped all legacy path-only external PDF
    documents from `localStorage` on startup, causing `ExternalPdfView` to lose its
    file identity and fail to resolve the PDF path for any non-Zotero local PDF.
  - `loadPersistedDocs` omitted `path` from the in-memory registry even for docs
    that had one, so `resolveDoc()` could not find the PDF after restart.
  - `syncState()` in `ExternalPdfView` rebuilt `docState` via `buildSyncedExternalPdfState`
    which dropped the runtime `path` field, permanently losing the path from `docState`
    after any zoom/page-change interaction.
  - `ChatSidebarView.onOpen()` called `renderContextChips()` without error handling;
    any exception thrown while iterating partially-initialized `ExternalPdfView` leaves
    aborted the entire `onOpen()` flow, leaving the sidebar blank.
  - `main.ts:getLeafFile()` used `getState().path` to identify external PDF leaves,
    but v0.29.0's `getState()` strips `path` before returning — so external PDF
    leaves were invisible to the open-tab context builder.

  All five vectors are fixed: path-only docs are retained (the reopen prompt already
  handles gracefully missing files), `loadPersistedDocs` restores path into the
  in-memory map, `syncState()` preserves the runtime path in `docState`,
  `getLeafFile()` uses `getRuntimePath()` as the primary source, and `onOpen()`
  wraps the initial chip render in a guard so one bad leaf cannot blank the sidebar.

## [0.29.0] - 2026-07-02
### Changed
- Replaced persisted absolute Reference Mode paths with portable identity.
  Zotero sources and plugin PDF views now store only the effective attachment
  key and resolve through the current device's Zotero database. Generic
  external sources store `@<root_key>/<relative-path>` backed by machine-local
  roots in repo `.cache/config/config.yml`.
- Added transactional schema-v10 migration with dry-run, ignored cache backup,
  vault-relative stub repair, dependent PDF-page/span repair, and v10 sync
  export regeneration.
- Removed absolute PDF paths from plugin localStorage, Obsidian view state,
  sessions metadata, and persisted backend/repository/Zotero path overrides.

## [0.28.5] - 2026-07-01
### Fixed
- **Plugin runtime status/source snapshots no longer export absolute local paths.**
  Backend-written `.curator/runtime/status.json` and `sources.json` now keep
  source identity portable, clear `external_path`, hide vault/model/cache paths,
  and sanitize machine-local config blocks. Device-specific paths remain in the
  repository-local `.cache/config/config.yml` and are resolved through backend
  commands only when needed.
- **The Obsidian plugin no longer falls back to stale global `wiki` commands.**
  The default `wiki` setting now resolves to the repository-root
  `.venv/bin/wiki` only. The plugin refuses unresolved PATH launchers, may use a
  memory-only sibling `Incurator` repo hint without writing it to `data.json`,
  and records per-device launcher hints in repo-local `.cache/config/devices.json`.

## [0.28.4] - 2026-07-01
### Fixed
- **`curate.yml.vault_root` is now device-portable.** Workspace provisioning
  writes `vault_root` relative to the workspace directory (e.g. `../..` for an
  in-vault workspace; the matching `../…` hop for a workspace outside the vault)
  instead of baking in the generating device's absolute path, so a synced
  `curate.yml` stays valid across machines whose vault lives at a different mount
  point. The MCP fallback now resolves a relative `vault_root` against the
  workspace directory rather than the process CWD, and re-running `workspace init`
  heals only a genuinely stale `vault_root` while preserving any value (relative
  or absolute) that already resolves to the active vault. The per-device
  `VAULT_ROOT` env var remains authoritative when the MCP server is running.
- **Workspace initialization no longer leaks Incurator repository workflow
  rules into generated workspaces.** `wiki workspace init` and
  `curator_workspace_init` now render only Curator navigation hooks into the
  selected agent rule file, keep `curate.yml.vault_root` as the vault-root
  source of truth, and avoid injecting repo-local roadmap, inbox, draft-plan, or
  release-workflow instructions.
- **Codex workspace provisioning uses the workspace-agent slug consistently.**
  Codex client detection now resolves to `codex` rather than the LLM-provider
  slug `codex-cli`, and shared `AGENTS.md` managed blocks are rendered only for
  the selected/detected runtime instead of being overwritten by Antigravity.

---

## [0.28.3] - 2026-06-29
### Fixed
- **MCP source registration no longer hides skipped search-index refreshes.**
  `curator_register_source` now returns a success `warnings` array when L1
  registration succeeds but the non-fatal DB-native search-index refresh is
  skipped, and unexpected refresh errors are no longer swallowed.

---

## [0.28.2] - 2026-06-29
### Fixed
- **Plugin source registration no longer hides skipped search-index refreshes.**
  `wiki plugin source register` now returns a success `warnings` array when L1
  registration succeeds but the non-fatal DB-native search-index refresh is
  skipped, and unexpected refresh errors are no longer swallowed.

---

## [0.28.1] - 2026-06-29
### Fixed
- **CLI best-effort maintenance failures are no longer silent.** `wiki init`
  now warns when a known MCP client config target cannot be updated — including a
  wrong-shaped config (e.g. a non-object top-level document or a non-object
  `mcpServers` value, which previously raised an uncaught `TypeError`) — while
  still continuing with other targets and completing vault initialization. `wiki
  config provider` and project-scoped `wiki config set --local` now warn (never
  crash) when expected dashboard runtime snapshot refresh failures occur — not
  just write errors, but also a plugin-locked `state.sqlite` or, for `config
  set --local`, a malformed merged config — without rolling back the
  already-successful config write.
- **Root-level plugin validation command works again.** `plugin/vitest.config.ts`
  now pins the plugin directory as Vitest's root, so
  `npx vitest run -c ./plugin/vitest.config.ts` discovers plugin tests when run
  from the repository root.

---

## [0.28.0] - 2026-06-29
### Changed
- **PDF chat crop (Cmd+Shift+X) now passes the image DIRECTLY to a vision-capable
  main chat model instead of a redundant backend VLM round-trip.** The backend
  `plugin pdf transcribe` resolver, in the default config, resolves to the SAME
  provider CLI the chat already uses (`latex_extract_model → vision_model →
  main-if-vision`) — so a crop was transcribed by one CLI call and then re-sent in
  a second CLI call to the same model. Now, when the main chat model is
  vision-capable (antigravity / claude / codex — all live-verified), the crop image
  is read directly by that model through a scoped CLI image channel, with the
  pymupdf region text riding along as a caption. A non-vision main model (text-only
  Ollama) still falls back to backend transcription. (SYSTEM_BEHAVIOR §26.2a
  revised; PLUGIN_SCHEMA §2.1.3 added.)
- **Interactive chat image channel (claude/agy/codex CLI).** Chat images (crops,
  pastes, PDF-page captures) are written to `<repo>/.cache/cli/chat_images/<run>/`
  and referenced by path; image-bearing CLI turns enable scoped `Read` +
  `--add-dir <that dir>` (claude drops `Read` from its denylist only for those
  turns) so the same model can open them. For claude — the only provider whose
  `Read` is denied by default — the image-turn `--add-dir` is confined to JUST the
  image dir (NOT the broad allowed roots), so the re-enabled `Read` cannot reach
  arbitrary vault/Zotero files and the v0.23.0 no-vault-read hardening still holds.
  Text-only turns keep the hardened no-`Read` denylist; DB-scoped MCP curator tools
  stay available; every invocation stays inside the OS sandbox (v0.23.0). Temp PNGs
  are removed in the CLI/stream `finally` (success, error, abort) — including when
  pre-spawn setup throws — and stale dirs are swept on startup.

### Fixed
- **Send no longer freezes for ~1 minute on a PDF crop.** v0.27.9 only relocated
  the blocking VLM call to send-time, where it still ran BEFORE the "Thinking…"
  indicator rendered, so Send looked frozen until transcription finished. The
  deferred materialize now runs AFTER the assistant thinking message is rendered;
  on the vision-passthrough path there is no transcription round-trip at all, so
  Send is instant.
- **Quick Query popover now follows distant PDF references.** A selected pointer
  like `Section 11.1.2, p281` now treats the explicit page locator as a fetchable
  target, while bare object labels like `(3.5)` use the PDF outline to fetch a
  bounded candidate page range. Exact ToC section matches are tried before wider
  chapter fallbacks, fetched in small batches, and stopped as soon as the target
  is found, so the popover does not scan a large chapter before answering. The
  fetched target text is sent in `<resolved_cross_references>` instead of
  answering from only the current page window.
- **PDF page fetches now share the backend page cache across sidechat and
  popover.** Quick Query uses the same backend PDF context path as sidechat
  before falling back to the open PDF.js viewer. Backend `plugin pdf context`
  reads and writes `.cache/pdf_pages/<content_hash>/<page>.txt` when a registered
  source or file hash is available, so repeated page lookups avoid reparsing
  PDFs. `04_Resources` Reference Mode stubs keep portable identity only; absolute
  local paths remain per-device backend hints and are not written to synced
  stubs. Missing or invalid PDF content hashes no longer crash page lookup, and
  backend/network failures now fall through to the open PDF.js viewer.
- **Runtime temp/cache files stay inside Incurator-owned roots.** PDF crop
  transcription now writes temporary images under the vault's
  `.curator/runtime/pdf_crops/`; plugin CLI cache falls back to
  `.curator/runtime/cli/` instead of OS temp when the repo path is unknown; backend
  CLI logs/output and Zotero SQLite lock-bypass copies now live under repo
  `.cache/`; and provider CLI subprocess `TMPDIR`/`TEMP`/`TMP` values point at
  those allowed cache roots.

---

## [0.27.9] - 2026-06-29
### Fixed
- **PDF crop (Cmd+Shift+X) now shows the context chip instantly.** VLM
  transcription was blocking at capture-time, delaying the chip appearance and
  prematurely showing the "Add source" badge. The VLM call is now deferred to
  send-time (`materializeContextRefs`), so the crop image thumbnail and region
  text appear in the sidebar immediately after snipping.

---

## [0.27.8] - 2026-06-29
### Changed
- **DB-2 (slice 2): `jobs.py` + `sources.py` carved out of `db/_entities.py`.**
  Continuing the `db/` package decomposition, the ingest job queue moved to
  `db/jobs.py` and the sources / layer-status / DAG-edge / source-page functions
  to `db/sources.py` — byte-for-byte verbatim moves. Both are dependency-leaves
  (import only `db.schema`; no import cycles), and the public `db.*` surface is
  unchanged (guarded by `test_db_public_api.py`). Internal-only; no SQL, schema,
  contract, or behavior change. (The graph/community/knowledge cluster and the
  leaf entity modules remain in `db/_entities.py` for a later slice.)

### Fixed
- **Small pre-existing bugs in the carved `db/sources.py` functions** (surfaced in
  review of the moved code): `get_pending_count` (which queries the `sources`
  table) moved from `jobs.py` to `sources.py`; `vision_cache_put` /
  `update_page_hash` now write UTC timestamps via `_now_iso()` instead of
  timezone-naive `datetime.now().isoformat()`; and `get_source_row`'s
  `resolved_lookup` defaults to `None` (binds SQL `NULL`) instead of `""`, so a
  relative-path lookup can no longer accidentally match empty `external_path` /
  `import_origin` rows.

---

## [0.27.7] - 2026-06-28
### Changed
- **DB-2 (slice 1): `db.py` decomposed into a `db/` package.** The 4759-LOC
  `db.py` god-file was split — byte-for-byte behavior-preserving — into
  `db/schema.py` (DDL, migrations, `connect`, `init_db`, `get_stats`, enums) and
  `db/_entities.py` (entity repository queries), with a `db/__init__.py`
  re-export facade. The public `db.*` surface is unchanged (callers use
  `from . import db` → `db.<name>`), guarded by a new `test_db_public_api.py`
  snapshot. Internal-only; no SQL, schema, contract, or behavior change. (Job
  queue and per-entity module carving follow in slice 2.)

---

## [0.27.6] - 2026-06-28
### Fixed
- **XC-1 (slice 2): bug-masking broad-`except` narrowed in `model_setup.py`.**
  Ollama serve/pull/reachability/unload, llama-cpp install, and GGUF download now
  catch the specific expected exceptions (`OSError`/`subprocess.SubprocessError`/
  `httpx.HTTPError`) so unexpected errors propagate instead of being hidden, while
  genuinely best-effort steps (native `llama_cpp` import, embed/rerank smoke
  tests) keep a broad catch with a justifying comment + log.

### Changed
- **XC-4: plugin logs now go through a namespaced, level-gated logger**
  (`src/utils/logger.ts`). `warn`/`error` always print (prefixed `[Incurator]`);
  verbose `debug`/`info` are off by default and enabled per-device via
  `localStorage["incurator-debug"] = "1"` (+ reload). All 42 `console.*` calls
  across the plugin were routed through it, so a user's developer console stays
  quiet unless they opt in. No new plugin setting; nothing synced.

### Notes
- XC-4 plugin timer audit: all 39 `setTimeout`/`setInterval` were reviewed; every
  interval and stored timeout is already cleared on teardown and fire-once UI
  deferrals are benign — no timer changes were needed.

---

## [0.27.5] - 2026-06-28
### Fixed
- **XC-1 (slice 1): bug-masking broad-`except` narrowed across the backend data
  pipeline.** Previously several `except Exception: pass` handlers in
  `config.py`, `parsers/pdf.py`, `llm.py`, `ingest_raw.py`, `ingest_worker.py`,
  and `pipeline/compile.py` swallowed real failures silently. They are now either
  narrowed to the specific expected exceptions (so unexpected errors propagate
  instead of being hidden) or kept broad **with a justifying comment and a log
  line** for genuine best-effort steps. Notably, the Zotero/external source-path
  resolver (`_resolve_reference_source`) now logs and degrades to the original
  source on a transient DB lock / IO error instead of failing silently, and the
  windowed PDF parse logs at warning when a page batch fails. The pipeline's
  intentional fault-tolerance (instant-L1 guards, per-page fallback, provider
  failover, checkpoint-resume) is unchanged — no previously-tolerated degradation
  was turned into a hard abort.

### Maintenance
- Added module-level loggers to `config.py`, `parsers/pdf.py`, `llm.py`,
  `ingest_raw.py`, and `pipeline/compile.py` for the above; removed an orphaned
  import. No public CLI / MCP / plugin contract or schema change.

---

## [0.27.4] - 2026-06-27
### Fixed
- **G17-7: Zotero "Reload Source" no longer rewrites a note from empty
  metadata.** A note that has only a `citekey` and no `zotero_app_url` passed the
  citekey where a Zotero item key was expected; the backend queries `items.key`,
  so the lookup returned empty metadata and the note was re-rendered with blanks.
  Reload now aborts with a clear error and leaves the note unchanged when the
  item cannot be resolved. (Full citekey → item-key resolution requires new
  backend support and is deferred.)

### Maintenance
- **G17-12: the deprecated `imageFolder` profile field is retired from stored
  profiles.** A one-time load-time migration normalizes any profile still
  carrying `imageFolder` to `assetFolder`/`assetSubfolder` and deletes
  `imageFolder`, then persists settings. The runtime fallback in
  `resolveProfileAssetSpec` is retained (the migration reuses it).

---

## [0.27.3] - 2026-06-27
### Fixed
- **G17-1: Settings auth polling stops on close/re-render.** The plugin settings
  tab now owns the login auth-poll timer on the tab instance and clears it when
  the tab hides or re-renders, preventing detached-DOM auth badge updates and
  repeated CLI probes after the settings UI is closed.
- **G17-5: Check DeepSeek API Key now checks key configuration.** The command
  palette action now reports a saved plugin key or `DEEPSEEK_API_KEY` instead of
  calling the login helper and always showing setup help.
- **G17-6: Zotero note reload uses the originating import profile.** Imported
  Zotero notes now store `zotero_profile` in frontmatter, and reload uses that
  profile for the template and annotation asset folder instead of always using
  `zoteroProfiles[0]`. The frontmatter stamp now detects the closing `---` by
  line (so a `---` inside a value or body no longer truncates the note, and
  empty rendered frontmatter no longer produces a duplicate fence), handles both
  LF and CRLF line endings (Windows notes are no longer given a duplicate
  frontmatter block), and new profiles are saved under their trimmed name so the
  stamp round-trips.
- **G17-9: Zotero open-link fallbacks preserve later plugin patches.** The
  global `window.open` / Electron `openExternal` fallbacks now restore their
  originals on unload only if Incurator still owns the patched function.
- **G17-11: Plugin `data.json` writes now use a single serialized settings
  writer.** Scroll-position saves, usage accounting, migrations, explicit
  settings saves, and unload now share `persistSettings()` instead of racing
  direct whole-settings `saveData` calls.

### Documentation
- **G18/G19 docs-surface guards.** `PLUGIN_SCHEMA §2.1` now includes the live
  persisted `PluginSettings` fields (`agentEffort`, `ollamaHost`, and the
  `autoSync*` group), Failure Atlas files have a role index, and USER_GUIDE is
  the canonical reference for `curate.yml` and CLI command definitions. Added
  guard tests for MCP/tool docs, plugin settings docs, Failure Atlas indexing,
  `curate.yml` single-sourcing, and CLI-reference links.

### Maintenance
- Removed dead plugin auth helpers from the settings tab and the unused
  `CLIAuthResolver.normalizeExpiry` helper.
- Removed the stale hardcoded model-default denylist; model migration now resets
  unavailable models by checking the live bundled catalogue, while exempting
  non-empty custom Ollama model ids the bundled catalogue cannot enumerate.
- Consolidated duplicate device-registry writers into one async helper so
  backend-command caching and Syncthing registry refresh no longer repeat inline
  synchronous mkdir/write setup.

---

## [0.27.2] - 2026-06-26
### Fixed
- **Large PDF L2 extraction could still use unsafe 60k prompt batches with CLI
  providers.** L2 and graph extraction now accept `optimal_chunk_chars` whether
  a client exposes it as a property or a method, so CLI providers such as
  Antigravity use their conservative chunk budgets instead of silently falling
  back to 60k-character batches.
- **Provider exceptions left `prompt_runs` rows stuck in `pending`.** Prompt
  traces now close as `failed` with the provider exception recorded when the
  initial call or JSON-repair call raises, making capacity/timeouts diagnosable.
- **L2 continued running later batches after a fatal batch error.** The
  top-level L2 loop now fails fast after the first unrecoverable batch, avoiding
  wasted LLM calls and preserving the detailed batch/span/provider error in the
  source and job state.

---

## [0.27.1] - 2026-06-26
### Fixed
- **Large PDF/Markdown L2 extraction could run for hours and then fail with
  `knowledge unit extraction failed`.** L2 knowledge-unit extraction now retries
  a failed validation batch as smaller source-span-preserving batches before
  failing the source. Validated units are held in memory until every batch and
  retry slice succeeds, then written in one transaction with claim supports, so
  a hard failure no longer leaves orphan or unpublished partial L2 rows behind.
  A fresh retry also discards active generation-less units left by older failed
  runs for that source before prompting while preserving retired audit history.

---

## [0.27.0] - 2026-06-26
### Fixed
- **G08-6: LLM client leak in `curator_build_all` / `curator_sync` MCP tools.**
  Both tools now use `with build_client(...) as client:` so the underlying HTTP
  session / CLI process is always released, even when the build or sync raises.
- **G11-8: `wiki lint` cross-layer suggestion emitted `dataclasses.field` instead
  of the field name.** `check_cross_layer_links` used the loop variable `field`
  (the imported function) in `suggestion` and `context["field"]`; fixed to use
  `fm_field` (the string frontmatter key), so lint output and machine consumers
  receive the actual field name (e.g. `concept_ids`).
- **G11-9: `wiki lint --save` wrote reports as invalid L4 synthesis pages.**
  Reports used `type: synthesis` with missing required L4 fields (`id`,
  `community_report_ids`, `source_span_ids`), causing future lint runs to flag
  their own saved reports.  Reports now use `type: lint_report` with a minimal
  header and are written to `.curator/reports/` instead of
  `.curator/Collections/04_Synthesis/`, so the lint inventory never ingests them.
- **G11-10: `wiki lint --deep` mutated atom files without `--fix`.**
  `check_contradictions_deep` wrote `is_flagged_for_agent: true` to both atom
  files on every detected contradiction, even during a read-only audit pass.
  The write-back is now gated on an `apply_flags=False` parameter (default
  read-only); the flag will only be persisted when called from an explicit
  fix/apply command.
- **G14-5: Model change did not persist the spec-required reasoning-effort reset.**
  `syncReasoningControl()` computed the valid effort for the newly selected model
  but only assigned it to the UI control, leaving the persisted setting stale.
  When the normalized value differs from the stored one it is now written back to
  the provider-specific effort setting and `saveSettings()` is called.
- **G15-6: Dashboard Jobs tab stacked polling intervals on re-entry.**
  `renderJobs()` installed a new `setInterval` every time it was called (e.g.
  cancel then re-run, repeated tab switches) without clearing any prior timer.
  An explicit `clearInterval` guard at the start of `renderJobs()` ensures only
  one 2-second poller is ever active.

---

## [0.26.0] - 2026-06-26
### Added
- **Cross-page PDF equation lookup (P1 — plugin).** The quick-query popover now
  resolves equation, figure, section, and theorem references that point to pages
  the user has not yet scrolled to. When the synchronous resolver finds a target
  page whose text is absent from the in-memory window, `resolveSelectionReferencesBlockAsync`
  fetches that page directly from pdf.js via the new `ExternalPdfView.fetchPage()`
  API, upserts it into the BM25 index, and re-resolves — so the LLM receives the
  actual LaTeX/prose regardless of which page is currently displayed.
  `PdfReferenceSource` gains an optional `searchIndex` field so the full
  document BM25 index (all previously-viewed pages, not just the visible window)
  is used for cross-document search.
- **Per-PDF page cache (P2 — backend).** `fetch_document_section` now accepts
  `content_hash` for source lookup (G08-1) and serves PDF page requests from a
  persistent `.cache/pdf_pages/<hash>/<pagenum>.txt` cache.  Cache hits skip PDF
  parsing entirely; misses trigger a bounded `parse_page_window()` call and write
  the result to disk for future sessions.
### Fixed
- **G08-1: `fetch_document_section` hash dispatch.** `db.get_source_row` now
  accepts a `content_hash` parameter and queries `WHERE content_hash = ?` when
  no `source_id` or `relpath` is provided — enabling the plugin to look up a PDF
  by its SHA-256 content hash instead of its vault path.
- **G12-2: `parse_page_window` bounded parse.** `pymupdf4llm.to_markdown` is now
  called with `pages=[n-1 for n in page_nums]` so only the requested pages are
  decoded, avoiding a full-document load for single-page cross-reference lookups.
## [0.25.8] - 2026-06-26
### Fixed
- **G07-1: `wiki config models use` for Ollama.** The command now writes
  `llm.primary = "ollama::<tag>"` (the canonical format read by all code paths)
  instead of the nested `llm.ollama.model` key that is stripped by
  `_migrate_llm_config` on every load — meaning the selection previously had no
  effect.
- **G07-3: `wiki query` no-op flags now warn.** `--mode`, `--lex`, `--vec`,
  `--limit`, `--min-score`, `--no-rerank`, `--scope`, and `--no-intent-classify`
  are not yet wired to the QueryOrchestrator. Passing any of them now prints a
  yellow warning instead of silently accepting a flag that has no effect on
  retrieval.
- **G07-7: `wiki status` is now read-only by default.** The command no longer
  calls `_mark_existing_l3_done_if_present` or `write_runtime_snapshots` on a
  plain diagnostic invocation. Pass `--refresh` to run those side-effects
  (re-marks stale L3 jobs and refreshes the on-disk runtime snapshot cache).
- **G07-8: `wiki lint` is now read-only by default.** The command no longer
  rebuilds the index, overview, ledger, or appends a log entry unless `--fix`,
  `--save`, or the new `--refresh-manifests` flag is passed.
- **G17-6: `deepseekApiKey` no longer persisted in `data.json`.** The key was
  being saved wholesale with all plugin settings, leaking it to Obsidian Sync and
  any git-tracked vault (PLUGIN_SCHEMA §2.4). All `saveData` call sites now route
  through `_persistableSettings()`, which strips `deepseekApiKey` before
  persisting. On load, the key is restored from the `DEEPSEEK_API_KEY` environment
  variable if present.

## [0.25.7] - 2026-06-26
### Fixed
- **G01-1: `remove_source` cascade.** `wiki source rm` now deletes `job_events`,
  `ingest_jobs`, and `dag_edges` referencing the source before removing the source
  row, preventing `sqlite3.IntegrityError` on compiled sources with FK constraints
  active.
- **G03-1: Sources LWW coalesce.** `db_sync` now uses `COALESCE(last_ingested,
  added_at)` as the LWW timestamp for `sources` — both in the SQL `SELECT`/`WHERE`
  clause and in the Python row-dict comparison — so pending sources (where
  `last_ingested IS NULL`) are included in since-filtered exports and resolve LWW
  conflicts correctly.
- **G04-1: Incremental sync DB-hash fast path.** `_find_changed_nodes` now
  compares full-file SHA-256 hashes against the DB page-hash store (via
  `db.get_page_hashes` / `calculate_hash`) instead of reading a `content_hash`
  frontmatter field that was never written, making the incremental sync fast path
  actually functional.
- **G06-1: Dead code removal in `run_query`.** ~230 lines of unreachable legacy
  search/synthesize pipeline (after an unconditional `return`) and their orphaned
  constants, helper function, and test cases were removed from `query.py`.
- **G06-3: `insert_query_trace` preserves `created_at`.** `_append_context_action`
  now passes the original trace `created_at` through to `db.insert_query_trace`,
  preventing the timestamp from being clobbered to `_now_iso()` on every action
  append.

---

## [0.25.6] - 2026-06-26
### Fixed
- **G14-1: Streaming spinner cleared on context-build failure.** `buildLLMMessages`
  is now inside the try/catch block so any failure during context preparation
  correctly clears `assistantMsg.isStreaming`, preventing the spinner from getting
  stuck forever.
- **G14-2: Manual continuation targets correct bubble.** `renderMessage` now stamps
  `data-msg-id` on each message element; `renderAssistantMessage` uses a CSS
  attribute selector to target the correct bubble by ID rather than always selecting
  the last assistant element in the DOM.

---
## [0.25.6] - 2026-06-26
### Fixed
- **chatSidebar streaming never stuck on context-build failure (G14-1).** `buildLLMMessages`
  was called outside the try/catch that clears `isStreaming`; a context-build failure
  (e.g. vault read error) left the assistant bubble permanently spinning. Moved the
  call inside the try block so all failures — context or streaming — go through the
  same catch that resets `isStreaming = false`.
- **Manual continuation renders into correct assistant bubble (G14-2).** `renderAssistantMessage`
  previously selected `querySelectorAll(".ai-agent-chat-msg-assistant")[last]`, so
  clicking "Continue" on an old truncated answer updated the wrong (newest) bubble.
  Fixed by stamping each message element with `data-msg-id` in `renderMessage` and
  looking up by ID first, with last-element fallback for backward compatibility.

---
## [0.25.5] - 2026-06-26
### Security
- **OS sandbox write scope narrowed to active provider only** (`sandboxWrapper.ts`):
  The v0.23.0 sandbox allowed write access to ALL four provider state directories
  (`~/.gemini`, `~/.antigravity`, `~/.claude`, `~/.codex`) regardless of which
  CLI was actually running. Antigravity now only gets `~/.gemini` + `~/.antigravity`,
  Claude CLI gets `~/.claude`, and Codex gets `~/.codex`. A cross-provider agent
  could no longer overwrite another CLI's auth state. When `provider` is not
  specified, the safe fallback grants all four dirs for backward compatibility.
  5 regression tests added.
## [0.25.4] - 2026-06-26
### Fixed
- **`curate.yml` boolean strings no longer invert policy** (`curate_yml.py`):
  Python's `bool("false") == True` caused any quoted boolean in `curate.yml`
  (e.g. `allow_general_knowledge: "false"`) to be read as the opposite of the
  user's intent. A new `_bool_from` helper accepts both Python booleans and
  YAML-style string literals (`"true"/"yes"/"on"`, `"false"/"no"/"off"`).
  Affects: `allow_general_knowledge`, `require_source_spans`,
  `exploration_enabled`, `require_insight_candidates`, `allow_external`,
  `require_rebind_approval`, `backprop.enabled`.
- **Scalar `include` pattern no longer silently drops the filter** (`curate_yml.py`):
  Writing `include: "03_Notes/**"` (a bare string) returned an empty list,
  which the source-matching logic interprets as "include all". Now wrapped in a
  one-item list so the filter is honoured.

## [0.25.3] - 2026-06-26
### Fixed
- **`resolveCredential` exhaustiveness** (`cliAuth.ts`): Added a `default` case
  to the provider switch that throws an explicit error with a `never`-typed guard.
  Without it, an unrecognised provider silently returned `undefined` as the
  credential, causing opaque call-site crashes.
- **`updateSettings` drops its argument** (`main.ts`): `Object.assign` now merges
  `updates` into `this.settings` before the data is saved. Previously every caller
  was saving the unchanged current settings, so settings-panel mutations were
  discarded on navigation.
- **`claude-sonnet-4-6` wrongly in unavailable-model blocklist** (`main.ts`):
  Removed from `unavailableDefaults`; it is a live, valid model ID. Its presence
  caused the plugin to force-reset users whose active model was
  `claude-sonnet-4-6` to the provider's default (Gemini) on every load.

## [0.25.2] - 2026-06-26
### Fixed
- **Stale config path references removed from docs.** All references to the
  retired `~/.config/curator/config.yml` global path and the renamed
  `.curator/config.yml` vault file have been corrected to reflect the actual
  paths used since v0.25.0: vault-scoped settings are in `.curator/settings.yml`
  and machine-local settings are in `.cache/config/config.yml` at the repo root.
- **False auto-processing callout removed from USER_GUIDE.** The `[!IMPORTANT]`
  callout that incorrectly claimed `wiki query` / `search_curator` auto-ingest
  pending sources has been replaced with an accurate note describing the manual
  pipeline (`wiki add` → `wiki build` → `wiki sync` → `wiki query`).
- **CLAUDE.md spec paths made explicit.** The `SEARCH_ENGINE_SCHEMA.md` glob in
  the version-bump instructions now lists its actual subdirectory
  (`docs/specs/search_engine/`) instead of relying on an ambiguous wildcard that
  agents misread as `docs/specs/system_behavior/`.

## [0.25.1] - 2026-06-25
### Fixed
- **Safer source/job recovery.** `wiki source rm` now keeps source files unless
  `--delete-file` is explicit, `wiki source retry` sees layer-scoped failures,
  and `wiki jobs rerun` is idempotent for already queued jobs.
- **Portable PDF/VLM ingest and L2 generation.** VLM markdown strips transient
  `.cache/vision_render` temp links before persistence; generated L2 Atom/KNU
  fields now pass an English-output guard with retry/failure behavior; generated
  CTX projections no longer expose parser-made same-document heading wikilinks.
- **Plugin source/PDF/quick-query stability.** Registered source chips stay
  inert while queued/running, generated vault block links are clickable, quick
  query preserves LaTeX copy data and now supports multiple independent popovers,
  bare PDF equation references like `(19.11)` resolve through local PDF context,
  and Convert-to-LaTeX uses an output-only dedicated transcription path.
- **L4 and PDF viewer clarity.** Completed builds now mark L4 `done`, `skipped`,
  or `error` instead of leaving eligible sources indefinitely `pending`; the
  dashboard renders `Skipped`, and PDF scroll work is coalesced per animation
  frame to reduce long-document jank.

---

## [0.25.0] - 2026-06-23
### Changed
- **Backend ↔ plugin config isolation + rename.** The vault-scoped config file is
  renamed `.curator/config.yml` → `.curator/settings.yml` so it no longer collides
  by name with the per-device backend config `<repo>/.cache/config/config.yml`.
  Rule: per-device backend settings (`llm`, `search`, `external`) and
  `devices.json` live only in the repo's `.cache/config/` (never synced); only
  device-portable, syncable settings live in the vault's `.curator/settings.yml`.
  No backward-compat: existing vaults must re-init or rename their config file.
### Added
- **`wiki status --json`.** Prints the live consolidated `{status, sources, jobs}`
  payload to stdout. The Obsidian dashboard now reads this live output directly
  (one CLI call per render, cached across panels) instead of the on-disk
  `.curator/runtime/*.json` snapshot — so it can never show stale data when a
  backend change forgets to regenerate the snapshot. The snapshot file remains a
  best-effort cache for the lightweight chat status bar only.
### Fixed
- **Dashboard ↔ `wiki status` desync ("Apply reverts after visiting Jobs").**
  `wiki config set --global` wrote `settings.yml` while the loader read
  `config.yml`, so global LLM changes (fallback / PDF-vision / LaTeX-region
  models, set via `config set`) silently reverted while the primary (set via
  `config provider`) stuck. Both `config get/set --global` now use the backend
  global `config.yml`.
- **Dashboard LLM Apply did nothing on fresh vaults.** Apply was gated on a
  successful `.curator/settings.yml` read, but LLM is a machine-local key that
  never lives there — the gate is removed (model-selected is the only precondition).
- **Dashboard changes appeared to revert.** The LLM Apply and Persona Save
  handlers did not refresh the backend snapshot after writing, so re-rendering
  showed the stale pre-save values; both now regenerate + re-read like every other
  mutation handler.
- **Dashboard model-load timer leak.** Closing the dashboard before the model
  catalogue loaded left a 400 ms `setInterval` polling a detached DOM; it is now
  tracked and cleared in `onClose()`.
### Changed
- **Edit-review loop demoted from hard gate to a hint.** A valid `ai-agent-edit`
  proposal now always opens a reviewable diff, even when the model skips the
  `[[PHASE:…]]` review markers. The old gate suppressed the diff entirely on
  token-limited / low-instruction-following models, producing "I made an edit"
  with no diff. Non-conforming answers now show the edit pills plus a soft,
  non-blocking note with an optional **Re-run with review** button; the blocked
  banner and the "Override & review anyway" escape hatch are removed.
### Added
- **Output-token truncation recovery.** Cut-off answers (Gemini `MAX_TOKENS`,
  OpenAI/Ollama `length`, Claude `max_tokens`) are detected via a normalized
  `StreamChunk.finishReason`/`truncated` mapped in every provider adapter, and
  auto-continued up to 3 times. Continuations resume mid-edit-block, are stitched
  with overlap de-dup (no duplicated text, no mangled `ai-agent-edit` fence), and
  the message stays streaming until truncation fully resolves — so edit pills /
  auto-open never fire on an in-flight partial. A manual **↪ Continue** button
  appears if it's still cut off after the cap.
### Fixed
- **Diff Viewer keyboard hijack.** Accept/Reject/navigate shortcuts now fire only
  when the diff editor or its toolbar is focused — pressing Enter in the chat box
  no longer silently applies an open diff. Opening a diff focuses it so the keys
  work immediately.
- **Multi-edit "could not be matched" / "already opening" errors.** Proposals are
  matched against the original file (order-independent), so accepting one edit can
  no longer break another's SEARCH; skipped edits are reported as not-found vs
  overlapping. A same-file re-entrant Review request now coalesces silently
  instead of raising "a diff review is already opening".
- **No more silent open failures.** `DiffViewer.show` returns a typed result and
  callers surface the exact reason (nothing changed / editor not ready).

---

## [0.23.0] - 2026-06-22
### Security
- **CLI provider tool-scope sandbox.** The Quick Query popover and chat sidebar use
  CLI agents (Antigravity `agy`, Claude, Codex) that have their own built-in tools —
  which the v0.19.0 MCP isolation did not govern, so the agent could run scripts,
  create files, and search the whole filesystem (e.g. a hallucinated
  `find_mvg_text.py`). Now `toolPolicy` reaches the CLI command builder:
  - **Popover runs the CLI tool-free** (claude `--tools ""`; codex `--sandbox
    read-only`); the **sidechat scopes tools to the allowed roots** (vault +
    configured Zotero folder + Zotero library) — claude `--disallowedTools`
    (keeping only the DB-scoped Incurator MCP tools), codex `workspace-write` +
    `--add-dir`. The dangerous `agy --dangerously-skip-permissions` /
    trust-workspace bypass is removed.
  - Antigravity's own `--sandbox` is ineffective (it still created files in testing),
    so every CLI subprocess is wrapped in an **OS sandbox** generated from the allowed
    roots — macOS `sandbox-exec` (Seatbelt, deny writes outside the roots; validated
    to contain nested child processes) and Linux `bubblewrap` (`bwrap`). On Linux,
    install `bubblewrap` (`sudo apt install bubblewrap`); without it the agentic CLI
    is blocked with a reminder. Windows CLI sandboxing is not yet supported. Setup is
    automatic — no manual profile configuration. Reads remain allowed (the contained
    harm is file creation / script execution); external user-configured `mcpServers`
    remain the user's own trust boundary.

---

## [0.22.0] - 2026-06-21
### Added
- **Dedicated PDF-extraction vision models (`vision_model` / `latex_extract_model`).**
  PDF text-layer extraction (pymupdf4llm) cannot reliably reconstruct LaTeX for math.
  You can now elect a **vision model**, configured in the **Dashboard → LLM Provider**
  card and decoupled from the main chat model, to read rendered pages. When
  `llm.vision_model` is set, every `add source` PDF page is rendered (PyMuPDF
  `get_pixmap`, bounded DPI + longest-edge cap) and transcribed to Markdown + LaTeX,
  becoming L1 with `parser_used="vlm"`. The pymupdf4llm text is retained per page as
  `parser_text`; a transient per-page VLM failure falls back to it (never aborts).
  A `vision_max_pages_per_run` rail bounds a single run. Cloud vision runs on your
  existing **CLI subscription** (Ollama in-memory, or the `claude`/`agy`/`codex` CLIs
  reading a temp PNG under `.cache/vision_render/` that is always cleaned up) — **no
  provider API keys**. Per-page transcriptions are cached by
  `(rendered-image hash, model)` so a Dashboard model switch invalidates stale L1.
  A second light slot, `llm.latex_extract_model` (empty → falls back to
  `vision_model`), powers interactive region OCR for right-click **Convert to
  LaTeX** and **Cmd+Shift+X** crop transcription. (SYSTEM_BEHAVIOR §26.2a.)

### Fixed
- **Interactive PDF snippets now use the selected PDF extraction model.**
  Right-click **Convert to LaTeX** and **Cmd+Shift+X** route through the backend
  `plugin pdf transcribe` resolver instead of the plugin main chat model. When a
  crop is successfully transcribed, the chat context carries the transcription
  text without forwarding the crop image to the main chat model's vision path.
- **Chat context decay on `Cmd+Shift+L` localized questions.** In long, edit-heavy
  sessions, a freshly referenced line range asked about as a *question* could be
  ignored while the agent proposed a whole-file edit. The root cause was a payload
  self-contradiction: a `Cmd+Shift+L` line range is both a primary-focus selection
  (recency anchor: "answer only, do not modify the document") and an editable range
  (`<editable_selection>` + the `<edit_review_loop>` contract: "you may edit these
  lines"). The plugin now suppresses both edit affordances when the latest turn is a
  localized question (a primary-focus selection present and the turn is not an edit
  request), so the recency anchor is unopposed. The decision is unconditional with
  respect to prior turns — a fresh question after an earlier whole-document edit is
  still honored. Genuine edit requests keep the full edit/diff flow.

### Changed
- **Zotero import profiles are ordered most-recently-used first.** The import
  wizard now auto-loads the most-recently-used profile (not merely the first saved)
  and orders the Import Profile dropdown recent-first via a new optional
  `lastUsedAt` timestamp, stamped when a profile is used for an import or created.
  Profiles never used keep their insertion order; the persisted profile order is
  not mutated by rendering.

---

## [0.20.0] - 2026-06-20
### Fixed
- **`context_expand` token-budget inflation.** Expansion now budgets against the
  *cumulative* pack — the tokens already consumed by the pack's selected items seed
  the budget, so a newly expanded item is admitted only if it fits within
  `limit_tokens` alongside everything already selected. Previously each expansion
  was granted a fresh full budget, so a near-full pack plus an expansion could
  overflow the model context window. Items that no longer fit return as
  `expansion_refused` (increase `limit_tokens` or refetch).
- **Retrieval provenance erased on answer-synthesis failure.** A failed
  `query_local_answer`/`query_global_reduce` validation no longer clears the
  result/trace `source_span_ids` (and sibling provenance arrays); the retrieved
  evidence is preserved exactly as the `explore` route already preserves it, so a
  synthesis failure is no longer misclassified as a recall=0 retrieval failure. The
  answer-cited spans on the `synthesis_status=failed` action remain empty.
- **Token estimate charged literal `"None"`.** A payload whose `detail` is JSON
  `null` is now costed as an empty string (1 token) instead of the 4-char `"None"`.
- Dropped a redundant `curate.yml` re-parse in `QueryOrchestrator.run` — the policy
  hash is now reused from the snapshot `context_fetch` already resolved.

### Changed
- **Explore route unified through `ContextService` (SYSTEM_BEHAVIOR §31.8).** The
  `explore` route no longer runs a divergent associative retrieval pipeline. It now
  grounds on the same `context_fetch` pack path as every other route — producing a
  `PACK-*`/`SNAP-*` snapshot, obeying the shared token budget, and recording ordered
  `CTXA-*` actions under a single `QTR-*` root. The explore-specific behavior
  (follow-up questions + provisional insight candidates) became a synthesis-phase
  consumer of that normalized pack rather than a second retrieval path.
  `explore` is admitted to `_ADMITTED_ROUTES` (not a safe baseline — it can still be
  rolled back to `local` via `INCURATOR_DISABLED_ROUTES`). `curator_fetch_context`
  now returns explore-route grounding for discovery-signal questions instead of
  silently degrading them to `local`.
- Removed the orphaned legacy explore branch in `QueryOrchestrator.run` and its
  dead helpers (`_evidence_json`, `_build_retrieval_trace`, `_question_hash`).

### Notes
- This release closes the RAG-hardening milestone's one genuinely-unimplemented
  systemic gap (explore unification). A grounding audit of the remaining
  `batch_1_to_3_audit` findings confirmed they were already shipped by the Plan A–G
  stabilization (orphaned-support truth state, CJK-safe token estimation, rank-order
  preservation, expansion state machine + budget-exhausted signal, graph
  giant-component `bridge_risk` quarantine + entity-alias resolution, degraded-mode
  eval fixtures) and are pinned by regression tests.
- Verified end-to-end on two testbed scenarios (`complex_math_backprop`,
  `testbed_template`) against a live LLM backend: `add` → `build` → `sync` →
  query (`local`/`global`/`explore`) → Mode B backprop.

## [0.19.0] - 2026-06-20
### Added
- **Shared prompt registry** (`plugin/src/context/promptRegistry.ts`). The chat
  sidebar and the Quick Query popover now assemble their security-critical prompt
  rules from one set of composable blocks (`boundaryConstraints`,
  `buildRecencyAnchor`, `SurfaceProfile`/`SIDECHAT_PROFILE`/`POPOVER_PROFILE`), so
  filesystem/tool boundaries can no longer drift between the two surfaces. The
  popover's "no filesystem access" rule is now sourced from the registry instead
  of a hardcoded duplicate.
- **Recency anchor against long-session context decay.** A `<critical_invariants>`
  block is appended LAST in each request (the strongest-attention position),
  re-asserting "answer only about the current `<primary_focus_selection>`; do not
  edit the whole document unless explicitly asked" — deferring to the existing
  pointer / `<resolved_cross_references>` rule. Fixes the case where a localized
  `Cmd+Shift+L` selection added late in a long chat was ignored and the agent
  reverted to whole-file modification.
### Fixed
- **Quick Query popover is now hard-isolated from MCP tools.** `LLMClient.streamChat`
  gained an optional `{ toolPolicy: "auto" | "none" }`; the popover passes
  `"none"` so `mcpManager.getAllTools()` is never invoked on its path. The popover
  can no longer run scripts (e.g. a hallucinated `find_mvg_text.py`), create
  files, or traverse the filesystem — it answers only from the selected passage
  and current page. The single `shouldInjectMcpTools` helper funnels the
  toolPolicy-none, CLI-provider, and no-MCP-manager cases into one no-tools path
  so they cannot diverge. The chat sidebar's tool behavior is unchanged
  (default `"auto"`).

## [0.18.0] - 2026-06-20
### Added
- Synthesized chat/query answers now cite the **original source documents**
  outside `.curator/` (e.g. `[[04_Resources/Paper]]`), not only the hidden DAG
  node. Each retrieved hit's spans are resolved to their real, visible source
  files via the new forward provenance trace `db.sources_for_spans` (span →
  `source_spans.source_id` → `sources.relpath`), and the synthesis prompt
  instructs the model to cite them. Only the `.md` suffix is stripped, so `.pdf`
  and other source links still resolve.
- `02_Wiki/` promotions (`promote_answer` / `wiki query` "save to wiki" / the MCP
  `promote_answer` tool / CLI `plugin promote`) accept the answer's
  `source_span_ids` and append a deterministic `## Sources` section linking every
  distinct source document behind the answer. Because the promoted note is a
  visible vault file, those sources appear in Obsidian's native Graph view and
  Backlinks pane — the hidden DAG cannot contribute such edges (the c3 hybrid).
  Multi-source syntheses list all contributing papers, not just the first.
- A **💾 Save to 02_Wiki** button in the chat **Sources & Trace** panel promotes the
  current answer to a durable `02_Wiki/` page, passing the trace's
  `source_span_ids` so the page's `## Sources` section (and thus native Graph /
  Backlinks) is populated. Promotion stays an explicit, human-approved action.
### Fixed
- Verified a gap left by RAG stabilization: the search materializer aggregates
  source provenance up to abstraction records (entities, relations, community
  reports, synthesis nodes) via `source_span_ids`, but this was never asserted and
  `_first_source_id` kept only a single source. `db.sources_for_spans` now returns
  every distinct origin in span order, pinned by `test_abstraction_source_trace`
  (including a multi-source synthesis node tracing back to both papers).
- `db.sources_for_spans` now resolves all distinct source relpaths with one
  batched `IN` query instead of one query per source.
- Promoting a historical chat answer now uses that answer's own trace and the
  immediately preceding user question. Older trace panels keep source navigation
  and Save to 02_Wiki available, but hide mutating context-pack actions so they
  cannot affect the active query state.

## [0.17.0] - 2026-06-20
### Fixed
- Curator DAG wikilinks are now clickable. The L1–L4 knowledge DAG lives under
  the hidden `.curator/Collections/` folder, which Obsidian's metadataCache never
  indexes — so curator-layer links such as `[[02_Atoms/ATM-9f8e7d6c]]` previously
  rendered as dead, unresolved links (no click, hover, graph, or backlinks) in the
  chat sidebar, the quick-query popover, and opened DAG pages. The plugin now
  registers a single markdown post-processor that rewrites these rendered links
  into clickable links which open the hidden page via `openLinkText`. The rewrite
  accepts an optional `.curator/Collections/` prefix, an optional `.md` suffix, and
  a `#heading`/`#^block` subpath; marks a missing target with an `is-missing`
  style instead of opening a nonexistent page; and leaves non-curator internal
  links, external links, real-vault embeds, and `[[PHASE:…]]` markers untouched.
### Notes
- Because the DAG stays hidden, curator nodes still do not appear in Obsidian's
  native Graph view or core Backlinks pane; use the chat Sources & Trace panel for
  backlink-style provenance. The backend `[[LAYER/ID]]` link format is unchanged.

## [0.16.1] - 2026-06-20
### Fixed
- Narrowed wikilink target normalization so it strips only the retired curator
  URI schemes (`legacy://` and the pre-v0.3.2 search-binary scheme) instead of
  any `scheme://` prefix. Standard external links (`http://`, `https://`,
  `obsidian://`, `zotero://`) in source paths are now preserved instead of
  having their scheme and authority mangled.

## [0.16.0] - 2026-06-20
### Changed
- Removed legacy external-search-binary runtime/build/status surfaces. The
  backend and MCP status payloads now expose the DB-native `search_*` contract
  only.
- Updated plugin dashboard/status handling to read `search_ready`,
  `search_version`, and related DB-native search fields without legacy fallback
  keys.
- Removed the obsolete benchmark harness and archived parity writeups that still
  invoked the retired external search path.

### Fixed
- Added a guard test that prevents active source, tests, plugin, scripts, specs,
  guides, and agent rules from reintroducing retired search-binary references.

## [0.15.0] - 2026-06-19
### Changed
- **Quick Query popover is now persistent.** Outside clicks and background
  scrolling no longer close or drag the popover away from the user's chosen
  context; close it explicitly with **×** or `Esc`.
- **Quick Query popover can be moved and minimized.** Drag the header to place it
  anywhere in the current window, and collapse it to a header-only state without
  losing the answer, input, or follow-up state.
- **Quick Query title follows the latest question.** The header updates on each
  submit so minimized popovers remain identifiable.

### Fixed
- Fixed old quick-query teardown order so popout-window scroll/resize listeners
  are removed before switching the active document.
- Fixed text-node outside-click handling in the quick-query document listener.

## [0.14.1] - 2026-06-19
### Fixed
- **Diff Viewer — Accept All cursor.** Accepting all changes now leaves the
  cursor at the first changed line instead of teleporting to the bottom of the
  document.
- **Diff Viewer — toolbar anchoring.** When a diff opens off-screen, the editor
  scrolls the first change into view before measuring, so the Accept/Reject
  toolbar anchors next to the change instead of jumping to the top of the screen.
- **Diff Viewer — multi-file review race.** Opening a diff is serialized behind a
  single in-flight guard, so clicking a second proposal pill can no longer
  re-point the singleton Diff Viewer to the wrong file mid-open.
- **Edit-proposal pills show honest, live status.** Each review pill is derived
  from the current file via the shared matcher: **✓ Applied** when the edit
  already appears, or when an empty-replacement deletion has already removed the
  SEARCH text; **⚠ Not found** when neither side matches. Applied/not-found pills
  no longer re-run doomed matches on click, so no "could not find" appears after
  a status pill already reported the state. Self-healing across re-render and
  session reload (no schema change).
- **Path resolution fallback.** `resolveVaultFile` adds a case-insensitive,
  whitespace-trimmed full-path scan, fixing spurious "file not found" on existing
  notes whose path differs only by case without retargeting same-named notes in
  other folders.
- **Agent no longer claims edits are applied.** The edit-loop post-edit phase now
  states edits are *proposed and pending your Accept in the Diff Viewer*; nothing
  is written to disk until you accept.

### Notes
- Triaged against the v0.11.0 Diff Viewer overhaul: navigation scroll and
  premature-disk-write were confirmed already fixed and are now pinned by
  regression tests. Unified-view polish and cross-model output determinism remain
  deferred to the Agent UI/UX & Context Architecture milestone.

## [0.14.0] - 2026-06-19
### Added
- **Enforced & observable sidechat edit-loop state machine.** Edit proposals
  now must walk a visible four-phase loop — **Analysed → Reviewed → Updated →
  Reviewed** — before any change can be accepted. A new composable
  `getEditLoopContract()` system-prompt block (anchored last, at strongest LLM
  attention) instructs the agent to emit canonical `[[PHASE:...]]` markers, and
  is appended for any edit-likely turn: a Markdown edit request, an editable
  selection, an open Markdown edit target, or a multi-turn continuation of an
  edit loop a previous answer already opened.
- **Runtime hard gate (`context/editLoopContract.ts`).** A pure validator parses
  the response; an edit-bearing answer that skips or mis-orders the loop no
  longer auto-opens the Diff Viewer. Instead the chat shows a **"Agent skipped
  the review loop"** banner with **Re-run with loop** (re-prompt) and **Override
  & review anyway** (open the diff regardless) actions. Pure Q&A with no edits is
  never gated.
- **Observable phase UI.** Conforming answers render each phase as a labeled,
  collapsible section (`.ai-agent-edit-phase[data-phase]`), with the inline diff
  review pill anchored inside the **Updated** phase. Phase markers never leak as
  raw text in any render path.

## [0.13.0] - 2026-06-19
### Added
- **Unified Agent ContextService feedback (Plan F P7).** New append-only
  `context_feedback` operation records `FBK-*` events against the exact served
  pack/snapshot with the nine locked feedback types (relevant, irrelevant,
  incorrect, stale, insufficient, duplicate, new_insight, correction,
  promotion_request). Feedback is hard-quarantined: it never edits source files,
  generated records, ranking, or truth state. A `new_insight` event enqueues a
  provisional `pending` insight candidate for human review. Exposed through
  `plugin_api.feedback_context` and the hidden `wiki plugin context feedback`
  command.
- **Sources & Trace feedback UI (Plan F P7).** Each evidence item shows
  relevant/irrelevant controls and a "Report..." menu
  (incorrect/stale/insufficient/duplicate) that records feedback through the
  backend without mutating the pack.
- **ContextService route admission and rollback (Plan F P8).** The service serves
  only Plan-A pack-integrated routes (`local`, `source-section`, `global`).
  `explore` and unknown routes degrade to `local` before retrieval runs; the
  experimental `global` route is independently disableable via
  `INCURATOR_DISABLED_ROUTES` for rollback. The decision is recorded as
  `route_admission` on the response and root trace.

### Changed
- **Sources & Trace locator resolution extracted (Plan F P6).** The pure
  open-target decision moved to `incuratorQueryTraceLocator.ts` with behavioral
  unit tests; the vault PDF locator label no longer repeats the `#page=N` anchor.

## [0.12.0] - 2026-06-19
### Added
- **Unified PDF asset identity resolution (Plan G).** Backend Reference Mode,
  Zotero-backed PDFs, add-source registration, and PDF viewer context now route
  through shared AssetIdentity/AssetSource contracts instead of ad hoc path
  conversion.
- **Device-safe PDF session sync.** Synced chat sessions no longer persist
  macOS/Linux absolute PDF paths or volatile backend path status as durable
  identity; portable identifiers are kept so each device re-resolves local paths.

### Changed
- **External PDF viewer slimmed.** Persistence/registry behavior and capture/RAG
  composition were extracted from `externalPdfView.ts`, with the PDF module LOC
  total reduced below the Plan G baseline.
- **Zotero PDF handling hardened.** Status keys, durable attachment identity,
  cache epoch invalidation, and stale localStorage path replacement now use the
  same resolver model.

### Fixed
- **Reference PDFs open the real file, not the stub.** Locator consumers now
  honor `external_uri` for Reference Mode PDFs while keeping vault stubs as
  portable metadata. Non-PDF local external references now use the desktop system
  opener instead of relying on Chromium `window.open`.
- **Add-source badge state regressions.** Zotero identity no longer depends on
  currently open PDF tabs, and added/building states are covered by contract
  tests.
- **PR review hardening.** Fresh Zotero/current-device path resolution now
  overrides stale DB/layout path hints, Reference Mode stubs no longer mark
  unresolved assets as resolved, Sources & Trace verification updates the
  displayed item, and synthesis output cannot overwrite `source_span_ids` with
  `None`.

---

## [0.11.0] - 2026-06-16
### Fixed
- **Complete overhaul of Diff Viewer UI (resolving 34 known bugs)**:
  - Implemented Inverted Decoration Model (projects diffs virtually without pre-mutating the buffer).
  - Prevented OOM crashes by setting hard limits on the LCS diffing algorithm.
  - Stabilized UI layout (floating toolbar now maintains correct viewport coordinates during scroll).
  - Enforced strict state synchronization (buffer is only modified upon explicit 'Accept').
  - Prevented DOM and event memory leaks via strict singleton enforcement and layout-change listener cleanup.
  - Added robust support for multi-file edit proposals and target-isolated routing.

## [0.10.0] — 2026-06-15

RAG Retrieval Provenance release (Plan A, Program 3). Builds the trusted
retrieval and evidence-selection substrate consumed by the forthcoming Plan F
ContextService. Every retrieval call now carries one authoritative RTR-*
execution ID, bounded and query-relevant evidence, explicit omission counts,
CurationPolicy enforcement, and resolvable structured source locators.
Specs: SCHEMA.md §22, SYSTEM_BEHAVIOR.md §28–§30, SEARCH_ENGINE_SCHEMA.md §12.

### Added

- **Authoritative RTR-\* retrieval execution ID (§30.1).** Each `build_evidence`
  call generates a unique `RTR-<8hex>` ID stamped on the `EvidencePack`, stored
  inside `query_traces.retrieval_trace_json` with `contract_version: "1"` for
  Plan F consumption (§22.4).
- **CurationPolicy forwarded through evidence assembly (§28.1 / F3).** The
  orchestrator now passes the resolved `CurationPolicy` to `build_evidence` on
  both the `fetch_context` and `run` paths, enabling workspace-scoped retrieval
  filtering.
- **Bounded, query-relevant global route (§28.2 / F4).** Community reports are
  scored by query-term overlap and capped at 10 (`_MAX_GLOBAL_REPORTS`);
  synthesis nodes capped at 6. Omitted report counts are recorded in
  `pack.omitted_counts["global_reports"]`.
- **Explicit evidence-block omission marker (§28.3 / F5).** `evidence_block()`
  appends `[N items omitted — character budget reached]` when the character
  budget causes items to be dropped. Previously items were silently truncated.
- **StructuredLocator dataclass (§29.2).** A transport-neutral, in-memory
  locator providing `source_id`, `source_kind` (vault_markdown/vault_pdf/
  external_uri/promoted_wiki), `relpath`, `heading`, `block_id`, `page_number`,
  `toc_id`, `external_uri`, and `locator_status` (exact/fallback_file/
  fallback_source/duplicate_anchor/stale/unavailable).
- **Locator resolution on source-span evidence items (§29.4).** `_span_items()`
  batch-fetches source metadata and resolves a `StructuredLocator` for every
  span-backed `EvidenceItem`. The `source-section` route is refactored to use
  the same path, gaining locators for free.
- **Plan-F handoff contract in `fetch_context` (§30.2).** The response now
  includes `retrieval_execution_id` at the top level, and each evidence item
  carries a serialized `locator` dict for Plan F to consume without re-querying.
- **`EvidencePack` extended fields (§22.3).** Added `retrieval_execution_id`
  (str) and `omitted_counts` (dict) to `EvidencePack`. Added `locator`
  (StructuredLocator | None) to `EvidenceItem`.

### Fixed

- **F3 — CurationPolicy not enforced (§28.1).** `build_evidence` now applies the
  workspace source-scope globs (`source_include`/`source_exclude`) via
  `CurationPolicy.allows_source` with a **strict all-spans rule**: an item is kept
  only when *every* backing span is in scope. Multi-source artifacts (community
  reports, synthesis, entities) are excluded entirely if any backing span is out
  of scope — their text commingles all sources, so partial inclusion would leak
  excluded content and trimming `source_span_ids` would corrupt provenance;
  `source_span_ids` is never mutated. Items dropped by scope are counted in
  `omitted_counts["policy_excluded"]`. (PR #31 review: the policy kwarg had been
  plumbed but the filter was missing; a follow-up review then tightened the
  initial "any-in-scope" rule to strict exclusion to close a private-data leak.
  The F3 oracle is behavioral — it seeds a mixed public+private report and asserts
  it is excluded whole.)
- **F4 — Global evidence query-independent and unbounded (§28.2).** All
  community reports were loaded regardless of query relevance or count.
- **F5 — Evidence block silent truncation (§28.3).** Character-budget cutoffs
  dropped items without any indicator; now always emits an explicit marker, and
  the marker (plus `\n\n` separators) never pushes the block past `max_chars` —
  it replaces the last partial item to fit. (PR #31 review fix.)
- **Locator `promoted_wiki` kind (§29.2).** Sources under `02_Wiki/` now classify
  as `promoted_wiki` instead of `vault_markdown`. (PR #31 review fix.)
- **Retrieval-trace `candidate_count` (§30.2).** `candidate_count` now reports
  `selected_count + omitted total` instead of being hardwired equal to
  `selected_count`. (PR #31 review fix.)

---

## [0.9.0] — 2026-06-15

Graph Quality release (Plan C). The trusted v0.8.0 claim layer compiles into a
reversible, support-aware knowledge graph and deterministic, claim-grounded
community reports — with a read-only graph audit that gates the serving path.
Specs: SCHEMA.md §21, SYSTEM_BEHAVIOR.md §27.

### Added

- **Entity resolution and reversible merges (§27.1).** Similar names are only
  ever *candidates*: synonyms, abbreviations, and translations merge only after
  type/context/contradiction/`avoid_merges` guards pass; ambiguous homonyms stay
  unmerged until an explicit decision. Every accepted merge keeps the origin
  identity (`redirected`) and a complete `entity_resolution_lineage` rewrite
  record, so it reverses to byte-identical pre-merge endpoints. A homonym
  surrogate-key alias model (`ALI-` ids) lets one surface form resolve to many
  distinct entities without collision.
- **Independent claim-level relation support (§27.2).** A relation is a
  proposition; re-asserting it *aggregates* `graph_relation_supports` instead of
  overwriting. Independence is counted by source lineage, so copied/forked
  sources count once. A relation becomes `active` only with **≥2 independent
  source lineages** of verified support — so a single source per topic builds no
  community reports until a second independent source corroborates the same
  relations.
- **Relation lifecycle and quarantine (§27.3).** Every relation carries
  `lifecycle_status ∈ {active, provisional, quarantined, retired}`. Weak edges
  are quarantined with a frozen reason (`unsupported`, `self_loop`,
  `contradiction`, `copied_source_only`, `bridge_risk`, `endpoint_unresolved`)
  and a re-evaluation trigger — never silently dropped or admitted. Purely
  topological cut-edge (bridge) detection gates on structure, not on the
  non-discriminative production confidence (GQ07). Authored vs extracted edge
  classes stay distinct.
- **Deterministic community construction (§27.4).** Filtered connected components
  over `active` relations between canonical entities is the explicit degraded
  fallback; the same `(graph, config, seed)` yields an identical partition, pinned
  by `config_hash`. Seeded weighted Leiden stays a benchmark-gated candidate
  (blocked on labeled relation-quality data; modularity alone is insufficient).
- **Claim-grounded community reports + reconciliation (§27.5/§27.8).**
  `rebuild_graph_generation` compiles the authoritative graph into reports whose
  identity is content/config-derived (`community_key = f(level, member_hash,
  support_hash, config_hash)`); a changed membership/support restructures and
  retires the superseded community before synthesis consumes it. Reports cite
  exact eligible active claim support — the broad whole-community-span fallback is
  removed. An unchanged rebuild is idempotent (no count amplification); a one-source
  edit/delete reconciles only its measured downstream closure.
- **Graph audit + `wiki lint` Graph Quality section (§27.6).** A read-only
  `graph_audit` asserts the §21.8 invariants (no active relation below the
  ≥2-lineage floor, no endpoint that is not a canonical entity, no reference to a
  redirected entity, every quarantined relation carries a reason + re-eval
  trigger, every served report finding cites active support). `wiki lint` gains a
  Graph Quality section that exits non-zero on release-blocking findings.
- **Live claim-grounded cutover.** The L2 compile writes one
  `graph_relation_supports` row per asserting claim, keyed by the source's lineage;
  `wiki build`/`wiki update`'s L3 (`compile_global_l3`) now grounds community
  reports on `rebuild_graph_generation`'s corroborated `active` relations, replacing
  the prior broad-span community path on the serving path.

### Changed

- **Schema v9 (additive, forward-only).** New `entity_aliases`,
  `entity_merge_proposals`, `entity_resolution_lineage`, `graph_relation_supports`
  tables + resolution/lifecycle/identity columns on `graph_entities` /
  `graph_relations` / `community_reports`. The migration infers nothing (legacy
  entities `canonical`, legacy relations `provisional`, zero alias/support rows).
- **MCP/plugin contracts unchanged.** Plan C is CLI-side; agents/plugin clients
  observe it only as better evidence on already-returned records (canonical
  entities, active relations, claim-grounded reports).

## [0.8.1] — 2026-06-15

Hotfix for the PDF crop (`Cmd+Shift+X`) context regression.

### Fixed

- **PDF crop now captures region-scoped text as primary focus.** The previous
  hotfix made the crop image-only with empty text, which caused two regressions:
  the crop image had no `<primary_focus_selection>` anchor and got buried under
  the full-page background context, and the crop's text ("line") extraction was
  lost entirely. The crop now extracts **only the text lines inside the drawn
  rectangle** (via text-layer span ∩ crop-rect intersection, in reading order)
  and uses that region text as the crop's primary focus — never the whole page
  text (the original pollution bug stays fixed) and never empty. Scanned regions
  with no selectable text fall back to an image-only reference.
- **Image-only primary context is no longer buried.** A primary user reference
  that carries an image but no text (a scanned-PDF crop or a dragged image) now
  emits an explicit `<primary_focus_selection>` anchor naming the attached image
  as the core subject, instead of the weak, ignorable "(Image context attached
  below.)" line.

---

## [0.8.0] — 2026-06-14

Evidence Compiler Integrity release (Plan B + Plan B2). Markdown/PDF source
truth compiles into stable, minimal, claim-level grounded L2 knowledge
without formula loss, unsupported broad-span grounding, duplicate
accumulation, stale records, or partial authoritative publishes.

### Added

- **Claim-level minimal support lifecycle (§26.1).** Every extracted claim
  is validated by a deterministic structural gate (verified/failed/uncertain
  trichotomy) against hydrated full span text, with ordered LaTeX
  token-sequence formula matching (direction/binding-preserving, contiguous
  sub-formula aware). Wrong-real-span citations (F6) are release-blocking.
  Evidence freshness re-checks detect stale claim supports. No gold-fixture
  lookup at runtime (overfitting ban).
- **Formula lifecycle and selective recovery (§26.2).** Provider-free
  measured-loss classification (`fragmented|image_only|parser_omitted`),
  additive `source_spans.metadata.formula_recovery` candidates with 0.80
  acceptance threshold + validator-trace + exact-claim-formula gates, and
  page-hash invalidation. Formula-bearing graph input is never destructively
  truncated.
- **Staged compile generations and atomic publish (§26.3, Plan B2).** Every
  compile runs inside a `GEN-` generation. Visibility gated at
  write/materialization time: staged units are never emitted as ATM pages,
  upserted into the graph, or materialized into search. Atomic publish
  wraps reconcile + graph persist + generation flip in a single DB
  transaction. Graph extraction (LLM) runs during staging but persistence
  is deferred to the publish transaction. A failed gate/error discards the
  staged generation with the prior authoritative state byte-untouched.
- **Source edit/delete/split reconciliation (§26.4).** Unchanged claims
  (per `semantic_hash` + exact statement equality) keep their stable ids
  and verified supports. Changed claims are re-extracted. Claims whose
  source basis disappeared are retired. Stale spans are reconciled.
- **Compiler audit surface (§26.5).** `wiki lint` gains a Compiler
  Integrity section reporting unsupported/failed/stale claims, dangling
  supports, formula inconsistencies, staged leftovers, duplicate candidates,
  and broad-fallback findings (Plan-C-assigned). Exits non-zero on
  release-blocking findings.
- **Full-span hydration (F10, SEARCH_ENGINE_SCHEMA §10.2).** Evidence items
  carry `evidence_status='ok'` when hydrated, `'stale'` when falling back
  to the 200-char preview.
- **`list_serving_units` / `list_generation_units` APIs (§26.3).**
  Serving surfaces read only authoritative-generation ∧ verified ∧
  not-retired units. Compiler reads its own staged generation.
- **Legacy NULL-generation backfill.** `init_db` attributes pre-B2 verified
  units to a deterministic synthetic authoritative generation so
  generation-scoped visibility has no permanent NULL escape hatch.

### Changed

- `SCHEMA_VERSION` bumped from 7 → 8 (`claim_supports` table,
  `compiler_generations` table, `knowledge_units` additive columns).
- `db_sync` exports/imports both new canonical tables (`claim_supports` with
  LWW, `compiler_generations` with always-upsert).
- `compile_source_l2` now runs the full copy-on-stage pipeline: stage →
  validate → gate → reconcile + graph persist + publish (atomic txn) →
  re-emit ATM/search from the authoritative served set.
- `materializer` and `reemit_projections` read `list_serving_units`.

### Fixed

- F6 (wrong-real-span citations): release-blocking gate rejects zero-overlap
  span citations.
- F7 (stale span accumulation): reconciliation removes the edited source's
  prior spans instead of lingering beside replacements.
- F10 (truncated evidence): full-span hydration replaces the 200-char
  preview in evidence packs.
- Re-publish publish gate now audits the uncommitted re-validated state
  inside the same transaction (§26.3), so it checks exactly what is about to
  be committed and a re-validation can heal a transiently-dangling support
  instead of being permanently blocked.
- Stale `formula` support rows are cleared on re-validation when the claim
  lost its formula or no longer cites the support's span (§20.5), preventing
  lingering/dangling formula links; valid recovery links are preserved.

---

## [0.7.0] — 2026-06-12

Program 1 D2 quality-observatory release.

### Added

- Fine-grained provider-free retrieval evaluation with per-family Recall@k,
  MRR, citation correctness/completeness, authoritative provenance resolution,
  hard-negative outranks, indexed-character cost, and latency.
- Query-level minimal-support labels and an auditable D2 Q06 holdout result.
- Final Program 2/3 Failure Atlas handoff contracts.
- A tracked current-architecture testbed scenario gate covering CTX/ATM/CON/SYN,
  DB-native retrieval, query traceability, and unchanged-update correctness.

### Fixed

- Search-hit `source_span_ids` now survive the public search adapter and
  evidence assembly, including global search fallback.
- Orchestrated queries persist one authoritative `QTR-` containing the engine
  retrieval trace instead of a disconnected second trace.

---

## [0.6.1] — 2026-06-12

Hotfix release. No schema or API changes.

### Fixed

- **SQLite connection leak in `db.init_db`** (`backend/src/curator/db.py`).
  `init_db()` used `with sqlite3.connect(...)`, but Python's sqlite3 context
  manager only commits/rolls back the transaction — it never closes the
  connection. The leaked connection kept the `state.sqlite-wal` /
  `state.sqlite-shm` sidecar files alive until garbage collection, which is
  timing-dependent across platforms and caused environment-dependent
  `sqlite3.OperationalError: database is locked` failures on Ubuntu 24.04
  (observed in `wiki status` bootstrap paths and the corresponding test).
  `init_db()` now closes its connection explicitly in a `finally` block, so
  no WAL sidecars outlive the call.
- **Same leak class in `db.connect()` on the setup-failure path** (review
  follow-up). `connect()` ran `executescript(SCHEMA_SQL)` and
  `_apply_migrations()` *before* its `try`/`finally`, so an exception during
  schema setup or migration leaked the connection and its WAL sidecars
  exactly like the `init_db` bug. All post-instantiation work now runs inside
  the `try` block. Regression test holds a reference to the connection and
  asserts it is closed (GC-independent) with no surviving sidecars.
- **Unbound `conn` in Zotero readers' error paths.** One site in `zotero.py`
  and both sites in `zotero_integration.py` referenced `conn` in `finally`
  without initializing it before `try`; if `sqlite3.connect()` itself raised,
  the cleanup raised `UnboundLocalError` and masked the original error. All
  sites now initialize `conn = None` first, matching the existing pattern in
  the other `zotero.py` readers. With these, every production
  `sqlite3.connect` call site is leak-safe on both success and failure paths.

---

## [0.6.0] — 2026-06-12

Program 1 (RAG & Knowledge Quality Stabilization) — Plan D1 diagnostic
baseline release. **No runtime behavior, schema, or API changes**: this
release freezes the truth contract that Programs 2/3 will be measured
against.

### Added

- **Failure Atlas diagnostic contract** (`docs/specs/failure_atlas/`).
  Versioned machine-readable case records for all thirteen suspected
  end-to-end quality failures (F1–F13), each with exact code boundary,
  minimal deterministic fixture, capture-before-repair evidence, frozen
  oracle, status lifecycle (`suspected → reproduced → assigned/accepted |
  disproven`), and downstream owner (Plan D2, Program 2, or Program 3). All
  thirteen were reproduced deterministically and assigned.
- **Deterministic reproduction suite**
  (`backend/tests/test_failure_atlas_repro.py`). Baseline tests pin the
  current defective behavior; strict-xfail oracle tests encode the desired
  contract and intentionally fail CI (XPASS) when a failure is fixed without
  updating the atlas — the mechanical anti-silent-redefinition handoff.
- **Atlas contract tests** (`backend/tests/test_failure_atlas_contract.py`)
  rejecting missing snapshot identities, missing oracles, aggregate-only
  reporting, unsupported status transitions, and dangling fixture references.
- **Mutation/degradation/atomicity experiments**
  (`backend/tests/test_failure_atlas_experiments.py`): unchanged-rebuild
  idempotency at L1/search, rename-duplication, failed-batch partial graph
  state, and provider-free lexical degradation evidence.
- **Frozen evaluation baseline** (`fixture_corpus.yml`, `qrels.yml`,
  `EVALUATION_BASELINE.md`, `backend/tests/test_failure_atlas_eval.py`):
  synthetic corpus with dev/regression/holdout/adversarial partitions,
  deterministic lexical baseline metrics (binding regression floor:
  Recall@1 = 1.0, 0 hard-negative outranks), and a runner-enforced
  no-holdout-tuning rule. Proposed Program 1/2/3 thresholds recorded,
  pending user approval.
- **Docs**: `SYSTEM_BEHAVIOR.md` §25 (Failure Atlas diagnostic contract) and
  `AGENT_WORKFLOW_GUIDE(_KR).md` §5 (running the diagnostic suite; rules when
  a change touches an atlas case).

---

## [0.5.6] — 2026-06-12

### Added

- **PDF add-source asset routing (`--asset-dir`).** Images extracted from an
  added PDF during instant L1 no longer always land in the hardcoded
  `05_Assets/<slug>/`. `wiki plugin source register` accepts a vault-relative
  `--asset-dir`; the plugin resolves it per source — Zotero-backed PDFs reuse
  the Zotero import profile's asset folder (plus a per-item subfolder from the
  item's display name), other PDFs use a sanitized source-name subfolder under
  the new `incuratorPdfAssetFolder` base folder. Unsafe values (absolute paths,
  `..` escapes, or path-resolution errors) and an empty setting fall back to
  the legacy `05_Assets/<slug>/`, and the L1 page's `![[...]]` embeds always
  reference the folder actually written (PLUGIN_SCHEMA §1.1).
- **Inert "Added" badge for tracked sources.** A successfully built source
  (`l1_ready` … `l4_ready`) now shows a single non-clickable **Added** badge in
  the chat context chip instead of clickable layer labels, so an
  already-tracked PDF can no longer be re-imported by accident. The tooltip
  still exposes the underlying layer state, and a refresh that re-derives
  `stale`/`moved`/`changed`/`missing`/`error` makes the badge actionable again
  (PLUGIN_SCHEMA §4.1.1).

### Fixed

- **PDF viewer-to-L1 adaptive routing.** Passive PDF chat no longer registers an
  untracked source. Local PDF.js text/crops remain the fast path; after an
  explicit Add Source completes L1, durable CTX ToC/section projection becomes
  available without reparsing the original PDF. Missing or preview-only CTX
  projections visibly degrade to read-only parsing, and PDF-focused turns do
  not use concept-grounded `curator_query` until the relevant source reaches L3.

### Documentation

- Documented what add-source actually does (instant L1 immediately, L2/L3
  queued to the background worker) and where extracted PDF figures land, in
  `PLUGIN_GUIDE` (EN/KR). PDF math-extraction fidelity is explicitly out of
  scope here and tracked by the RAG & Knowledge Quality Stabilization program.
- Reconciled the documentation authority and workflow contracts with the
  implementation: `state.sqlite` is authoritative, Collections Markdown is a
  disposable projection, queries are sessionless, CLI `wiki add` stops at L1
  while plugin Add Source queues L2/L3, PDF.js remains the viewer fast path,
  and correction proposals classify without silently patching generated nodes.
  Also repaired internal documentation links and advanced the spec-sync guard
  to v0.5.6.

---

## [0.5.5] — 2026-06-11

### Fixed

- **LaTeX-copy review fixes (PR #22):** an escaped backtick (`\``) no longer makes
  the math-source parser mistake it for an inline-code opener (which could drop a
  later formula); the chat/quick-query copy handler reads the element's own
  document selection (`el.ownerDocument`) so it works in Obsidian pop-out windows;
  and the reading-view math post-processor extracts section source by line index
  instead of splitting the whole document on every render (large-note perf).
- **Zotero reload emitted absolute cache image paths.** "Reload Source"
  (`Cmd+Shift+R`, formerly "Refresh Zotero Item") read the deprecated `imageFolder`
  profile field, which was empty after the wizard migrated to
  `assetFolder`/`assetSubfolder`, so it skipped localization and wrote
  `![[/Users/.../Zotero/cache/...]]` instead of vault-relative `![[05_Assets/...]]`.
  Reload and import now share one localization path (`src/zotero/assetLocalization`).
- **Changed annotation regions did not refresh.** Localization skipped any asset
  that already existed; it now overwrites an asset whose source region bytes
  changed (and only then), so edited annotations update.
- **`zotero_app_url` PDF open failed with "attachment key not found".** That URL
  carries the **parent item** key; backend `resolve-pdf` now resolves it to the
  item's child PDF attachment and returns the effective `attachment_key`.
- **Zotero annotation links did not jump to the annotation.** The plugin now uses
  the resolved child attachment key for annotation lookups, so a parent/select link
  can open the PDF *and* navigate to + highlight the annotation.
- **`Cmd+Shift+R` reloads the active Zotero note OR external PDF view**, via the
  same code path as the PDF viewer's toolbar Reload button.
- **Dashboard showed a stale backend version / provider.** The dashboard read a
  cached `runtime/status.json` first; it now forces a fresh `wiki status` snapshot
  (deduped per render burst) and reports the backend as *unavailable* instead of
  trusting a stale snapshot when `wiki status` fails. A backend upgrade or
  `wiki config provider` change is reflected on the next dashboard open/refresh
  without restarting Obsidian.
- **External PDF view lost its document after restart** (`resolveDoc failed: no
  path in docState or cache for ID`). The persisted-doc cache no longer drops a
  path-bearing entry at load (startup `existsSync` race), `setState` keeps the doc
  identity even when a restored state lacks a name, and `getState` always persists
  the path — so a reopened/restored PDF resolves the same document; a genuinely
  missing file is reported distinctly at use time.

---

## [0.5.4] — 2026-06-11

### Added

- **LaTeX-preserving copy from the AI chat (copy as Markdown).** Selecting part of
  an assistant reply and pressing `Cmd/Ctrl+C` now copies it as Markdown with
  formatting *and* the formulas' LaTeX **source** (`$...$` / `$$...$$`) restored,
  instead of the browser's flattened plain text / empty MathJax SVG.
- **LaTeX-preserving copy/cut from a note's Reading View.** Drag-selecting note
  text that contains a formula and pressing `Cmd/Ctrl+C` (or `Cmd/Ctrl+X`) copies
  the selection as Markdown with the LaTeX source restored. Works in pop-out
  windows. The selection visually skipping a non-selectable formula is expected —
  the formula is still captured.
  - Implemented via a Markdown post-processor that re-parses each rendered
    section's source and stamps it onto every formula as `data-tex` (only when the
    parsed and rendered formula counts match exactly, so a wrong source is never
    attached), plus a capture-phase clipboard handler gated to
    `.markdown-reading-view` + rendered math.
  - Non-math selections are left to Obsidian's native clipboard (byte-identical).
    Live Preview / Source mode already preserve `$...$` natively (CodeMirror copies
    the document source), so they are unchanged.

### Docs

- `PLUGIN_GUIDE` (EN + KR) §3.6/§3.7 and `PLUGIN_SCHEMA` §14 document the chat and
  Reading-View LaTeX copy behavior, the render-time stamping mechanism, and the
  exact-count correctness guard.

---

## [0.5.3] — 2026-06-11

### Removed

- **GitHub CLI (`gh`) dependency** — Incurator no longer requires or installs
  `gh`. `setup.sh` no longer installs it; the plugin's GitHub Sign-in/out
  settings toggle, the `github_authenticated`/`github_account` status fields, and
  `auth/githubAuth.ts` are removed; the backend `git_manager` no longer shells
  out to `gh auth status`. None of the core Git features needed it — `status`,
  `log`, file `history`, `commit`, and `push` all use the local `git` binary.

### Changed

- **Sidechat Git integration is local-only.** Asking "how did I write this
  before?" / history & status / push continue to work via local `git` with no
  GitHub account. HTTPS-push authentication, if you use it, is handled by your
  normal git credential helper, outside the plugin (commit/push can also stay
  with whatever tool you already use).

---

## [0.5.2] — 2026-06-11

### Fixed

- **Plugin no longer falls back to a stale `backend/.venv`** — `resolveWikiBinary`
  used to probe `<repo>/backend/.venv/bin/wiki` as a fallback after the canonical
  `<repo>/.venv/bin/wiki`. Because `backend/.venv` is never created by the
  supported workflow, when present it is stale, and running it silently executed
  an out-of-date backend (wrong version, missing fixes) without the user
  noticing. The resolver now probes ONLY the repo-root `.venv` and returns
  nothing if it is absent, so the user is prompted to re-run `./setup.sh` instead
  of unknowingly running an old build.

## [0.5.1] — 2026-06-11

### Fixed

- **Ask AI dropped formulas when selecting over math** — the quick-query popover
  captured the selection via `selection.toString()`, which is empty for a
  MathJax formula rendered as SVG, so dragging across a formula lost it. Capture
  now reads the formula's LaTeX source from the DOM annotation (present in both
  the SVG and the Live-Preview swapped-text state), preserving `$...$` / `$$...$$`
  — independent of render timing. Non-math selections are unchanged.

### Added

- **Keyboard selections trigger Ask AI** — selecting text with the keyboard
  (Shift+Arrow, Shift+Home/End, or Ctrl/Cmd+A) now surfaces the floating
  **✨ Ask AI** button, not just a mouse drag. Collapsing the selection back to a
  caret hides it.

> Note: copying only a partial editor selection with LaTeX intact (Cmd+C in an
> open note) remains deferred — see the ROADMAP Icebox.

---

## [0.5.0] — 2026-06-11

### Changed

- **Resilient, ambiguity-safe agent-edit matching** — `ai-agent-edit` SEARCH
  blocks no longer need to match the file byte-for-byte. A single shared matcher
  (`utils/editMatch.findSearchBlock`, used by every apply and preview path) tries
  `exact → line-trim → anchored`, tolerating leading/trailing whitespace and
  indentation-level drift, and always splices the file's real text. It refuses
  (returns null → "could not find") when ≥2 spans are plausible or an anchored
  span balloons past 3× the search size, so it never applies a guessed edit. This
  fixes the frequent "Could not find the exact SEARCH block" failures where no
  diff rendered at all.
- **Immediate diff (safe-gated)** — when an answer's edits target the note you're
  already viewing (or no note is focused), the in-editor Diff Viewer now opens
  automatically instead of waiting for a "Review Diff" click. A different focused
  note keeps the clickable pill so the diff never steals your editor; auto-open
  fires once per message and never on history re-render.
- **Diff Viewer hunk counter is always visible** (e.g. `1/1`), with ↑/↓ · Tab
  navigation and Y/N/Enter/Esc shortcuts for multi-hunk diffs (unchanged).
- **Scoped edits** — the edit prompt now requires minimal, section-scoped REPLACE
  bodies (never pasting a whole chat answer), plus a non-blocking "large
  replacement" warning as a model-independent safety net.

### Fixed

- **Leaked edit markers** — orphan `<<<<` / `====` / `>>>>` markers from a
  malformed/partial edit block are stripped from the rendered message (fence-aware,
  evidence-gated). Stored message content is untouched, so "Copy as Markdown"
  stays faithful. The block parser also tolerates marker spacing/length variants
  and a missing closer.

### Removed

- **On-disk diff artifact** — the `00_System/Agent Diffs/` note feature and its
  **Write edits as diff artifact** setting were removed; the in-editor Diff Viewer
  is now the single source of truth. Existing artifact files in your vault are
  left untouched.

---

## [0.4.4] — 2026-06-11

### Fixed

- **Plugin resolved a stale `wiki` binary** — `resolveWikiBinary` probed
  `<repo>/backend/.venv/bin/wiki` *before* the canonical repo-root
  `<repo>/.venv/bin/wiki`. Because `setup.sh` installs the live backend into the
  root `.venv` (`VIRTUAL_ENV="$ROOT_DIR/.venv"` + `uv pip install -e ./backend`),
  the leftover `backend/.venv` copy was frequently stale, so the plugin reported
  an old backend version (e.g. `0.4.2`/`0.3.2`) and silently broke the self-update
  toast. The probe now prefers the root `.venv` and keeps `backend/.venv` only as
  a fallback for un-migrated checkouts. Completes the install-path hotfix started
  in the previous commit.
- **Backend dashboard misreported the active model** — the LLM selector fell back
  to the first catalogue entry (Antigravity Gemini) whenever the configured model
  was not in the bundled catalogue (e.g. a custom local Ollama model like
  `qwen2.5:3b`), so the dashboard always showed Antigravity Gemini even though the
  backend config (`wiki status`) was correct. The unmatched model is now surfaced
  as its own "(current)" option and selected, keeping the display faithful to the
  persisted config.
- **Docs path scrub** — removed an absolute `file:///Users/...` link from
  `SYSTEM_BEHAVIOR.md` (now relative) and genericized real vault-name examples
  (`second_brain`, `/Users/<you>/...`) to `/path/to/<vault>/...` in the dev/sync
  guides. Updated `DEV_SCRIPTS_GUIDE` to match `plugin/deploy.sh`'s new local-build
  fallback when `OBSIDIAN_PLUGIN_DIR` is unset.

---

## [0.4.3] — 2026-06-07

### Fixed

- **Chat sidebar LaTeX selection** — Shift+click could not extend a text selection
  across rendered MathJax formulas because SVG elements block mouse events by
  browser default. Added `pointer-events: none` and `user-select: text` on
  `.ai-agent-chat-msg-content mjx-container` and its SVG child so that the mouse
  event passes through to the surrounding text layer, letting selection span
  formulas. The existing `copy` event interceptor then extracts LaTeX source from
  `annotation[encoding="application/x-tex"]` as before.

---

## [0.4.2] — 2026-06-07

### Added

- **LaTeX copy preservation** — selecting rendered math in the agent chat sidebar
  or quick query popover and pressing Ctrl+C now copies `$...$` / `$$...$$` LaTeX
  source instead of empty SVG content. Implemented via a `copy` event interceptor
  that extracts the source from MathJax v3 `annotation[encoding="application/x-tex"]`.
- **PDF → LaTeX conversion** — right-click "Convert to LaTeX (Copy)" (or
  Cmd+Shift+C) in the PDF viewer sends selected text to the LLM, which returns
  clean Markdown with proper LaTeX delimiters. Result is copied to clipboard.
  Shortcut registered on `ownerDocument` via `registerDomEvent` for correct
  event bubbling and automatic cleanup.

### Fixed

- **CI TypeScript check** — `buildManifest.json` is gitignored so it was absent
  in CI after checkout. Plugin-tests job now generates a minimal stub before
  `tsc --noEmit` and `vitest run`.
- **CI pytest** — `test_plugin_version_returns_build_fields` was asserting stale
  `*_fingerprint` fields removed in v0.4.1. Updated to match current schema.
- **setup.sh plugin deploy** — after building, setup.sh now reads `last_root`
  from `.cache/config/last_root` and copies `main.js`, `manifest.json`,
  `styles.css` directly to the vault's plugin directory. Removes the need for
  `OBSIDIAN_PLUGIN_DIR` or a `.env` file.

---

## [0.4.1] — 2026-06-07

### Added

- **Vault schema migration** (`wiki migrate`) — explicit upgrade path for vaults
  after a backend update changes config or Collections structure. Tracks
  `VAULT_SCHEMA_VERSION`; `wiki status` warns when a vault is behind. `wiki migrate`
  applies pending steps, scans `Collections/*.md` for files missing required
  frontmatter fields, and `--requeue` re-queues their sources for regeneration.
  `--dry-run` previews without writing. `wiki init` stamps new vaults with the
  current schema version.
- **Plugin repo-path auto-discovery** — the backend now reports its own repo root
  via `wiki plugin version` (`repo_path`), so the Obsidian plugin no longer needs
  a manually configured "Repository path". The setting becomes an optional
  override. Non-editable (site-packages) installs report `repo_path: null` and the
  plugin hides the update banner instead of showing a dead button. The 1-click
  update copies built plugin files into the currently open vault only.

### Fixed

- **Machine-local config isolation** (`config.py`) — `llm`, `search`, and
  `external` blocks are no longer stored in the synced vault `.curator/config.yml`.
  `load_config()` automatically migrates any existing machine-local blocks into
  `.cache/config/config.yml` (global cache) and rewrites the vault config without
  them. `zotero_init()` saves Zotero roots to the global cache instead of the
  vault config, so ZotMoov/data-directory paths never leak into synced state.
- **Portable Zotero source identity** (`runtime_state.py`) — `build_sources_snapshot()`
  now returns `zotero://open-pdf/library/items/<attachmentKey>` as `source_path`
  for Zotero-backed references (where `logical_source_id` starts with `zotero:`).
  The absolute local PDF path is preserved as `external_path` (device-local hint)
  and is no longer surfaced as the portable display identifier.
- **Plugin dashboard always refreshes local snapshots** (`incuratorDashboardModal.ts`) —
  Added `readFreshRuntimeJson()` which always triggers a local backend refresh
  before reading. Sources tab now uses it so the dashboard never renders a peer
  device's stale snapshot. `wiki config set llm.fallback` no longer passes
  `--local` (vault scope); LLM fallback is now written to the machine-local
  global config, consistent with how all `llm` config is handled.

---

## [0.4.0] — 2026-06-06

### Added

- **Cross-device Knowledge Sync Bridge** (`wiki db export / wiki db import`)
  - Export the knowledge DB to a portable JSONL file (`wiki db export`)
  - Import a JSONL file into another device's DB with Last-Write-Wins merge (`wiki db import`)
  - `--dry-run` option to preview changes before writing
  - `--compress` option for gzip output (`.jsonl.gz`)
  - `--since <datetime>` for incremental (delta) exports
  - Post-import automatic `wiki reindex` (skippable with `--skip-reindex`)
  - Device-local tables (embeddings, job state, FTS5 indices) are automatically excluded from exports
- **Tombstone table** (`deleted_records`) — deleted records propagate to other devices on next import
- `db_sync.record_tombstone()` helper for future delete operations to call
- **Syncthing auto-sync (Zotero-grade, one-writer-per-file)** (`wiki db autosync`)
  - Each device writes only its own `.curator/sync/dev-<id>.jsonl` snapshot and imports
    every peer's — no Syncthing write-write conflicts by construction
  - Row-level Last-Write-Wins + tombstones: concurrent offline edits on two devices both
    survive (no whole-file overwrite)
  - Structural loop prevention with **no content-hash guard**: own file never imported,
    re-export only when the local DB actually changed
  - Syncthing `*.sync-conflict-*` files imported as LWW peers, then archived under
    `.curator/runtime/sync_conflicts/`
  - Reference-Mode `sources.external_path` preserved per device on merge
    (`_DEVICE_LOCAL_COLUMNS`)
  - Device-local `.curator/sync_state.json` (excluded via `.stignore`) tracks device id +
    per-peer high-water marks
  - Obsidian plugin: on-load sync, `.curator/sync` file watcher (desktop) + 60s poll
    fallback, manual "Sync Knowledge DB" ribbon, status-bar indicator, four default-on
    settings toggles
  - Optional `auto_sync.enabled` so CLI `wiki update` exports this device's snapshot

### Changed

- `SCHEMA_VERSION` bumped from 6 → 7 (non-destructive; adds `deleted_records` table only)
- Existing vaults self-heal on next `wiki` invocation

### Fixed

- `wiki db import` reported `0 changes` after any prior export — caused by a
  `sync_meta.json` content-hash loop guard, now removed in favor of structural
  loop prevention (dry-run and real import report/apply the identical delta)

### Documentation

- `docs/guides/USER_GUIDE.md` + `USER_GUIDE_KR.md`: "Cross-Device Knowledge Sync" +
  `wiki db autosync` section
- `docs/guides/PLUGIN_GUIDE.md` + `_KR.md`: plugin auto-sync settings/triggers
- `docs/guides/SYNC_IGNORE_GUIDE.md` + `_KR.md`: `sync_state.json` exclusion;
  keep `.curator/sync/` synced
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: §13.1 one-writer-per-file auto-sync;
  §13.3 device-local sync state
- `docs/specs/curator_schema/SCHEMA.md`: §11.17 `deleted_records` contract +
  `_DEVICE_LOCAL_COLUMNS`

---

## [0.3.3] — 2026-06-06

Initial release on `master` branch. Baseline for the v0.4.x series.
