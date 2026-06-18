# Cross-Agent Relay State

## Goal
Batch 3 / Plan F — Unified Agent Context Service on `feature/agent-context-service`.

## Plan Reference
- Active plan: `.agents/plans/F_agent_context_service.md`
- Current phase: P6 — Obsidian Agent Grounding And Sources & Trace

## Analysis & Reasoning
- P1 target contracts were added without bumping release versions yet. Spec
  headers remain on v0.11.0 because `backend/tests/test_spec_sync.py` pins the
  active release line; Plan F contracts are documented as "Plan F target,
  v0.12.0" sections.
- P2 landed `backend/src/curator/context_service.py`; `ContextService` now owns
  root `QTR-*`, deterministic `SNAP-*`, ordered `CTXA-*` child actions,
  `PACK-*`, and typed `snapshot_conflict`. `QueryOrchestrator.fetch_context`
  delegates to it while preserving additive legacy fields.
- P3 hardening has started. `ContextService.context_fetch` now selects a
  budget-bounded pack, records explicit budget omissions, exposes `next`
  expansion handles for omitted items, resolves locators for source-supported
  generated records from backing source spans, and rewrites the stored `QTR-*`
  trace to match the selected response pack.
- Backend validation no longer uses `export VIRTUAL_ENV` or
  `uv run --directory backend --active`. The canonical backend command path is
  `scripts/backend-check`, which calls repo-root `.venv-dev/bin` directly and
  pins mypy stubs/cache without creating backend-local artifacts.

## Progress Status
- Completed P1 docs updates across specs and EN/KR guides.
- Completed P2 service boundary and orchestrator delegation.
- Added `scripts/backend-check` and updated CI, PR template, AGENTS/CLAUDE,
  EN/KR agent workflow and contribution guides, Failure Atlas command
  references, research-spike manifests, and active Plan F evidence.
- Extended `backend/tests/test_workspace_hygiene.py` to forbid `backend/uv.lock`,
  require the backend helper, and reject reintroduced active-uv/export
  validation examples in canonical agent/guide files.
- Extended `backend/tests/test_plan_f_context_service_contract.py` with P3
  contract tests for locator resolution, explicit budget omissions,
  trace/response selected-pack parity, deterministic pack order, and
  formula/code/citation boundary preservation.
- Added route-specific P3 tests for global route retrieval omissions
  (`global_reports`) plus ContextService budget omissions, and source-section
  budget truncation without mixing omitted spans back into response or trace
  provenance.
- Fixed `backend/src/curator/retrieval/evidence.py` so `_span_items()` restores
  caller `span_ids` order after fetching spans with `WHERE id IN (...)`.
- Started and completed the P4 service-boundary slice:
  `ContextService.context_manifest`, `context_expand`, and `context_verify`
  now exist; expansion and verification reuse the root `QTR-*`, enforce stored
  `SNAP-*`, and append ordered `CTXA-*` child actions only on successful
  operations.
- Added P4 fixtures for manifest, successful expand, and verify under
  `docs/specs/system_behavior/context_service_fixtures/`, and updated the
  schema fixture registry text.
- Started P5 public adapter parity. `backend/tests/test_mcp_tools.py` now
  requires `curator_fetch_context` to expose the normalized ContextService pack
  shape and verifies that the returned root `QTR-*` trace contains the same
  `retrieval_trace.context_service.pack_id` and snapshot id as the public
  response.
- Refactored non-explore `QueryOrchestrator.run` so `curator_query`/`wiki query`
  first obtains the exact ContextService pack, synthesizes over that selected
  pack, and appends the prompt run as a `synthesis` child action on the same
  root `QTR-*`. Explore mode remains on the existing explore pipeline.
- Migrated MCP `curator_query` L3-complete path to `QueryOrchestrator.run`,
  preserving legacy `ok`/`answer`/`question`/`trace` fields while adding Plan F
  trace metadata (`pack_id`, `snapshot`, `budget`, `source_span_ids`,
  `prompt_trace_ids`). L3-incomplete degraded fallback remains unchanged.
- Updated `SYSTEM_BEHAVIOR.md` and EN/KR MCP guides for the additive
  `curator_query` trace fields.
- Completed P5 adapter parity tightening: plugin API and hidden
  `wiki plugin query` JSON now have tests proving result-level/nested trace
  `pack_id`, `snapshot`, `budget`, and prompt trace parity against the stored
  root `QTR-*`.
