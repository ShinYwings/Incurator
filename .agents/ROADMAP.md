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

The user's 2026-07-30 stability-review follow-up is triaged below. Draft PR
#101 remains unmerged; confirmed v0.39.0 authored-topology blockers stay on that
release branch, while pre-existing cross-system defects and any additional
v0.32.0+ regression findings ship as small follow-up patch releases.

### 🚀 Priority Order

1. **[Patch-in-release] v0.39.0 Authored-Topology Review-Blocker Closure** *(MERGE READY)*
   - Draft PR #101 remains on `release/v0.39.0`; the release has not merged, so
     authored-topology corrections keep the same version and public contract.
   - Close the newly confirmed single-generation tombstone hole, exact audit
     membership enforcement, strictly-monotonic repair/retirement clocks,
     winner-report invalidation, nested Markdown labels, and single-decode
     target normalization.
   - Preserve the already-green first hardening pass from commit `f6ff089`;
     every new failure receives a red regression test before code.
   - Seven direct review findings plus a reconciliation-quiescence guard are
     implemented, fully validated, pushed, and green on latest-head PR CI.

2. **[Patch Chain] v0.39.x Stability Regression Audit — v0.32.0 Through Current** *(ACTIVE — PLAN FIRST)*
   - Audit every merged release diff from PR #80 / v0.32.0 through PR #100 /
     v0.38.0 plus the current PR #101 branch. Cross-check the original release
     plan, implementation diff, tests, specs/guides, and adjacent failure
     transitions rather than re-reading only the final happy path.
   - Confirmed starting queue: complete source-deletion closure; post-publish
     compiler recovery; explicit vector-query degradation; provider/CLI abort
     and model dispatch parity; MCP name mapping and shutdown settlement;
     bounded backend subprocesses; fail-closed/atomic session and secret
     persistence; runtime-secret redaction; embedding/reranker cardinality;
     prompt failover attribution and numeric version ordering.
   - Deliver fixes as independently reviewable patch releases by integrity
     boundary. Do not place all cross-system work into PR #101. No schema change
     is currently expected; stop and re-plan as a Minor if the audit proves one
     necessary.

3. **[Major Update] System Stability Overhaul — Exhaustive Diagnosis & Refactoring** *(ACTIVE)*
   - Absorbs the prompt-architecture milestone. Whole-codebase diagnosis (bugs,
     redundancy, architectural debt) + refactoring with architectural redesign
     allowed; prompt-v2 for cross-model output consistency; legacy/dead-code sweep.
   - Master Plan: `.agents/plans/01_system_stability_overhaul.md`
   - Briefing: `.agents/plans/system_stability_overhaul_arena/00_problem.md`
   - Delivered as a chain of independently reviewable release PRs.
   - **Shipped stability & hardening releases (v0.25.0 → v0.39.0)**:
     diagnosis G17–G19, XC-1/XC-4 robustness slices, DB-2 slices 1–2,
     CLI/MCP warning visibility, portable paths and cross-device LWW sync,
     strict v12 schema/reindex speedup, CM-1 command decomposition,
     fail-closed sync/KRS integrity, PDF/Antigravity transport hotfixes,
     grounded Sidechat vault links, and authored-note graph topology.
   - **Remaining Scope for Upcoming Releases**:
     - **Source-Deletion Closure**: separately plan and repair the pre-existing
       extracted-data deletion path so source removal cannot leave active
       generations, knowledge units, graph support, or serving artifacts.
       This is broader than F9 authored-topology hardening and must not be
       smuggled into PR #101 without its own evidence and plan.
     - **Exception Handling Hardening (XC-1 later slices)**: audit broad
       catch-and-return boundary handlers and other backend modules after the
       silent-swallow slice lands. Provider follow-ups found during v0.37.1
       planning are cancellation trace finalization, trace-storage outage
       recovery, malformed provider-wire payloads, post-failover prompt-provider
       attribution, Antigravity early-failure temp-log cleanup, and generic
       no-JSON plugin command errors.
     - **Performance & UX Refinements**: RAG/DAG benchmark harness & retrieval hotspot optimization; chat/popover UX friction cleanup.

4. **[Minor Update] Chat Session Context Compaction**
   - Confirm full-session history behavior.
   - Add a Claude-Code-style circular token usage meter under the query box and a click-to-compact action.
   - Detailed analysis: `.agents/drafts/chat_context_compaction.md`

5. **[Minor Update] Vault Storage Governance & Quota Visibility**
   - Separate authoritative, derived, cache, and external storage accounting.
   - Add capacity guidance, safe admission control, and CLI/plugin visibility.
   - Detailed analysis: `.agents/drafts/vault_storage_governance.md`

