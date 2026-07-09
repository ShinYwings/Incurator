# Incurator Master Roadmap & Todo List

This is the master roadmap for major architectural overhauls and future updates.
It tracks only live priorities and active follow-up references. Completed plan
artifacts are removed from `.agents/plans/`; use Git history for old plans.

## 🚨 Update Classification & Planning Rule

Before starting work, all agents MUST use `.agents/USER_REPORT.md` as the Single
Source of Truth to identify unresolved items.

- **Major and Minor Updates**: do not write code immediately. Write or update a
  milestone plan using `.agents/PLAN_TEMPLATE.md` first, then implement.
- **Hotfix and Simple Bug Fixes**: may skip heavy planning only when the change is
  small, isolated, and does not alter public contracts, schemas, or architecture.
- **Completed plans**: delete active `.agents/plans/` artifacts after shipping.
  The Git history is the archive.

---

## 📥 Triage & Queuing

`USER_REPORT.md` is currently empty. The following queue is the ordered roadmap.

No urgent items currently tracked.

### 🚨 Immediate Next Release

No urgent items currently tracked.

### 🚀 Priority Order

1. **[Major Update] System Stability Overhaul — Exhaustive Diagnosis & Refactoring** *(ACTIVE)*
   - Absorbs the prompt-architecture milestone. Whole-codebase diagnosis (bugs,
     redundancy, architectural debt) + refactoring with architectural redesign
     allowed; prompt-v2 for cross-model output consistency; legacy/dead-code sweep.
   - Master Plan: `.agents/plans/01_system_stability_overhaul.md`
   - Briefing: `.agents/plans/system_stability_overhaul_arena/00_problem.md`
   - Delivered as a chain of incremental release PRs (starting from v0.34.0+).
   - **Shipped stability & hardening releases (v0.25.0 → v0.33.0)**: diagnosis G17–G19, XC-1/XC-4 robustness slices, DB-2 slices 1–2, CLI/MCP warning visibility, portable paths v0.29–v0.32, cross-device LWW sync v0.30, and strict v12 schema/reindex speedup v0.33.0.
   - **Remaining Scope for Upcoming Releases (v0.34.0+)**:
     - **God-file Decomposition (CM-1 / PL-1)**: decompose `cli.py`, `mcp_server.py`, `plugin_api.py` (CM-1) and plugin god-files `chatSidebar.ts`, `llmClient.ts`, `externalPdfView.ts` (PL-1).
     - **Exception Handling Hardening (XC-1 Slices 2+)**: narrow broad exception blocks in `cli.py`, `mcp_server.py`, `plugin_api.py`.
     - **Performance & UX Refinements**: RAG/DAG benchmark harness & retrieval hotspot optimization; chat/popover UX friction cleanup.

2. **[Validation] `[[wikilink]]` Architecture Validation**
   - Core entities in the backend pipeline documents are not explicitly marked with `[[wikilink]]`.
   - Validate `backend/src/curator/page_writer.py` and `sync.py` backlink parsing logic against `[[wikilink]]` syntax.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Wikilink section)

3. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

4. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

5. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

6. **[Minor Update] Web Search Integration**
   - Design and integrate web search capabilities for local models (Ollama, Deepseek, etc.).
   - Investigate API options (Brave, SerpAPI) and implement `web_search.py`.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Web Search Section)

---

## ✅ Completed Milestones

- **v0.33.0 — Strict Sync Schema Enforcement & Startup Speedup** (shipped 2026-07-09, PR #84
  merged): removed legacy pre-v12 database schema migration and automatic fallback conversions;
  simplified db init and connection pathways; added incremental embedding reindex speedups
  and fixed cross-device config isolation.
- **v0.32.2 — Autosync Legacy Peer Hotfix** (shipped 2026-07-06, PR #83
  merged): fixed `db autosync` crash on pre-v12 legacy peer export files
  missing `export_id`.
- **v0.32.1 — Cross-Device Integrity Boundary** (shipped 2026-07-06, PR #82
  merged): schema v12 `sync_key` transport identity with source-id remap on
  import; `compiler_generations.updated_at` for monotonic LWW; `export_id` in
  JSONL headers; table/column allowlist on import; device-local state
  (DB, runtime, staging, logs, PDF caches) relocated to
  `.cache/vaults/<vault-key>/`; one-time DB migration with dual-existence abort;
  serialized session/profile saves; Zotero profile deletion tombstones; plugin
  temp paths isolated to repo cache.
