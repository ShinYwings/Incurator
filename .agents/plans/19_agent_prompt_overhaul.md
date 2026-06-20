# v0.19.0 Master Implementation Plan — Agent Prompt Architecture & Context Overhaul

Date: 2026-06-20
Status: AWAITING USER APPROVAL — Arena debate concluded (see
`agent_prompt_overhaul_arena/`). Specs to be authored spec-first in P1. No code
until approved.

## 1. Objective
Unify the plugin's fragmented prompt construction into one composable registry
shared by the chat sidebar and the Quick Query popover, hard-isolate the
popover from MCP tools, and add an end-of-payload recency anchor so localized
context (`Cmd+Shift+L`) is honored in long sessions.

**Definition of done:**
1. A single `promptRegistry.ts` supplies the shared boundary/format/language/math
   blocks; `systemPrompt.ts` (sidechat) and `quickQueryContext.ts` (popover) both
   consume it. No "no filesystem access" / boundary literal is declared twice.
2. The popover path passes **zero** tools: a unit test spies `mcpManager.getAllTools`
   and asserts it is never called when `toolPolicy: "none"`, for both
   mcp-present and mcp-absent cases.
3. A recency-anchor block is appended LAST on each surface, gated by `allowEdits`
   and `toolPolicy`, pointer-rule-aware; a long-context fixture test shows a
   primary-selection turn does not emit a whole-file `ai-agent-edit`.
4. Sidechat prompt output is unchanged (golden-master byte-equality); the edit
   loop, language bridge, and incurator MCP addendum are preserved.

## 2. Explicit Non-Goals
- **No "mathematically proven" filesystem sandbox over external MCP servers.**
  The plugin cannot enforce path limits inside a third-party MCP process. We
  guarantee popover-zero-tools + prompt-declared boundaries only. (red_team V1.)
- No aggressive stale-context truncation / token-meter — that is roadmap item 4
  (Chat Session Context Compaction). This plan only adds the recency anchor.
- No DB schema change, no migration, no backend logic change.
- No change to the popover's role: it stays a read-only reading assistant; it
  will NOT run `curator_query`/RAG by design.
- Deferred Diff Viewer polish (#5 gutter CSS, #8 determinism, #10 token-reject)
  is tracked under roadmap item 2 but is OUT of this prompt-architecture plan
  unless trivially adjacent; revisit as a separate follow-up.

## 3. Strict Quality Conditions & Release Gates
- `npx vitest run -c ./plugin/vitest.config.ts` — 100% pass, incl. new
  `promptRegistry.test.ts` and updated `systemPrompt.test.ts` /
  `quickQueryContext.test.ts` / `llmClient.test.ts`.
- Golden-master: sidechat `buildBaseSystemPrompt` output is byte-identical to the
  pre-refactor snapshot for every flag combination.
- Popover boundary: substring-assert the strengthened "no tools / no filesystem"
  phrase is present (NOT frozen blob — red_team V3).
- Tool gate: `getAllTools` spy asserts 0 calls on popover path (red_team V5).
- `scripts/backend-check pytest` green, including `test_spec_sync.py` after the
  spec-title bump to `v0.19`.
- `ruff` + `mypy` clean (no backend logic changes, but spec-sync test runs).

## 4. Locked Design Decisions (Arena Consensus)
1. **New module** `plugin/src/context/promptRegistry.ts` holds pure block
   functions (`persona`, `mathRules`, `languageRules`, `editFormatRules`,
   `boundaryConstraints(profile)`, `incuratorMcp`, `planMode`, `editLoopContract`
   re-export, `buildRecencyAnchor`).
2. **`SurfaceProfile`** = `{ surface, toolPolicy: "auto"|"none", allowEdits,
   hasExternalIncuratorMcp, planMode }`. Sidechat = auto/edits-on; popover =
   none/edits-off.
3. **Behavior-preserving refactor**: `buildBaseSystemPrompt` re-implemented as a
   composition that reproduces today's exact text; popover keeps its persona but
   sources its boundary line from the registry (intentionally strengthened).
4. **Recency anchor** = a SEPARATE trailing block (outside
   `<original_user_request>`), gated by `allowEdits`/`toolPolicy`, deferring to
   the existing pointer / `<resolved_cross_references>` rule (red_team V2,
   specialist R3).
5. **Tool gate**: `streamChat(messages, onChunk, opts?: { toolPolicy?: "auto"|"none" })`.
   `"none"` and the existing `shouldUseCli`/no-`mcpManager` early return MUST
   funnel into the SAME single-turn execution (red_team V4). Default `"auto"`
   keeps the sidechat caller untouched.
6. **Anti-duplication guard test** asserts `quickQueryContext.ts` imports the
   boundary text from the registry (specialist S2).
7. **Spec-line sync**: bump all four `docs/specs/*` titles to `v0.19`; primary
   contract edits in `PLUGIN_SCHEMA.md` (specialist S1).

## 5. Scope Exclusions & Stop Conditions
- **Exclusions**: external-MCP path enforcement; context compaction/token meter;
  Diff Viewer polish backlog. All deferred to their own roadmap items.
- **Stop conditions** (halt and ask the user):
  - If golden-master shows the sidechat text MUST change to satisfy a fix
    (i.e. behavior-preservation and a bug fix conflict) — get a ruling.
  - If removing tools from the popover breaks an intended popover capability the
    user actually wants (e.g. they DO want `curator_query` in popover).
  - If `test_spec_sync.py` reveals a manifest/version disagreement pre-existing
    on the branch.

## 6. Evidence Ledger
See `19_roadmap_evidence.md` (rollback anchor, schema reality, dirty worktree).

## 7. Execution Phases (TDD + CI at each phase)
- **P0 — Baseline & golden master**: capture current `buildBaseSystemPrompt` and
  `buildQuickQueryMessages` outputs into snapshot fixtures; add the long-context
  decay fixture (reproduces F1). Verify: snapshots committed, decay fixture
  currently FAILS the desired assertion (red test).
- **P1 — Contract spec (docs-first, STOP for approval if contract shifts)**:
  write the prompt-registry + `streamChat` tool-policy contract into
  `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`; bump all four spec titles to
  `v0.19`; update `docs/guides/PLUGIN_GUIDE.md` (+ `_KR.md`) with the popover
  zero-tools boundary and the external-MCP caveat. Verify: `test_spec_sync.py`
  green.
- **P2 — Registry module**: implement `promptRegistry.ts` + `promptRegistry.test.ts`.
  Verify: vitest green; blocks pure.
- **P3 — Sidechat re-route (behavior-preserving)**: re-implement
  `buildBaseSystemPrompt` over the registry. Verify: golden-master byte-equal.
- **P4 — Popover unify + tool gate**: route `quickQueryContext.ts` boundary
  through the registry; add `toolPolicy` to `streamChat`; popover passes
  `"none"`; append recency anchor on both surfaces. Verify: getAllTools spy = 0
  on popover; decay fixture now PASSES (no whole-file edit); anti-duplication
  guard green.
- **P5 — Testbed smoke**: `VAULT_ROOT=testbed wiki status`; manual/automated
  popover + sidechat sanity (no script-execution on popover; Cmd+Shift+L honored;
  sidechat edit loop intact). Document any LLM-availability blocker.

> LIFECYCLE: on green CI → bump to **0.19.0** across `pyproject.toml`,
> `package.json`, `manifest.json` + `CHANGELOG.md`; delete plan artifacts;
> `chore(release): v0.19.0`; push + PR per Universal Strict Workflow.