- Started P6 and completed the first provider-grounding slice:
  hidden `wiki plugin context fetch` returns a normalized ContextService pack
  without synthesis; `IncuratorClient.fetchContext()` consumes it; sidechat now
  uses `client.fetchContext()` + `formatCuratorContextPack()` for ordinary
  provider grounding instead of injecting backend synthesized answers by
  default.
- Completed the P6 Sources & Trace exact-pack rendering slice:
  sidechat preserves the fetched pack as `context_pack`, and the trace panel now
  renders exact pack id, snapshot, budget, coverage/degraded state, evidence
  item summaries, truth/freshness state, locators, expansion handles,
  verification handles, and omitted `next[]` expansion handles.
- Completed the P6 locator/action slice:
  Sources & Trace locators are clickable for vault relpaths plus heading/block
  anchors and external URIs; hidden plugin JSON now exposes
  `wiki plugin context expand` and `wiki plugin context verify`;
  `IncuratorClient` has `expandContext()` / `verifyContext()`; the trace panel
  renders `Expand`/`Verify` controls and `chatSidebar` handles
  `context:expand` / `context:verify` events, merging successful expansion
  items back into the displayed `context_pack`.
- Updated plugin schema, system behavior spec, and EN/KR plugin guides for
  hidden context fetch, the no-default-backend-answer rule, and exact-pack
  Sources & Trace rendering plus clickable locator / follow-up operation
  behavior.
- Moved the Batch 1~3 deferred audit items out of `.agents/USER_REPORT.md` and
  into `.agents/ROADMAP.md` under the active Plan F follow-up requirements.
- Did not initialize `testbed/`; active scenario remains unconfirmed and Plan F
  defers destructive `wiki testbed init --force` until P9 or explicit selection.

## Validation
- `scripts/backend-check pytest -q` ->
  `923 passed, 6 skipped, 5 xfailed, 7 warnings`
- `scripts/backend-check ruff` -> passed
- `scripts/backend-check mypy` -> no issues in 95 source files
- `npx tsc --noEmit` from `plugin/` -> passed
- `npx vitest run` from `plugin/` -> `44` files / `379` tests passed
- Workspace hygiene check found no backend-local `.venv`, `.venv-dev`, tool
  cache, or `uv.lock` artifact.

## Critical Context / Blockers
- Items `01`-`03` and `06` from the Batch 1~3 audit are real follow-up risks,
  now tracked in `.agents/ROADMAP.md` instead of `.agents/USER_REPORT.md`.
- P6 snapshot-conflict refetch/rebase UX and compact pack/action control styling
  are now implemented at source-contract level. Browser/Obsidian visual QA is
  still pending.

## Immediate Next Action
Continue P6 TDD:
1. Add registered/unregistered PDF and external Reference Mode context-pack
   cases for Sources & Trace.
2. Run broader browser/Obsidian visual QA for pack/refetch/action controls.
3. Keep explore-mode ContextService migration deferred to the explicit
   follow-up requirement unless the user directs otherwise.

### Update (2026-06-18, Codex)
- Continued P5 public adapter parity by migrating `plugin_api.curator_query` L3-complete path to `QueryOrchestrator.run`.

### Update (2026-06-18, User & Gemini)
- Gemini generated 10 deep audit reports (`.agents/drafts/batch_1_to_3_audit/`).
- The user manually implemented code fixes for the 6 immediate vulnerabilities (`04`, `05`, `07`, `08`, `09`, `10`).
- Gemini ran `scripts/backend-check pytest -q` as an independent verification gate.
- Result: 920 tests passed. The user's fixes are mathematically and structurally sound. The audit remediation is officially cleared.
- System State Machine unpaused and returned to Plan F P5 execution.

### Update (2026-06-18, Codex)
- Cleared the remaining P5 adapter parity hardening:
  `plugin_api.curator_query` L3-complete path is tested to avoid legacy
  `search.query`, preserve one root `QTR-*`, and emit matching
  `pack_id`/`snapshot`/`budget`/prompt trace ids at result and nested trace
  levels. Hidden `wiki plugin query` JSON has the same parity assertions.
- Started P6 with backend/plugin transport for evidence-pack grounding:
  added `wiki plugin context fetch`, `IncuratorClient.fetchContext()`,
  `formatCuratorContextPack()`, and changed sidechat default provider context
  from backend answer injection to ContextService evidence pack injection.
