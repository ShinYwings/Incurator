# v0.15.0 Master Implementation Plan

Date: 2026-06-19
Status: APPROVED — Arena debate concluded. Specs/tests are updated before
implementation.

## 1. Objective

Upgrade the Quick Query Popover into a session-local persistent reference
window: outside clicks do not close it, it can be dragged by its header, it can
be minimized/restored without losing answer or follow-up state, and its title
reflects the latest submitted question.

Definition of done:
- The five review findings in `.agents/drafts/persistent_popover.md` are fixed.
- Docs/specs describe the new manual lifecycle.
- Plugin tests, TypeScript, and build pass.
- Version/changelog are updated to `v0.15.0`.

## 2. Explicit Non-Goals

- No Obsidian `ItemView` migration.
- No restart persistence.
- No chat-sidebar session persistence for popover turns.
- No new quick-query presets, tool buttons, or backend query route.
- No work from `.agents/drafts/popover_tool_scope.md`; that remains item 6 scope.

## 3. Strict Quality Conditions & Release Gates

- Outside workspace clicks never call `removePopover`.
- Trigger button still disappears when selection collapses or outside click
  occurs without an open popover.
- Popover is positioned once at spawn and then only moves by drag.
- Popover close aborts in-flight generation and removes drag/reposition
  listeners.
- Minimize/restoration preserves `turns`, answer DOM, and current input state.
- EN/KR guide and plugin schema remain synchronized.

## 4. Locked Design Decisions (Arena Consensus)

- Keep `QuickQueryPopover` as the single raw DOM owner.
- Use owner-document/default-view for popout compatibility.
- Add local drag/minimize/title fields to `QuickQueryPopover`.
- Do not introduce a DOM test dependency; use existing source-contract style for
  private Obsidian UI wiring and pure tests where possible.
- Treat this as a minor plugin UX release: `v0.15.0`.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: popover MCP tool injection, prompt unification, path
  sandboxing, restart persistence, multi-popover management.
- **Stop Conditions**:
  - Stop if implementation requires persistent storage or `ItemView`.
  - Stop if drag behavior cannot be made popout-window safe with owner-window
    listeners.
  - Stop if docs/specs reveal a conflicting higher-priority contract.

## 6. Evidence Ledger

See `.agents/plans/04_persistent_quick_query_popover_evidence.md`.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Source Baseline**
  - Verify current source-contract tests fail or add failing assertions for the
    five review findings.
  - Verify: focused Vitest shows the new assertions fail before code changes.

- **P1 — Contract Specification**
  - Update `PLUGIN_SCHEMA.md` §13.1/§13.4 and EN/KR `PLUGIN_GUIDE` Quick Query
    sections for persistent manual lifecycle, drag, minimize, and dynamic title.
  - Verify: docs mention no outside-click dismissal and no restart persistence.

- **P2 — Tests First**
  - Extend `quickQueryPopover.test.ts` with source-contract assertions for:
    teardown before `activeDoc` mutation, node-safe click target handling,
    no popover reposition in scroll handler, captured `titleEl`, minimize class,
    drag listener attach/detach.
  - Verify: focused Vitest fails on current implementation.

- **P3 — Popover Lifecycle Implementation**
  - Reorder `openForCurrentSelection` teardown.
  - Change `handleDocumentClick` to remove only the trigger button outside own
    UI and never dismiss an open popover.
  - Update `attachRepositionListeners` to track only `buttonEl`.
  - Verify: focused Vitest passes.

- **P4 — Persistent Tool Window UI**
  - Add `titleEl`, minimize control/state, drag state/listeners, and CSS for
    minimized/drag affordances.
  - Verify: focused Vitest, TypeScript.

- **P5 — Release Validation**
  - Run full plugin tests, TypeScript, and plugin build.
  - Bump backend/plugin versions to `0.15.0` and update `CHANGELOG.md`.
  - Update `RELAY.md` and roadmap state.
  - Push branch and open PR.
