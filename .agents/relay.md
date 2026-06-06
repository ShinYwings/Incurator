# Relay State — user_report items 16/17/18/20 fixed (2026-06-06, Claude Code)

## Latest Session Summary (2026-06-06, Claude Code)

Fixed four user_report To-Do items. Remaining open items: 13, 14, 15, 19.

- **Item 18 (chat auto-scroll)**: `plugin/src/ui/chatSidebar.ts` —
  `renderMessages(forceScroll=true)` now captures scroll position before the
  rebuild; generation-complete path calls `renderMessages(false)` so it only
  follows to the bottom when the reader was already there. New `isNearBottom()`
  helper. Tests: `chatSidebarSource.test.ts`.
- **Item 17 (LaTeX backticks)**: root cause was the system prompt modeling
  `` `$x = 2$` ``. Fixed `systemPrompt.ts` (removed backtick example, added
  explicit "never wrap math in backticks"); `textUtils.normalizeLatexDelimiters`
  now unwraps `` `$...$` `` / `` `$$...$$` `` math spans (keeps non-math like
  `$5 and $10`); Ask AI popover (`quickQueryPopover.ts`) now normalizes before
  render. Tests: `textUtils.test.ts`, `systemPrompt.test.ts`,
  `quickQueryPopover.test.ts`.
- **Item 16 (Zotero duplicate stub)**: image-8 showed `...-EN-2.md` twin.
  `ingest_raw._find_existing_reference_stub` reuses an on-disk stub with a
  matching `logical_source_id` before `_unique_destination` can append `-2`
  (triggers when stub survives but DB row was lost). Test:
  `test_mcp_source_tools.py::...reuses_disk_stub_when_db_row_missing`.
- **Item 20 (code dump in chat)**: streaming only hid from the LAST edit marker;
  earlier blocks leaked raw code. New `textUtils.collapseStreamingEditBlocks`
  cuts from the FIRST marker. Post-stream renders compact Review-Diff pills.
  Tests: `textUtils.test.ts`.
- **Item 20b (persistent diff artifact)**: approved /goal plan
  (`.agents/plans/2026-06-06_edit_diff_artifact.md`) implemented. New pure module
  `plugin/src/context/editArtifact.ts` builds an `agent-diff-artifact` Markdown
  note (unified-diff blocks) written to a fixed `00_System/Agent Diffs/` folder
  (outside `raw_dirs`, never ingested). Gated by new `editArtifactEnabled`
  setting (default ON); idempotent via `ChatMessage.editArtifactPath`. Additive:
  chat shows a `📝 Open diff artifact` pill alongside the existing Review-Diff
  pills. Spec `PLUGIN_SCHEMA_v0.3.2.md` + `PLUGIN_GUIDE.md`/`_KR.md` updated.
  Tests: `editArtifact.test.ts`, `settings.test.ts`, `chatSidebarSource.test.ts`.
  Plugin `tsc`/`vitest` (272 passed)/`build` all green. Testbed verified the
  key backend invariant: a note placed at `00_System/Agent Diffs/...md` is NOT
  ingested — `wiki add` reported "No new or changed files found" and source count
  stayed 2 (test file cleaned up afterward). The chat→artifact creation path runs
  inside Obsidian and cannot be driven headlessly here; it is covered by the
  source-contract + unit tests instead.

Verification: plugin `npx tsc --noEmit` clean, `npx vitest run` 261 passed (37
files). Backend `pytest -k "ingest or reference or source or import or zotero"`
89 passed; the only failures are the pre-existing `pymupdf4llm is not installed`
PDF-parser blocker (3 PDF tests), confirmed failing without my changes too.

Docs updated: `PLUGIN_GUIDE.md`/`_KR.md` (scroll, LaTeX, diff pills),
`USER_GUIDE.md`/`_KR.md` (Zotero reference dedup).

---

# Relay State — synthesis audit implemented; GraphRAG improvements deferred

## Goal

Continue `.agents/user_report.md` in priority order.

Items 1-9 reading-assistant work remains implemented and verified in the dirty
worktree. Items 10-11 now have an approved plan and the first implementation
milestone is complete: a read-only L4/L3/answer audit surface proves how
synthesis/query artifacts connect back to L1 source spans.

The GraphRAG algorithm-upgrade part of item 11 is intentionally deferred until
the audit surface can be used on a richer scenario.

## Plan Reference

- Implemented reading-assistant plan:
  - `.agents/plans/2026-06-06_reading_assistant_crossref_toc.md`
- Approved synthesis/GraphRAG plan:
  - `.agents/plans/2026-06-06_knowledge_synthesis_graphrag_verification.md`
- Research/session log:
  - `.agents/claude_code_session_20260606.md`
- Active report:
  - `.agents/user_report.md`

## Analysis & Reasoning

### Items 10-11 / Knowledge Synthesis And GraphRAG

- The existing DB is already GraphRAG-like:
  `source_spans -> knowledge_units -> graph_entities/graph_relations ->
  community_reports -> synthesis_nodes`, with `query_traces`, `prompt_runs`,
  `memory_paths`, and `insight_candidates`.
- The missing product capability was auditability: there was no single command
  or dashboard view that walked from L4 synthesis or a QTR answer back through
  reports, graph objects, knowledge units, prompt traces, and L1 source spans.
- Implemented the conservative first milestone:
  - do not add Microsoft GraphRAG as a dependency;
  - expose existing DB-native evidence;
  - persist `QTR-` traces from `QueryOrchestrator`;
  - surface read-only synthesis audit JSON through CLI, plugin command, and
    dashboard tab;
  - report missing/stale links as warnings instead of silently hiding them.