- Updated docs/specs and tests. Validation:
  backend focused suite -> `22 passed`;
  full backend pytest -> `922 passed, 6 skipped, 5 xfailed, 7 warnings`;
  `scripts/backend-check ruff` -> passed;
  `scripts/backend-check mypy` -> no issues in 95 source files;
  `npx tsc --noEmit` -> passed;
  `npx vitest run` -> `44` files / `373` tests passed.

### Update (2026-06-19, Codex)
- Continued P6 Sources & Trace work. The plugin now preserves fetched
  ContextService packs on `CuratorQueryResult.context_pack` and renders the
  exact pack in Sources & Trace: pack id, snapshot id, budget,
  coverage/degraded state, item summaries, truth/freshness state, locators,
  expansion handles, verification handles, and omitted `next[]` handles.
- Added source-contract tests for pack rendering and explicit
  `snapshot_conflict`/degraded-state display.
- Updated plugin schema, system behavior spec, and EN/KR plugin guides for
  `context_pack` and exact-pack panel behavior.
- Validation:
  targeted plugin tests -> `4` files / `56` tests passed;
  `npx tsc --noEmit` -> passed;
  `npx vitest run` -> `44` files / `375` tests passed;
  workspace hygiene check found no backend-local `.venv`, `.venv-dev`, tool
  cache, or `uv.lock` artifact.

### Update (2026-06-19, Codex)
- Continued P6 interaction work. Sources & Trace locators now open vault
  relpaths with heading/block anchors or external URIs. Unavailable locators
  remain inert.
- Added hidden `wiki plugin context expand` and `wiki plugin context verify`,
  plus `IncuratorClient.expandContext()` / `verifyContext()`.
- Added `Expand` / `Verify` controls for pack item handles. The panel dispatches
  `context:expand` / `context:verify`; `chatSidebar` calls the backend,
  merges successful expansion items into `context_pack`, removes consumed
  expansion handles, and re-renders without forcing scroll.
- Updated specs/guides and tests. Validation so far:
  backend focused suite -> `22 passed`;
  targeted backend context plugin commands -> `2 passed`;
  targeted plugin tests -> `3` files / `51` tests passed;
  `npx vitest run` -> `44` files / `379` tests passed;
  `npx tsc --noEmit` -> passed;
  `scripts/backend-check ruff` -> passed;
  `scripts/backend-check mypy` -> no issues in 95 source files;
  full backend pytest -> `923 passed, 6 skipped, 5 xfailed, 7 warnings`.

### Update (2026-06-19, Codex)
- Addressed reviewer provenance/null-trace findings in
  `backend/src/curator/retrieval/orchestrator.py`,
  `backend/src/curator/mcp_server.py`, `backend/src/curator/plugin_api.py`, and
  `backend/src/curator/context_service.py`.
- `_context_evidence_block` now joins every already-budgeted pack item, with no
  secondary 16k character cap, and normalizes null item fields to empty strings.
- ContextService-backed `curator_query` and plugin query trace readers tolerate
  persisted `retrieval_trace_json = null`.
- Successful synthesis now records only validated prompt-output cited
  `source_span_ids` at result/root-trace level. Failed synthesis clears
  result/root answer reference arrays while keeping the retrieved pack under
  `retrieval_trace.context_service.selected_items`; the synthesis child action
  records failed status with empty cited spans.
- Updated `SYSTEM_BEHAVIOR.md` and EN/KR MCP guides for cited-answer provenance
  versus full-pack provenance.
- Validation:
  reviewer-focused tests -> `5 passed`;
  adapter focused suite -> `24 passed`;
  `scripts/backend-check ruff` -> passed;
  `scripts/backend-check mypy` -> no issues in 95 source files;
  full backend pytest -> `926 passed, 6 skipped, 5 xfailed, 7 warnings`;
  `npx tsc --noEmit` from `plugin/` -> passed;
  `npx vitest run -c ./vitest.config.ts` from `plugin/` ->
  `44` files / `379` tests passed;
  `git diff --check` -> passed;
  workspace hygiene found no backend-local `.venv`, `.venv-dev`, tool cache, or
  `uv.lock` artifact.

