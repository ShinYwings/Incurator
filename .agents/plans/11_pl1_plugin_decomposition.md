# v0.35.0 Master Implementation Plan

Date: 2026-07-09
Status: DRAFT - Arena debate concluded; awaiting human approval before implementation.

## 1. Objective

Decompose the plugin god-files `chatSidebar.ts`, `llmClient.ts`, and
`externalPdfView.ts` into cohesive modules while preserving the current Obsidian
plugin behavior, public import paths, view types, provider behavior, session
persistence, PDF state persistence, backend command contracts, and all visible
UI flows.

Definition of done:

- Current facade imports still work:
  - `src/ui/chatSidebar`
  - `src/agent/llmClient`
  - `src/ui/externalPdfView`
- The primary implementation logic lives under:
  - `src/ui/chat/`
  - `src/agent/llm/`
  - `src/ui/pdf/`
- `plugin/main.ts` remains the Obsidian entrypoint and lifecycle coordinator.
- Plugin tests, TypeScript check, plugin build, and required backend/version
  checks pass.

## 2. Explicit Non-Goals

- No UI layout changes.
- No chat/session persistence format changes.
- No backend command string, argument, JSON envelope, or plugin API changes.
- No MCP behavior changes.
- No provider/model behavior changes.
- No new runtime dependency unless explicitly approved.
- No full `main.ts` rewrite in this release.

## 3. Strict Quality Conditions & Release Gates

- Add characterization tests before moving each target module.
- Preserve public exports from the existing file paths.
- Update source-contract tests to assert the new owner modules, never by leaving
  dead strings/comments in facades.
- Avoid circular imports by using one-way dependencies:
  - shared DTOs/types from `src/types.ts` or local `types.ts`;
  - LLM modules do not import UI modules;
  - PDF modules do not import chat modules;
  - chat may depend on PDF public facade/types only.
- Each phase must pass focused tests plus `npx vitest run -c
  ./plugin/vitest.config.ts` before the next phase.
- Final release gate:
  - `npx tsc --noEmit -p plugin/tsconfig.json`
  - `npm run build --prefix plugin`
  - `npx vitest run -c ./plugin/vitest.config.ts`
  - backend spec/version checks required by release workflow

## 4. Locked Design Decisions (Arena Consensus)

- Use facade-first extraction. Old files remain import-compatible public
  surfaces.
- Extract pure helpers before extracting class orchestration methods.
- Move source-contract tests to the module that owns the behavior in the same
  commit that moves that behavior.
- Keep `ChatSidebarView`, `LLMClient`, and `ExternalPdfView` as the public class
  names.
- Defer broad `main.ts` decomposition. PL-1 may only update imports or extract
  small startup helpers needed to avoid cycles.
- Add a plugin schema note that internal module layout may use facades while
  public plugin contracts remain unchanged. Guides do not need user-facing
  changes unless implementation changes visible behavior, which is forbidden.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: new features, visual redesign, new settings, session
  migration, provider changes, native PDF annotation system, chat compaction.
- **Stop Conditions**:
  - Stop if a module move requires changing persisted DTO fields.
  - Stop if a circular dependency cannot be removed without a public behavior
    change.
  - Stop if a source-contract test can only be satisfied by inert comments.
  - Stop if TypeScript requires broad `any` casts across extracted modules.

## 6. Evidence Ledger

- **Current Repository Reality**: See `.agents/plans/11_roadmap_evidence.md`.
- **Current Dirty Worktree**: At planning start, only
  `.agents/drafts/11_pl1_plugin_decomposition.md` was untracked.
- **Rollback Requirements**: Each extraction phase should be its own commit so
  regressions can be reverted by phase without losing the entire milestone.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 - Characterization Baseline**
  - Add tests that lock facade exports for `chatSidebar`, `llmClient`, and
    `externalPdfView`.
  - Add or update tests so source-contract assertions can target new owner
    modules.
  - Verify: focused tests + full plugin vitest.

- **P1 - Contract Specification**
  - Update `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` with an internal module
    ownership/facade rule for PL-1.
  - Do not update user guides unless behavior changes; behavior change is a stop
    condition.
  - Verify: `backend/tests/test_spec_sync.py` if version/spec titles are touched
    later; no version bump during planning.

- **P2 - LLM Client Extraction**
  - Create `plugin/src/agent/llm/`.
  - Move message utility helpers, provider adapters, and CLI runtime helpers in
    small commits.
  - Keep `plugin/src/agent/llmClient.ts` re-export-compatible.
  - Verify: `plugin/src/agent/llmClient.test.ts`, source-contract tests, full
    vitest, `tsc --noEmit`.

- **P3 - External PDF View Extraction**
  - Create `plugin/src/ui/pdf/`.
  - Move PDF types, ToC helpers, toolbar helpers, snipping helpers, and rendering
    helpers.
  - Move `ExternalPdfView` class only after helper extraction is green.
  - Keep `plugin/src/ui/externalPdfView.ts` as the public facade.
  - Verify: external PDF tests, chat/PDF source tests, full vitest.

- **P4 - Chat Sidebar Extraction**
  - Create `plugin/src/ui/chat/`.
  - Move context/status helpers, message rendering/edit rendering, session
    drawer helpers, drag/drop helpers, and model-control helpers.
  - Keep `plugin/src/ui/chatSidebar.ts` as the public facade or thin
    orchestrator until all imports are stable.
  - Verify: chat sidebar source tests, context tests, diff tests, full vitest.

- **P5 - Entrypoint Import Hygiene**
  - Update `main.ts` imports only as needed.
  - Extract tiny lifecycle helper modules only if they are required to remove
    cycles and are covered by existing tests.
  - Verify: `mainSecurity.test.ts`, settings tests, full vitest, plugin build.

- **P6 - Release Hygiene**
  - Run full local CI:
    - `npx tsc --noEmit -p plugin/tsconfig.json`
    - `npm run build --prefix plugin`
    - `npx vitest run -c ./plugin/vitest.config.ts`
    - backend checks required by release workflow
  - Run testbed smoke if any backend/plugin integration contract was touched.
  - Bump manifests to `0.35.0`, update changelog, sync spec titles for the new
    minor line, delete implemented plan artifacts after committing them to Git
    history, push branch, and open the PR.