- **v0.32.0 — Portable-Path Compatibility Removal** (shipped 2026-07-04,
  PR #80 merged):
  removed the `wiki paths` command, standalone portable migration service,
  DB-connect v9/v10 source-table converter, legacy external-root array
  conversion, and absolute non-reference relpath fallback. The macOS
  `second_brain` DB was backed up and normalized to schema 11 with all three
  Zotero keys preserved; deployed `wiki status` reports backend 0.32.0.
- **v0.31.0 — Pipeline State Integrity + Sync Hardening** (shipped 2026-07-03,
  PR #79 merged): replaced filesystem layer counts with
  authoritative serving DB counts; added schema-v11 source revisions for
  status-only LWW; corrected false L2/L3/L4 ready states; repaired Zotero
  attachment-key L1 resolution and implicit Tesseract failures; atomically wrote
  sync snapshots; serialized/merged Zotero profile saves; added MCP/worker
  exports and compound-command export deduplication. Production `second_brain`
  migrated cleanly with 32/32 L1, zero errors, orphan projections removed, and
  interrupted jobs recovered to queued.
- **v0.30.0 — Cross-Device State Sync** (shipped 2026-07-02, PR #78 merged;
  two review rounds fixed on-branch: corrupt/structural profile-store guards,
  migration-ordering safety, incremental-sync export hook, LWW gate `>=` +
  tombstones, profile field sanitization): fixed the
  "Dashboard shows 5 sources instead of 31 on the other device" bug and
  per-device Zotero profile divergence. Root cause was NOT a missing DB-file
  sync (§13.1 JSONL autosync already ships row-level LWW): every export
  trigger was opt-in, and on the CLI-primary linux device (plugin
  `incuratorEnabled: false`) none ever fired, so peers converged on a stale
  Jun-30 5-source snapshot. Now `auto_sync.enabled` defaults on and the export
  hook runs after `add`/`build`/`sync`/`update`/`jobs run` (LWW-gated);
  `db autosync --dry-run` reports `would_export`. Zotero profiles moved from
  `data.json` to synced `.curator/zotero_profiles.json` with automatic legacy
  migration. Plan `06_cross_device_state_sync.md` (deleted; see git history —
  documents the P1 pivot away from raw `state.sqlite` file sync, which would
  have fought the shipped LWW transport).
- **v0.29.1 — Side Chat Sidebar Regression Hotfix** (shipped 2026-07-02, PR #77):
  Fixed five interacting regressions introduced by v0.29.0 portable-path storage
  that collectively caused the chat sidebar to render blank on startup:
  `isRetainablePersistedDoc` now retains path-only docs; `persistDocs` preserves
  path for local-only PDFs so they survive across restarts; `loadPersistedDocs`
  restores path into the in-memory registry; `syncState()` passes runtime path
  through `buildSyncedExternalPdfState`; `getLeafFile()` uses `getRuntimePath()`
  for external PDF views; `renderContextChips()` guards all 21 call sites via an
  internal try/catch.
- **v0.29.0 — Portable Path Storage** (completed 2026-07-02): schema v10 removes
  persisted absolute source paths. Vault locators are relative, Zotero persists
  only `zotero:<effective_attachment_key>` and resolves through the current
  backend/Zotero DB, and generic external files use
  `@<root_key>/<relative-path>` with machine-local roots confined to repo
  `.cache/config/`. Migrated and audited production `second_brain`, sanitized
  plugin localStorage/view/session/settings persistence, and validated Reference
  Mode in the `gaussian_splatting` testbed.
- **v0.28.5 — Runtime Path Snapshots & Stale Fallback Removal** (shipped 2026-07-01, PR #75): deployed 0.28.5 build to `second_brain` vault plugin. Removed stale Anaconda/conda PATH fallback from `resolveBackendCommand`; plugin now auto-discovers `.venv/bin/wiki` via repo path only. Added runtime path snapshot tracking to `runtime_state`. Docs updated (PLUGIN_GUIDE, SYNC_IGNORE_GUIDE, SCHEMA, PLUGIN_SCHEMA). Extended test coverage for runtime_state and device_registry.
- **v0.27.2 — L2 Extraction Hardening + Checkpoint-Resume** (shipped 2026-06-27,
  PRs #59/#60/#61): root-caused the large-source L2 failure. Closed unclosed
  prompt traces on provider exceptions (guarded `finish_prompt_run` so a DB write
  failure can't mask the original provider error), added the missing `except`
  clause to `curator_explore`/`curator_backprop_correct` MCP handlers, real CLI
  chunk-budget fallback, and fail-fast after terminal L2 batch errors. Added
  checkpoint-resume: each completed L2 batch is recorded in a new `l2_checkpoints`
  table keyed by `(span_id, section_title)` content hash, so a 429 mid-run on a
  277-batch PDF resumes from the last finished batch instead of restarting from
  batch 1 and re-burning quota. `compile_source_l2` auto-detects resume via
  `db.has_l2_checkpoints()` (immune to callers that reset `l2_status` before
  dispatch). Production follow-up: source #27 still needs one clean retry run.
- **v0.25.1 — User Report Stability Bug Batch** (completed 2026-06-25): fixed
  the 14 urgent reports triaged from `.agents/USER_REPORT.md`: source-file
  deletion safety, layer-error retry, queued job rerun UX, VLM temp-path
  leakage, generated L2 English enforcement, malformed generated wikilinks,
  registered source badge state, popover LaTeX copy, Convert-to-LaTeX
  output-only transcription, bare PDF equation lookup, generated vault block
  links, Add Resource/L4 status clarity, PDF scroll jank, and multiple
  independent quick-query popovers.
- **v0.25.0 — Backend/Plugin Config Isolation + Dashboard Live-Read** (shipped
  2026-06-23, commit `b9a49a1`, unpushed): vault config renamed
  `.curator/config.yml` → `.curator/settings.yml` to end the name collision with
  the per-device backend `<repo>/.cache/config/config.yml` (per-device keys +
  devices.json stay out of the synced `.curator/`). Fixed the dashboard ↔
  `wiki status` desync (the "Apply reverts after Jobs" bug — `config set --global`
  wrote settings.yml while the loader read config.yml), plus the LLM-Apply
  read-gate, missing post-mutation refresh on LLM/Persona, and a model-load timer
  leak. New `wiki status --json` live payload: the dashboard reads ALL backend
  info live from it (one cached CLI call/render) instead of a stale-prone snapshot
  file; the runtime snapshot stays at `.curator/runtime/` (device-local) purely as
  a chat-status-bar cache.
- **v0.24.0 — Diff Viewer Multi-Model Robustness** (shipped 2026-06-22): the
  `ai-agent-edit` → Diff Viewer flow now works across model tiers. The four-phase
  review loop was demoted from a hard gate to a hint (a valid SEARCH/REPLACE is always
  reviewable, even when a weak/token-limited model skips the `[[PHASE:…]]` markers);
  output-token truncation (Gemini `MAX_TOKENS`, OpenAI/Ollama `length`, Claude
  `max_tokens`) is detected via `StreamChunk.finishReason`/`truncated` and auto-continued
  (≤3, fence-safe overlap stitch, no premature finalization, manual Continue fallback);
  the Diff Viewer keyboard shortcuts are focus-gated (chat-Enter no longer Accept-Alls)
  with `show()` focusing the editor and returning a typed `{opened,reason}`; multi-edit
  proposals match against the original text (order-independent) with same-file review
  coalesce.
- **v0.23.0 — CLI Provider Tool-Scope Sandbox** (shipped 2026-06-22): closed the
  CLI-native-tool escape the v0.19.0 MCP isolation left open. `toolPolicy` now reaches
  the CLI command builder — popover runs tool-free, sidechat scopes tools to the
  allowed roots (vault + Zotero); dropped `agy --dangerously-skip-permissions`. agy's
  own `--sandbox` proved ineffective (P0 created files), so every CLI subprocess is
  wrapped in an OS sandbox (macOS `sandbox-exec`, Linux `bwrap`; Windows out of scope).
- **v0.22.0 — PDF Vision Extraction + Chat Decay & Quick Wins** (shipped 2026-06-21,
  one combined release on `feature/chat-decay-quick-wins`): dedicated PDF-extraction
  vision models (`llm.vision_model` always-on `add source` page-VLM → LaTeX L1,
  `latex_extract_model` light slot; CLI-subscription cloud vision, no API keys;
  Dashboard rows); plus localized-question edit-affordance suppression (`Cmd+Shift+L`)
  and Zotero import-profile recent-first ordering. (The unreleased v0.21.0 `latexModel`
  was reshaped into the vision slots — never shipped standalone.)

*(All previous milestones up to v0.20.0 have been successfully shipped and archived in the Git history. No active follow-ups remain.)*

---

## 🧊 Blocked / Icebox

No blocked items currently tracked.

---

## 📌 Current Focus & Active Milestone

- **Roadmap state**: System IDLE. No active milestone.
- **Active Milestone**: None.
- **Next actionable item**: triage `.agents/USER_REPORT.md` when new items arrive.
