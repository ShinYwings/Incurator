# Incurator Active Roadmap

Updated: 2026-08-06

This file contains only live work. Completed milestones and planning artifacts
belong in Git history, not the active workspace. New raw reports enter through
`.agents/USER_REPORT.md`.

## Active Queue

1. **System Integrity Consolidation — B2 through B7** (in progress)
   - Single milestone replacing the former regression-audit (P10) and stability
     overhaul umbrellas. 22 work items from the v0.42.x Arena audit.
   - **Shipped**: B1 plugin lifetime/teardown (v0.42.4) · the Quick Query
     document-identity P1 (v0.42.3) · the corroboration-gate fix that unblocked
     L3/L4 (v0.43.0).
   - **Also shipped**: B4 (v0.44.0) · B3 P1-P4 (v0.45.0, `l4_status='error'`
     per Q1, the `layer_error` primitive, and the glob-promotion deletion).
   - **B3 remainder**: P5 (synthesis dep-hash freeze), P6 (Q2 = delete the dead
     L2 checkpoint-resume, a table migration), and P7 (record a reason on
     legitimate skips — needs a decision on whether `layer_error` or
     `error_reason` carries a non-error reason).
   - **B2** (cross-device sync integrity, the last P1): Q5 = no migration needed
     (zero backslash relpaths; Windows unsupported), Q6b = Windows not supported.
   - **B5 / B7** each require their own Arena plan before implementation.
   - Gate G0 is CLOSED: all three missing passes ran.
   - Plan: `.agents/plans/03_system_integrity_consolidation.md`
   - Arena record: `.agents/plans/system_defect_audit_arena/`

2. **Retrieval reaches the distilled layers** (new, from the v0.43.0 follow-up)
   - The `local` route never consults L4/L3 — it goes entities → L1 spans → flat
     search, so the layer split delivers none of its intended cost benefit and
     bibliography lines outrank equations.
   - Formula availability is a retrieval-ranking problem, not the L2 support
     gate: all 105 equation spans are already indexed.
   - **Sequenced after the current build**: both need a repopulated L3/L4 to be
     judged. Re-measure first with `/tmp/measure_after_build.sh`.

3. **`.curator` state audit findings** (new, 2026-08-06, from the artifact-first Arena)
   - **[P1] The chat sidebar's job/status indicator has been dead since
     2026-07-04.** It polls `<vault>/.curator/runtime/jobs.json`, which the
     backend stopped writing when runtime snapshots moved to the repo cache.
     Verified: the vault file says `idle: true`, the live one says `running: 1`.
     This is the user's own "build indicator appears then stops" report. Fix is
     to call `wiki status --json` as `incuratorDashboardModal` already does —
     not to correct the path, since the plugin cannot compute the cache key.
   - **[P1] Losing `.cache/` reports a healthy empty vault**, because `connect()`
     self-heals a schema into any empty DB file and `get_stats` returns zeros.
     Recovery exists (the in-vault sync journal + `wiki db import`) but is
     silent and undocumented.
   - **[P1] Vault rename/move silently mints a new empty database** — the cache
     key is `sha256(resolved_root)[:16]`. Also hits `VAULT_ROOT=testbed` run
     from two different directories.
   - **[P2] `sessions.json` is 15 MB, 81% re-embedded context** (one note stored
     52×, a 1.39 MB base64 image); ~1.1 s per send, and the 30-session cap is a
     provable no-op. Supersedes the vaguer "Chat Session Context Compaction"
     item with measurements.
   - **[P2] Sync journals never compact** — 24 MB, unused gzip measured at
     9.86×, tombstones never expire, a stale peer is skipped silently while
     autosync reports success.
   - **[P2] Several derived artifacts are never rewritten**, incl. `wiki sync`
     claiming to rebuild `ledger.md`/`overview.md` while calling neither.
   - **[P3] Docs contradict themselves** on where `state.sqlite` lives —
     SYSTEM_BEHAVIOR contradicts itself internally.
   - Arena record: `.agents/plans/curator_state_arena/`
   - Synthesis + sequencing: `.agents/plans/curator_state_arena/03_synthesis.md`