6. **[Major Update] Native PDF Annotation & Asset System**
   - Native annotation highlight/memo synchronization using Obsidian's built-in PDF viewer.
   - In-PDF full-text search and strict-spelling mode remain here.
   - Detailed analysis: `.agents/drafts/pdf_annotation_system.md`

7. **[Minor Update] Web Search Integration**
   - Design and integrate web search capabilities for local models (Ollama, Deepseek, etc.).
   - Investigate API options (Brave, SerpAPI) and implement `web_search.py`.
   - The former quick-wins draft was deleted after triage; create a fresh
     provider/privacy/cost plan from current APIs before implementation.

---

## ✅ Completed Milestones

- **v0.38.0 — Sidechat Vault-Page Wikilinks**
  (shipped 2026-07-30, PR #100): every selectable Sidechat provider receives the
  same exact-path/non-invention contract and completed `vault_link_target`
  literals for safe included Markdown/PDF context and usable ContextService
  locators. External, degraded, unsafe, or source-kind/suffix-mismatched targets
  fail closed; ordinary links remain owned by Obsidian's native renderer.
  Antigravity and local Ollama produced grounded links, real heading/block
  navigation succeeded, all 737 plugin tests and 1,325 backend tests passed,
  static analysis/build/spec-sync passed, and `npm audit` found zero
  vulnerabilities.

- **v0.37.1 — Query Provider Failure UX**
  (shipped 2026-07-30, PR #99 merged): Ollama, Claude, Codex, and failover paths now
  normalize blank/non-zero provider results through the existing `LLMError`
  boundary. Failed synthesis retains QTR/PTR/evidence diagnostics, CLI exits
  non-zero without a Rich traceback, and CLI/MCP/hidden-plugin/plugin UI
  surfaces share the existing failure meaning. Backend 1,325-test, plugin
  725-test, Ruff, Mypy, production build, zero-vulnerability npm audit,
  ResNet testbed lint 100/100, and authenticated Antigravity query gates passed.

- **v0.37.0 — Composite-Primary-Key Tombstone Convergence**
  (shipped 2026-07-30, PR #98 merged): schema v13 adds a closed canonical-JSON transport
  identity for all six synchronized composite-key tables, using portable source
  keys instead of replica-local ids. Full-key deletes, delete/update LWW,
  fail-closed malformed-token handling, transactional source cleanup, local
  delete/reinsert emission, multi-peer convergence, and first-import dry-run
  parity are locked by tests. Backend 1,303-test, plugin 721-test, static
  analysis, production build, ResNet autosync quiescence, and lint 100/100
  gates passed.

- **Plugin npm audit PostCSS dependency chore** (completed 2026-07-30):
  updated only the Vite transitive lockfile resolution from
  `postcss@8.5.15` to patched `8.5.25` and its required Nano ID patch. A clean
  `npm ci` reproduced the lockfile; `npm audit` reported zero vulnerabilities,
  all 721 plugin tests passed, and the production build succeeded.

- **v0.36.8 — PDF Convert-to-LaTeX Antigravity Prompt Transport**
  (release-ready 2026-07-30): fixed the backend Antigravity client to pass the
  complete request as the `agy --print` prompt and exact `--model`. Explicit
  Convert-to-LaTeX slots use `low` only when supported; fixed variants omit
  effort. The plugin chat selector now reaches `agy --model`, and the catalogue
  uses the live `claude-opus-4-6-thinking` slug. The reported scratch-workspace
  planning narration was reproduced before the fix; all five Antigravity vision
  models and Codex Terra returned selected prose with LaTeX. Backend 1,276-test,
  plugin 721-test, static-analysis, production build, testbed lint 100/100, and
  live transcription gates passed.

- **v0.36.7 — Obsidian Agent Activation + Open-Tab Context Hotfix**
  (release-ready 2026-07-26): provider launch now fails closed when Obsidian is
  still running a stale plugin bundle; complete plugin updates lead to a real
  renderer reload. The purple context row inventories materialized leaves plus
  deferred pop-out tabs from the public workspace layout, while hidden tabs
  remain eye-off and outside prompts. Full backend 1270-test, plugin 721-test,
  static-analysis, build, testbed lint 100/100, four-chip live UI, and two live
  Antigravity PDF-query gates passed.

- **v0.36.6 — Purple Pin Zotero Source Registration Hotfix**
  (release-ready 2026-07-23): Purple Pin Add source now preserves the explicit
  Zotero attachment key as portable identity when a resolved local PDF path is
  supplied on macOS or Linux. Generic unregistered external paths remain
  blocked. Backend 1270-test, plugin 704-test, static-analysis, production
  build, real-path dry-run, and testbed lint gates passed.

- **v0.36.5 — Zotero Import Case-Collision Refresh Hotfix**
  (release-ready 2026-07-22): an explicit Zotero re-import now refreshes the
  case-insensitive existing note after `EEXIST`, preserving its filename and
  persisted template content while replacing stale Zotero metadata and keys.
  Non-collision filesystem errors remain visible.

- **v0.36.4 — Antigravity Headless PDF Compatibility Hotfix**
  (release-ready 2026-07-22): migrated headless `read_file` approval to the live
  Antigravity CLI settings with lossless atomic merging, safely retired the
  ineffective v0.36.3 TOML artifact, and forwarded required `--effort` values
  for Gemini 3.6 Flash base slugs. Backend 1268-test, plugin 699-test, static
  analysis, production build, testbed lint 100/100, and a real iCloud Zotero PDF
  read through `agy -p` passed.

- **v0.36.2 — XC-1 Fail-Closed Correctness Hardening**
  (shipped 2026-07-20, PR #90 merged): preserved corrupt device-local sync state instead
  of regenerating identity, surfaced peer/conflict/archive failures, made
  tombstone deletion transactional, and prevented existing invalid KRS files
  from widening query scope or persisting curation plans. Backend 1268-test,
  plugin 689-test, static-analysis, production build, version/docs consistency,
  Gaussian Splatting Reference Mode, lint 100/100, and repeated quiescent
  autosync gates passed. External Antigravity answer synthesis returned no
  output; the resulting traceback UX is queued separately. PR self-review then
  fixed `wiki query --workspace` dropping its KRS path, made invalid policy fail
  before provider startup, and removed undocumented pending-source ingestion.
- **v0.36.1 — XC-1 Silent Exception And False-Success Hardening**
  (release-ready 2026-07-19): eliminated 28 silent broad handlers across the
  decomposed CLI/MCP/plugin API packages; fixed empty-build false success,
  surfaced degraded search refreshes, restored packaged provider model loading,
  and reconciled MCP/runtime snapshot documentation. Backend 1225-test, plugin
  688-test, static-analysis, build, Gaussian Splatting, and consecutive
  zero-change autosync gates passed.
- **v0.36.0 — PL-1 Plugin God-file Decomposition** (release-ready 2026-07-19):
  moved the chat sidebar, LLM client, and external PDF view implementations into
  dedicated internal packages while preserving stable public facades, class and
  view identities, persistence, provider behavior, and UI flows. Corrected the
  EN/KR External PDF restoration docs. Backend 1218-test, plugin 683-test,
  static-analysis, build, and Gaussian Splatting testbed gates passed; a real
  autosync followed by dry-run confirmed no pending Knowledge Sync re-export.
- **v0.35.0 — Claude/Codex Model Catalogue Refresh** (shipped 2026-07-19,
  PR #87): updated the shared catalogue to Claude Sonnet 4.6, Fable 5,
  Opus 4.8, Haiku 4.5 and Codex GPT-5.6 Sol/Terra/Luna plus GPT-5.5; unified
  model-specific effort normalization across settings, sidebar, dashboard, and
  stored-setting migration; omitted effort flags for no-effort models; restored
  Claude text/image effort parity; synchronized EN/KR guides and static specs.
  Full backend, plugin, build, version-consistency, and Gaussian Splatting
  Reference Mode testbed validation passed.
- **v0.34.1 — Knowledge Sync Loop Hotfix** (release-ready 2026-07-19): made
  composite/immutable full-snapshot imports content-idempotent, made autosync
  dry-run honor peer export-id high-water state, and filtered the plugin's known
  self snapshot from incoming-file watcher triggers. Production before/after
  dry-run moved from `updated=6650` / `would_export=true` to zero imports and
  `would_export=false`; backend, plugin, build, and Gaussian Splatting testbed
  validation passed.
- **v0.34.0 — CM-1 Command Module God-file Decomposition** (shipped 2026-07-09, PR #85 merged): decomposed `cli.py`, `mcp_server.py`, and `plugin_api.py` into cohesive packages (`curator/commands/`, etc.) with compatibility facades preserved.
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

- **Roadmap state**: System Stability Overhaul ACTIVE; v0.39.0 is unmerged.
- **Active Milestone**: v0.39.0 authored-topology review-blocker closure plus
  the v0.32.0+ release-chain regression audit.
- **Next actionable item**: merge PR #101, fast-forward `master`, then begin P5
  source-lifecycle/compiler-recovery work from the clean merged anchor.