### Update (2026-06-19, Claude)
- Continued P6 locator slice: registered/unregistered PDF + external Reference
  Mode cases for Sources & Trace. `incuratorQueryTrace.ts` `locatorTarget`/
  `openLocator` now resolve open targets by source kind — external Reference Mode
  sources open the real file (`external_uri`), never the in-vault stub;
  reference PDFs open in the plugin external PDF viewer at the cited page (new
  `openExternalPdfLocator` via `registerExternalPdfByPath` + `EXTERNAL_PDF_VIEW_TYPE`);
  registered/vault PDFs jump via `#page=N`. external_uri branch now evaluated
  before the relpath branch so a non-null stub path can't shadow the real file.
- Added 3 source-string contract tests in `incuratorQueryTraceV031.test.ts`.
- Updated `PLUGIN_SCHEMA.md` and EN/KR plugin guides for the by-source-kind
  locator-open behavior.
- Validation: `npx tsc --noEmit` -> passed; full `npx vitest run` -> 44 files /
  385 tests passed.
- Per user request, audited Reference Mode + "pin PDF as source" paths. Logged a
  6-item bug cluster (1 fixed this session, 5 open) in `.agents/USER_REPORT.md`
  with exact code locations; recommended a plan-first refactor for items 2-6.
- User chose (A) + asked to simplify the 3 PDF flows (reference mode / add source
  / agent↔PDF viewer). Authored full Arena plan set under
  `.agents/plans/G_pdf_unified_handling_arena/` + Master Plan
  `G_pdf_unified_handling.md` + evidence ledger `G_pdf_roadmap_evidence.md`.
- Plan G APPROVED. Branch `feature/pdf-unified-handling` off the Plan F
  checkpoint `3c05f08` (backend P2 depends on Plan F's context_service.py absent
  on master; rebase onto master after Plan F merges). Commits:
  `3c05f08`(F checkpoint) → `e03a976`(G plan) → `cb62ec7`(P0) → `7988393`(P1) →
  `439eabe`(P2) → `b957cce`(rename Pdf*→Asset* + cache-invalidation contract) →
  `2a27e78`(P2 review hardening + D2 fix).
- P0/P1/P2 DONE. P2 = `backend/src/curator/asset_identity.py` (AssetIdentity
  facade) + locator/logical-id routing; reviewer-hardened (stale-path verify,
  isolated logical lookup kept local so frozen D2-pinned db.py is untouched,
  state-leakage guard, untracked is_reference consistency). Full backend 938
  passed/0 failed; ruff+mypy clean.
- NEXT: P3 (plugin AssetSource model + single assetStatusKey + remove any-cast
  Zotero detection + mandatory Zotero cache invalidation + external-image asset
  routing). STOPPED at P3 gate for approval.

### Update (2026-06-19, Codex)
- Continued P6 snapshot-conflict UX. `IncuratorClient` now preserves
  `snapshot_conflict` metadata (`error_type`, expected/current snapshot ids,
  `resolution`) from context expand/verify responses.
- Sources & Trace now renders stale snapshot conflicts with expected/current
  snapshot ids and a **Refetch** control. Expand/verify conflicts mark the
  displayed pack stale instead of merging evidence; refetch re-runs
  `client.fetchContext()` for the original question and replaces the displayed
  `context_pack`, result ids, trace pack id, snapshot, and budget.
- Added trace panel CSS for compact pack rows, action buttons, stale/refetch
  controls, and long id wrapping. Updated plugin schema, system behavior spec,
  and EN/KR plugin guides for the stale/refetch-required UX and no
  mixed-snapshot merge rule.
- Validation:
  targeted plugin tests -> `3` files / `54` tests passed;
  `npx tsc --noEmit` from `plugin/` -> passed;
  full plugin vitest -> `44` files / `382` tests passed;
  `scripts/backend-check ruff` -> passed;
  `scripts/backend-check mypy` -> no issues in 95 source files;
  `scripts/backend-check pytest backend/tests/test_spec_sync.py backend/tests/test_workspace_hygiene.py -q`
  -> `12 passed`;
  `git diff --check` -> passed;
  workspace hygiene found no backend-local `.venv`, `.venv-dev`, tool cache, or
  `uv.lock` artifact.

### Update (2026-06-19, Gemini)
- Scheduled an autonomous Codex execution at 04:21 AM to implement fixes for the PDF architectural flaws identified in the review (`externalPdfView.ts` God Class, `asset_identity.py` State Leakage/Collision) and to resolve the failing test `backend/tests/test_failure_atlas_d2.py::test_d2_holdout_result_is_single_run_frozen_and_fine_grained` (`DeprecationWarning: builtin type swigvarlink has no __module__ attribute`).
