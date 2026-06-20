# v0.21.0 Master Implementation Plan — Chat Context Decay & Minor Quick Wins

Date: 2026-06-21
Status: DRAFT — Arena debate concluded. Awaiting human approval before any code.
Branch: `feature/chat-decay-quick-wins`
Arena record: `.agents/plans/chat_decay_quick_wins_arena/`

## 1. Objective

Ship three independent, plugin-only quick wins as one Minor release
(`0.20.0 → 0.21.0`):

- **A. Chat decay fix**: When the latest chat turn is a *fresh localized question*
  (a primary selection — e.g. `Cmd+Shift+L` line-range — present, the turn is not
  an edit request, and it is not continuing an open edit loop), the assembled LLM
  payload must contain the recency anchor UNOPPOSED: no `<editable_selection>` and
  no `<edit_review_loop>` block. Definition of done: the model answers about the
  selection and does not emit an `ai-agent-edit` block for the whole file.
- **B. LaTeX fast/light model setting**: A plugin setting lets the user pick a
  separate light model for right-click "Convert to LaTeX"; empty = reuse main
  model; placeholder/recommended default `qwen2.5:0.5b` (Ollama).
- **C. Zotero recent-first profiles**: The Zotero import Profile dropdown and its
  default selection list profiles most-recently-used first.

## 2. Explicit Non-Goals

- NOT a rewrite of the v0.19.0 recency-anchor system — it stays; we only remove
  the contradicting edit affordances.
- NOT a general per-task model registry — Item B adds ONE narrow `latexModel`
  field; future light-task surfaces extend it later.
- NOT changing item-level Zotero ordering (already recent-first) — only the
  profile list/default.
- NO Web Search work (explicitly excluded by RELAY.md).
- NO backend, DAG, schema, or DB change; NO migration.
- NOT changing `isMarkdownEditRequest` heuristics.

## 3. Strict Quality Conditions & Release Gates

- `npx vitest run -c ./plugin/vitest.config.ts` 100% passing, including new tests.
- New deterministic unit test proves the Item A truth table and payload
  block presence/absence — NO live LLM dependency.
- Genuine edit turns and in-flight edit-loop continuations retain full edit
  affordances (no regression) — covered by test.
- Docs updated: `PLUGIN_GUIDE.md` first, then `PLUGIN_GUIDE_KR.md`; plugin spec
  title bumped to `v0.21`.
- All three build manifests (`backend/pyproject.toml`, `plugin/package.json`,
  `plugin/manifest.json`) = `0.21.0`; all four spec titles declare `v0.21`;
  `backend/tests/test_spec_sync.py` green.

## 4. Locked Design Decisions (Arena Consensus)

1. **Item A predicate** (the single load-bearing decision) — CORRECTED per human
   review, supersedes red-team A1:
   ```ts
   const latestIsLocalizedQuestion =
     lastUserHasPrimaryContext &&
     !latestIsMarkdownEditRequest;
   ```
   When true, suppress BOTH `<editable_selection>` and `<edit_review_loop>`.
   Recency anchor is unchanged and therefore unopposed.
   **Why `!priorAnswerOpenedEditLoop` was REMOVED**: `priorAnswerOpenedEditLoop`
   inspects the last assistant message. In the exact reported scenario (early
   whole-doc edit → then a fresh `Cmd+Shift+L` question), the immediately prior
   assistant turn DID contain edits, so `!priorAnswerOpenedEditLoop` is false and
   suppression would never fire — the bug survives. A fresh non-edit question must
   UNCONDITIONALLY override edit affordances for the recency anchor to win. The
   red-team's "kills an in-flight edit loop" worry is moot: a fresh non-edit turn
   should be answered, not edited, and once the assistant answers without an edit
   the `priorAnswerOpenedEditLoop` chain self-clears for the next turn. Genuine
   edit continuations are still protected because `latestIsMarkdownEditRequest`
   flips the predicate to false for any edit-phrased turn.
2. **Extract a pure helper** `shouldSuppressEditAffordances({hasPrimarySelection,
   isEditRequest, priorAnswerOpenedEditLoop})` so the truth table is unit-testable
   without instantiating the sidebar. Place it next to the existing context-priority
   pure functions (`chatContextPriority.ts`) for cohesion.
3. **Item B**: `PluginSettings.latexModel?: string`. **The plugin LLM client MUST
   be extended (TS-only — the no-backend rule is Python-only)**: add an
   `opts?: { model?: string }` parameter to `LLMClient.complete()`
   (`plugin/src/agent/llmClient.ts:962`), mirroring the existing
   `streamChat(messages, onChunk, opts?: { toolPolicy })` pattern
   (`:663-666`). Inside `complete`, resolve `const model = opts?.model ||
   this.settings.model` once and replace the hardwired `this.settings.model`
   references in the HTTP path (`:974`, `:976`, `:997`, `:1003`, `:1006`) with
   `model`. A transient client is NOT used (`auth` is private at `:537`).
   Call-site policy in `externalPdfView.ts::convertSelectionToLatex`: pass
   `{ model: settings.latexModel.trim() }` ONLY when the override is non-empty AND
   the provider is Ollama; otherwise pass nothing → main model. (Ollama runs the
   HTTP path, so the override lands; non-Ollama falls back to the main model by
   design.) Settings field placeholder shows `qwen2.5:0.5b`. On conversion
   failure, Notice the resolved model + `ollama pull` hint.