- `scripts/dev/complex_math_backprop` remains the right richer validation
  scenario, but it is still stale against current `SYN-` / `04_Synthesis` /
  sessionless `QTR-` semantics.

## Progress Status

- [x] Item 1 — GitHub auth **Sign in / Sign out** toggle.
- [x] Item 2 — per-device repository path via `.curator/devices.json`
      local override.
- [x] Items 3/4/6/7 — PDF cross-reference resolver and ToC/caption grounding.
- [x] Item 5 — quick-query popover clamp/flip/reposition/popout-window support.
- [x] Item 8 — chat-title cleanup and answer-link navigation.
- [x] Reading-assistant hardening — PDF PageLabels for printed-page references.
- [~] Item 9 — web-search preference.
  - No plugin-side web-search implementation found. Target injection should
    reduce provider fallback; provider browsing controls remain separate.
- [x] Items 10-11 — synthesis audit first milestone.
  - Docs/specs updated:
    `SYSTEM_BEHAVIOR_v0.3.2.md`, `SCHEMA_v0.3.2.md`,
    `PLUGIN_SCHEMA_v0.3.2.md`, `USER_GUIDE.md`/`_KR.md`,
    `PLUGIN_GUIDE.md`/`_KR.md`.
  - New backend module:
    `backend/src/curator/inspection/synthesis_audit.py`.
  - New tests:
    `backend/tests/test_synthesis_audit.py`,
    `backend/tests/test_plugin_synthesis_audit.py`.
  - `QueryOrchestrator` now persists durable `QTR-` query traces.
  - New public CLI:
    `wiki inspect synthesis SYN-... [--json]`,
    `wiki inspect report REP-... [--json]`,
    `wiki inspect answer QTR-... [--json]`.
  - New hidden plugin commands:
    `wiki plugin synthesis list --limit N --json`,
    `wiki plugin synthesis show --synthesis-id SYN-... --json`.
  - Plugin client methods:
    `listSynthesisNodes(...)`, `getSynthesisAudit(...)`.
  - Dashboard:
    added read-only **Synthesis** tab backed by backend JSON commands.

## Verification

- Focused backend:
  - `pytest tests/test_synthesis_audit.py tests/test_plugin_synthesis_audit.py tests/test_v031_query_orchestrator.py -q`
  - 12 passed.
- Adjacent backend suites:
  - `pytest tests/test_v031_synthesis.py tests/test_v032_search_db.py tests/test_v032_plugin_clicktouse.py tests/test_plugin_cli.py tests/test_synthesis_audit.py tests/test_plugin_synthesis_audit.py tests/test_v031_query_orchestrator.py -q`
  - 34 passed.
- Full backend:
  - `pytest -q`
  - 427 passed, 3 skipped, 4 failed.
  - The 4 failures are PDF parser tests blocked by missing local dependency:
    `ModuleNotFoundError: No module named 'pymupdf4llm'`.
  - Confirmed with `python -c 'import pymupdf4llm'`.
- Plugin:
  - `npx tsc --noEmit` passed.
  - `npx vitest run` passed: 250 tests, 37 files.
  - `npm run build` passed.
- Testbed:
  - `VAULT_ROOT=testbed wiki status` passed.
  - `VAULT_ROOT=testbed wiki lint` passed, health 100/100.
  - `VAULT_ROOT=testbed wiki plugin synthesis list --limit 5` returned
    `SYN-31681844`.
  - `VAULT_ROOT=testbed wiki inspect synthesis SYN-31681844 --json` returned
    hydrated L4→L1 evidence with report, entities, relations, knowledge unit,
    source span, prompt traces, and dependency warnings.

## Critical Context / Blockers

- Worktree is very dirty from prior intended edits. Do not revert unrelated
  backend/GitHub/dashboard changes.
- Full backend test failures are environmental unless `pymupdf4llm` is installed.
- The new audit command revealed stale dependency warnings in the existing
  testbed synthesis/report rows. This is useful signal, not a command failure.
- The Synthesis dashboard tab is a first cut: list/detail only, read-only.
- GraphRAG algorithm upgrades are still not implemented:
  - no modular community detection;
  - no improved global report selection;
  - no DRIFT-like exploration tree;
  - no `complex_math_backprop` scenario modernization yet.
- **GLOBAL PRIORITY RULE**: Agents must ALWAYS check `.agents/user_report.md` first. If there are unresolved items (like Items 13-20), they must be fixed before proceeding to architectural plans.
- **DO NOT START CODING FOR v0.4.0/v0.5.0/v0.6.0 YET.** The sub-plans (`01_...`, `02_...`, `03_...`) are currently only legacy skeletons.

## Immediate Next Action

1. **Coding Agents**: Check `.agents/user_report.md`. Prioritize and fix the remaining items (e.g., Item 17 LaTeX bug, Item 18 Chat scroll UX, Item 20 Agent Diff formatting).
2. **Planning Agents**: Only if the user report is completely clear, **preprocess the existing plan skeletons** (e.g., `01_v0.4.0_stabilization_plan.md`). You MUST migrate these legacy single-file skeletons into the strict multi-document domain format (`A_*.md`, `B_*.md`, `00_MASTER_IMPLEMENTATION_PLAN.md`) as mandated by `.agents/plans/PLAN_TEMPLATE.md` before any deep research or coding begins.