4. **Vault file moves and deletes are not tracked anywhere** — shipped v0.46.0
   for moves/deletes going forward. Remaining: retro-repair of vaults that
   already carry a dead source row (needs a content-hash reconciliation sweep).
   - The plugin registers **no** vault file events at all — two `registerEvent`
     calls exist repo-wide and both are workspace layout events. No
     `vault.on("rename")`, no `vault.on("delete")`. Pinned context keeps a dead
     path and the agent reports "File not found".
   - The backend denormalizes the path into `sources.relpath`,
     `source_spans.relpath`, and `search_documents.projection_path`, and
     reconciles none of them on a move. Already rotting: source 32 points at a
     path that exists nowhere, and its 48 descendant atoms are the 48 lint
     errors that survive the v0.44.1 fix.
   - Reference Mode complicates it: `sync_key` embeds the path, and the Zotero
     `logical_source_id` must survive a move.
   - **Needs a PLAN_TEMPLATE plan before implementation.**
   - Evidence: `.agents/USER_REPORT.md` (2026-08-06).

5. **Build-artifact audit findings** (new, 2026-08-06, post-v0.43.0 build)
   - `wiki lint` is unusable as a signal: 70 unfixable `invalid_source_path`
     ERRORs. 22 are a macOS NFC/NFD byte-compare false positive whose suggested
     `--fix` writes back the same value, so the error can never be cleared; 48
     come from one genuinely mangled `sources.relpath` (a title slug with a
     `-ref-5` suffix that never existed on disk).
   - Community hierarchy is flat by construction (`level = 0` hardcoded) with
     one 176-entity giant and a 152-community singleton tail. §27.4 sanctions
     the degraded fallback but requires it be "surfaced by the audit" — nothing
     reports the mode.
   - One stale CTX file survives re-ingest; every other layer is 1:1 with the DB.
   - 10 sources are `skipped` with no recorded reason, two of them holding 11
     knowledge units each (feeds B3).
   - Evidence: `.agents/USER_REPORT.md` (2026-08-06).

6. **Job progress is unobservable, and Reference-Mode jobs display as `.md`**
   - `ingest_worker.py:180/195` writes `progress=0.1` once when L2 starts and
     `0.5` only after all of L2 returns; `progress_current/progress_total` stay
     `0/1` and `job_events` gets zero rows, so a long job is indistinguishable
     from a hung one. Same defect class as the popover "Thinking…" fix.
   - `wiki jobs list` renders `sources.relpath`, which for `is_reference`
     sources is the `04_Resources/` markdown stub — so a PDF job shows a `.md`
     name. The stub filename template also emits a trailing empty field
     (`"… - .md"`).
   - Related: no way to cancel a job that is already running.
   - Evidence: `.agents/USER_REPORT.md` (2026-08-05).

7. **Chat Session Context Compaction**
   - Draft: `.agents/drafts/chat_context_compaction.md`
   - **Superseded in evidence by item 3**, which supplies the measurements this
     draft was missing: 15 MB file, 81% `contextRefs`, one note stored 52×, a
     1.39 MB base64 image, ~1.1 s per send. Fold them in before planning.

8. **Vault Storage Governance & Quota Visibility**
   - Draft: `.agents/drafts/vault_storage_governance.md`

9. **Native PDF Annotation & Asset System**
   - Draft: `.agents/drafts/pdf_annotation_system.md`

10. **Web Search Integration**
   - No current plan. Re-plan from current provider, privacy, and cost
     constraints before implementation.

11. ~~**Agentic PDF Retrieval Tools for Ask AI/Sidechat**~~ — shipped in
   v0.41.0 as a local (non-MCP) read-only page reader. Scope was narrowed
   during planning: `fetch_pdf_page` is first class, `search_pdf_anchor` is
   exposed only for documents proven outline-less, and CLI providers keep the
   deterministic path. Historical context: `git show` the deleted
   `.agents/plans/04_agentic_pdf_retrieval.md` and
   `.agents/plans/agentic_pdf_retrieval_arena/`.

## Blocked / Icebox

- None.