4. **Item C**: `ZoteroImportProfile.lastUsedAt?: number`. Stamp at the single
   shared persistence/apply point. Sort a COPY (`[...profiles]`) by `lastUsedAt`
   desc, undefined last, stable for ties.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: Web Search; `[[wikilink]]` validation (Roadmap item 5);
  context-compaction token meter (separate milestone); diff-viewer work.
- **Stop Conditions**:
  - **STOP** after P1 (contracts/docs) for the user's approval gate if any spec
    contract wording is non-obvious.
  - Item B is NO LONGER a defer-gate. The LLM client extension is confirmed
    feasible and in-scope (TS-only). STOP only if wiring `opts.model` through the
    HTTP path turns out to break an existing `complete()`/`streamChat` caller in a
    way that needs a contract change beyond an optional param.
  - **STOP** if the Zotero profile persistence has multiple uncoordinated save
    sites that can't share one stamp point without a refactor → reassess scope.

## 6. Evidence Ledger

See `.agents/plans/01_chat_decay_quick_wins_roadmap_evidence.md`. Key pre-facts:
- Rollback anchor: `0339b63` (current HEAD, clean worktree).
- v0.19.0 recency anchor confirmed live (`promptRegistry.ts:78`, wired at
  `chatSidebar.ts:1356`).
- `line-range` is primary context (`chatContextPriority.ts:20`) and ALSO an
  editable ref (`chatSidebar.ts:1175`) — the contradiction source.
- Current version `0.20.0` across all three manifests (verified).

## 7. Execution Phases (TDD + CI at each phase)

- **P0 — Research & Baseline**:
  - DONE (human-reviewed): `LLMClient.complete()` (`llmClient.ts:962`) takes no
    opts; `auth` is private (`:537`); model is hardwired to `this.settings.model`.
    `streamChat` already has `opts?: { toolPolicy }` (`:663`) to mirror. Item B
    will extend `complete()` with `opts?: { model?: string }`.
  - Enumerate every existing caller of `complete()` to confirm the optional param
    is backward-compatible (no caller passes a 2nd arg today).
  - Confirm the single Zotero profile persistence/apply call site(s).
  - Capture the green baseline of the current chatSidebar/zotero/externalPdf
    vitest suites before touching code.
- **P1 — Contract & Docs (docs-first)**:
  - Update `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`: document the localized-
    question suppression rule, `latexModel` setting, `lastUsedAt` profile field.
  - Update `docs/guides/PLUGIN_GUIDE.md` then `PLUGIN_GUIDE_KR.md`.
  - Bump the four spec titles to `v0.21`. (STOP for approval if wording is unclear.)
- **P2 — Item A (chat decay)** TDD:
  - Write failing tests: truth table for `shouldSuppressEditAffordances`; payload
    assertions (selection-question turn → no edit blocks + anchor present; edit
    turn → blocks present; open-edit-loop continuation → blocks present).
  - Implement helper + gate the two blocks + gate `editLoopLikely`.
  - Verify: `vitest` green, no regression in existing chatSidebar tests.
- **P3 — Item B (LaTeX model)** TDD:
  - Tests: `complete()` honors `opts.model` over `settings.model` in the HTTP body
    (assert the request body/url model); omitting opts uses `settings.model`
    (backward-compat); call-site passes the override only for non-empty
    `latexModel` AND Ollama provider; failure Notice path if testable.
  - Implement: extend `LLMClient.complete()` signature + internal model resolution;
    `types.ts` `latexModel` field; `settings.ts` UI; `externalPdfView.ts` call-site
    policy.
  - Verify: `vitest` green; existing `complete()`/`streamChat` callers unaffected.
- **P4 — Item C (Zotero profiles)** TDD:
  - Tests: profiles sorted recent-first by `lastUsedAt`; undefined last; copy not
    mutated; default selection picks most-recent.
  - Implement field + stamp + sorted render.
  - Verify: `vitest` green.
- **P5 — Release**:
  - Bump `0.21.0` in all three manifests + four spec titles; `CHANGELOG.md`.
  - `backend/tests/test_spec_sync.py`, full `vitest`, `ruff`/`mypy` (no backend
    change but run for safety) green.
  - Delete plan artifacts; `chore(release): v0.21.0`; push; PR.

> Versioning: Minor `0.20.0 → 0.21.0` (new user-facing setting + new behavior).
