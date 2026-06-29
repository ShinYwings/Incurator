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

### 🚨 URGENT HOTFIX QUEUE

_(empty — L2 extraction hotfix shipped in v0.27.2, see Completed Milestones.)_

### 🚀 Priority Order

1. **[Major Update] System Stability Overhaul — Exhaustive Diagnosis & Refactoring** *(ACTIVE)*
   - Absorbs the prompt-architecture milestone. Whole-codebase diagnosis (bugs,
     redundancy, architectural debt) + refactoring with architectural redesign
     allowed; prompt-v2 for cross-model output consistency; legacy/dead-code sweep.
   - Master Plan: `.agents/plans/01_system_stability_overhaul.md`
   - Briefing: `.agents/plans/system_stability_overhaul_arena/00_problem.md`
   - Delivered as a chain of minor-release PRs (0.25.0 → 0.26.0 → …).
   - Shipped so far: G17/G18/G19 (v0.27.3), G17 S3 (v0.27.4), **XC-1 error-handling
     slice 1 (data-pipeline, v0.27.5, PR #64)**, XC-1/XC-4 robustness
     slice 2 (model setup + plugin logging/timer audit, v0.27.6), DB-2 slices
     1–2 (v0.27.7–v0.27.8), G07-12 CLI best-effort warning visibility
     (v0.28.1), and G08-5 plugin source-register warning visibility (v0.28.2).
     Remaining S2: god-file decomposition CM-1/PL-1/DB-2; XC-1 slices 2+ (god-file
     excepts in cli.py/mcp_server.py/plugin_api.py, `model_setup.py`); XC-4 plugin
     timers/logging.

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

7. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

8. **[Minor Update] Web Search Integration**
   - Design and integrate web search capabilities for local models (Ollama, Deepseek, etc.).
   - Investigate API options (Brave, SerpAPI) and implement `web_search.py`.
   - Detailed analysis: `.agents/drafts/minor_quick_wins.md` (Web Search Section)

---

## ✅ Completed Milestones

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

- **Roadmap state**: v0.27.2 L2 hotfix shipped (PR #61 merged). Urgent hotfix
  queue is clear. System Stability Phase B is in progress.
- **Active Milestone**: System Stability Overhaul — Exhaustive Diagnosis &
  Refactoring.
- **Phase A diagnosis state**: ✅ COMPLETE (2026-06-27). All 19 groups (G01–G19)
  diagnosed; findings merged into `01_roadmap_evidence.md`. Tally: **10 S1, 118
  S2, 97 S3**.
- **Phase B status**: S1 queue verified complete in the 0.25.4–0.25.8 release
  chain. Current branch `fix/plugin-api-best-effort-warnings` handles G08-5:
  plugin source registration now returns warnings for skipped non-fatal
  search-index refreshes instead of swallowing them. Version bumped to v0.28.2.
- **Next actionable item**: after v0.28.2 ships, continue remaining S2 groups
  (XC-1 broad-except narrowing in MCP/plugin API surfaces, CM-1/PL-1 god-file
  decomposition) or remaining G17 S3 cleanup.
