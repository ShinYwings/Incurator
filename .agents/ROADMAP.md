# Incurator Active Roadmap

Updated: 2026-08-05

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
   - **Next, unblocked**: B4 — remove `wiki query --update` and its
     `add_atom_from_insight` path (Exhibition-era leftover, not a fix), plus the
     secret-decryption failure reported as a missing API key.
   - **Blocked on the build**: B3 (Q1 = `l4_status='error'`, which makes B3 a
     Minor; Q2 = delete the dead L2 checkpoint-resume). Decided, but the l4
     semantics should be confirmed against a vault whose `skipped` means what it
     says — i.e. after the current `wiki build`.
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

3. **Build-artifact audit findings** (new, 2026-08-06, post-v0.43.0 build)
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

4. **Job progress is unobservable, and Reference-Mode jobs display as `.md`**
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

5. **Chat Session Context Compaction**
   - Draft: `.agents/drafts/chat_context_compaction.md`

6. **Vault Storage Governance & Quota Visibility**
   - Draft: `.agents/drafts/vault_storage_governance.md`

7. **Native PDF Annotation & Asset System**
   - Draft: `.agents/drafts/pdf_annotation_system.md`

8. **Web Search Integration**
   - No current plan. Re-plan from current provider, privacy, and cost
     constraints before implementation.

9. ~~**Agentic PDF Retrieval Tools for Ask AI/Sidechat**~~ — shipped in
   v0.41.0 as a local (non-MCP) read-only page reader. Scope was narrowed
   during planning: `fetch_pdf_page` is first class, `search_pdf_anchor` is
   exposed only for documents proven outline-less, and CLI providers keep the
   deterministic path. Historical context: `git show` the deleted
   `.agents/plans/04_agentic_pdf_retrieval.md` and
   `.agents/plans/agentic_pdf_retrieval_arena/`.

## Blocked / Icebox

- None.
