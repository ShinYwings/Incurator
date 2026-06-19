# v0.14.0 Sidechat Edit Loop — Enforced & Observable State Machine

Date: 2026-06-19
Status: DRAFT (REVISED per user scope override) — awaiting user approval before implementation.

> **Scope change note.** The first draft of this plan (the minimal "prompt
> helper only" version) was rejected by the user. The user explicitly requested
> all four expansions: (1) parser / hard enforcement, (2) wider trigger
> conditions, (3) user-visible UI phases, and (4) a re-scope/rethink. This
> document supersedes the minimal plan. The original non-goals that forbade
> hard-blocking, wider triggers, and UI changes are **intentionally reversed**
> here. The Arena consensus doc has an appended scope-override round recording
> this decision (`sidechat_loop_regression_arena/04_scope_override.md`).

## 1. Objective

Convert the sidechat file-edit workflow from a soft, prompt-only suggestion
into an **enforced, observable four-phase state machine**. Whenever the agent
proposes any file mutation, it MUST emit and the UI MUST display the loop:

`Analysed → Reviewed → Updated → Reviewed`

before the user can accept the change through the Diff Viewer.

Definition of done:

- The agent is *prompted* to emit the four phases as machine-parseable markers
  for every edit-producing turn (wider triggers than before).
- A pure validator *parses* the response and *hard-gates* the
  Review/Apply path when an edit proposal is missing the required phases.
- The sidechat *renders* the four phases as distinct, labeled, observable UI
  sections, with the `ai-agent-edit` proposal anchored under the second
  `Reviewed` phase.
- The existing Diff Viewer remains the only mutation path.
- Tests + docs/specs prove the contract.

## 2. Re-scope Rationale (Item 4: Rethink Scope/Approach)

The minimal prompt-only approach cannot satisfy the user's actual requirement
("the agent must explicitly halt or output its review state before mutating
files" — draft success criteria). A prompt request is not enforcement: models
silently skip it (the reported regression). To make the loop *reliable* and
*observable* we need three coordinated layers — prompt, validator, renderer —
which is precisely the composable-prompt + enforced-contract direction of
roadmap item 6 (`prompt_architecture_refactoring.md`).

Therefore this plan claims a **vertical slice** of item 6:

- The edit-loop contract is implemented as a single composable prompt block
  (`getEditLoopContract()`), anchored near the END of the system prompt where
  LLM attention is strongest (directly addresses the "Dynamic Anchoring" goal
  of the prompt-architecture draft).
- It is the first contract to be paired with a runtime validator, establishing
  the pattern (prompt block ↔ parser ↔ UI) that the broader refactor will
  generalize to the popover and other contracts.

We do NOT do the full registry/builder refactor here. We add ONE composable
block + its validator + its renderer, and leave the rest of `systemPrompt.ts`
untouched. This keeps the change reviewable while moving item 6 forward.

## 3. Explicit Non-Goals (revised)

- Do not implement the full prompt registry/builder refactor (only one block).
- Do not change MCP tool sandboxing or popover prompt text in this patch
  (popover inheritance is deferred to item 6).
- Do not redesign the Diff Viewer internals; only gate its entry point.
- Do not add backend schema, DB migration, or new CLI commands.
- Do not expose private chain-of-thought; the four phases are deliberate,
  user-facing *work products*, not raw reasoning.
- Do not force the loop for pure Q&A (no edit blocks ⇒ no contract, no gate).

## 4. Locked Design Decisions

### 4.1 Canonical phase markers

Phases use stable, English, machine-parseable markers so the validator and
renderer are language-independent (phase *content* may be in the user's
language):

```
[[PHASE:ANALYSED]]   ... what the agent understood / the logical gap ...
[[PHASE:REVIEWED]]   ... critique of its own plan before editing ...
[[PHASE:UPDATED]]    ... the ai-agent-edit block(s) ...
[[PHASE:REVIEWED]]   ... self-check that the edit closes the gap ...
```

Markers are stripped from the rendered prose and converted into UI section
headers. Rationale for a sentinel token (`[[PHASE:...]]`) over a Markdown
heading: it cannot collide with user note content or the model's own headings,
and survives the existing thought-block / `ai-agent-edit` stripping passes.

### 4.2 Three coordinated layers

1. **Prompt (Item 2 — wider triggers).** New pure block
   `getEditLoopContract()` in `plugin/src/context/systemPrompt.ts`. Appended by
   `chatSidebar.buildLLMMessages` for ANY turn likely to produce a mutation, not
   only "latest-turn Markdown edit with editable target":
   - latest message is a Markdown edit request (`isMarkdownEditRequest`), OR
   - there is an editable line-range selection, OR
   - there is an open Markdown edit target, OR
   - the prior assistant turn already opened an edit loop (multi-turn edits —
     keeps the contract alive across follow-ups like "now also fix the heading").
   Anchored as the LAST system block so attention does not decay.

2. **Validator (Item 1 — hard enforcement).** New pure module
   `plugin/src/context/editLoopContract.ts`:
   - `parseEditLoopPhases(content): { phases: PhaseMarker[]; editBlocks: number }`
   - `validateEditLoop(content): { ok: boolean; missing: PhaseLabel[]; hasEdits: boolean }`
   The contract is required ONLY when `hasEdits` is true. A response with edit
   blocks but an incomplete/absent phase sequence is `ok: false`.

3. **Renderer + Gate (Item 3 — visible UI).** `chatSidebar` render path:
   - When phases parse, render each as a labeled, collapsible section
     (`.ai-agent-edit-phase` with `data-phase` attr), reusing the existing
     `ai-agent-thought-block` styling vocabulary; the `ai-agent-edit` inline
     diff is rendered inside the `UPDATED` section.
   - **Hard gate**: the "Review"/apply entry point
     (`extractMultiEditProposals` → `renderInlineMultiDiff` → DiffViewer.show)
     is blocked when `validateEditLoop` returns `ok: false`. The blocked state
     shows an explicit banner ("Agent skipped the review loop") with two
     actions: **Re-run with loop** (auto-reprompts appending a one-line
     reminder) and **Override & review anyway** (explicit user escape hatch so
     enforcement is firm, not a dead end).

### 4.3 Enforcement firmness

"Hard" enforcement = the Diff Viewer cannot be opened from a non-conforming
response by the default path; the user must consciously click **Override**.
We do NOT silently drop the edit or block the chat. This satisfies "the agent
must explicitly output its review state before mutating files" while avoiding a
trap when a provider genuinely cannot comply.

## 5. Strict Quality Conditions & Release Gates

- Contract present, parseable, and language-independent (English markers).
- Wider trigger set covered by unit tests (selection / open target / md-request
  / multi-turn continuation).
- Validator: edits-without-phases ⇒ `ok:false`; full sequence ⇒ `ok:true`;
  Q&A with no edits ⇒ contract not required.
- Gate: non-conforming edit response does not auto-open the Diff Viewer;
  Override path still works; conforming response behaves exactly as today.
- Existing `ai-agent-edit` parsing + Diff Viewer review behavior unchanged for
  conforming responses (regression guard).
- Plugin checks pass: `npx tsc --noEmit`, `npx vitest run -c ./plugin/vitest.config.ts`.
- Docs/specs updated before completion (PLUGIN_SCHEMA → PLUGIN_GUIDE → _KR).

## 6. Stop Conditions

- Stop if the gate cannot be inserted without restructuring the Diff Viewer
  internals (then descope the gate, ship prompt+validator+UI, and escalate the
  Diff Viewer dependency to item 2).
- Stop if marker stripping cannot coexist with existing `ai-agent-edit` /
  thought-block stripping without a larger renderer rewrite.
- Stop if the multi-turn continuation trigger requires persisting new state on
  `ChatMessage` beyond a derived flag (avoid schema growth in this patch).

## 7. Evidence Ledger

- **Current repository reality** (verified 2026-06-19):
  - `plugin/src/context/systemPrompt.ts` — static base prompt +
    `editableSelectionInstruction(hasEditableSelection, hasOpenMarkdownEditTarget)`.
  - `plugin/src/ui/chatSidebar.ts` (4332 lines):
    - `buildLLMMessages` (L1143) assembles system text; edit triggers computed
      at L1170–L1190 from `isMarkdownEditRequest` (L1362) + editable line-range
      refs + `buildOpenMarkdownEditTargetContext`.
    - Edit proposals parsed by `extractMultiEditProposals` (L3456,
      `ai-agent-edit` block regex) and legacy `extractEditProposal` (L3505).
    - Render path L2490–L2533 routes proposals to `renderInlineMultiDiff` /
      `renderInlineDiff`; `processMarkdownForThoughts` (L3077) already injects
      collapsible `details.ai-agent-thought-block` sections — the UI vocabulary
      we extend for phase sections.
    - DiffViewer entry: `DiffViewer.getInstance(...).show(...)` (~L3443).
  - `plugin/src/context/systemPrompt.test.ts` already asserts prompt strings.
  - No backend schema/migration required.
- **Current dirty worktree**: `.agents` roadmap/relay/draft cleanup in progress;
  shipped RAG plan artifacts deleted. New work must not touch that cleanup.
- **Rollback**: revert `editLoopContract.ts`, the `getEditLoopContract()` block,
  the `buildLLMMessages` append, the render/gate hunks, and their tests to
  restore current behavior. No data migration.
- **Version anchor**: manifest/package/pyproject all at `0.13.0`. This is a
  Minor feature ⇒ target **v0.14.0**.

## 8. Execution Phases (TDD + CI gate at each phase)

- **P0 — Baseline inspection** ✅ (captured in §7). Confirm marker token does not
  collide with existing stripping regexes.

- **P1 — Spec & guide first**
  - `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`: define the edit-loop contract
    (markers, validator result shape, gate behavior, trigger set).
  - `docs/guides/PLUGIN_GUIDE.md` then `docs/guides/PLUGIN_GUIDE_KR.md`: document
    the user-visible four-phase sections, the blocked-state banner, and the
    Re-run / Override actions.

- **P2 — TDD (failing first)**
  - `systemPrompt.test.ts`: `getEditLoopContract()` content + presence rules.
  - New `editLoopContract.test.ts`: `parseEditLoopPhases` / `validateEditLoop`
    across conforming, missing-phase, out-of-order, and no-edit responses.
  - `chatSidebar` trigger test: contract appended for each of the four trigger
    conditions and omitted for pure Q&A (extend existing harness only; no broad
    fixtures — see stop condition).

- **P3 — Prompt layer**
  - Add `getEditLoopContract()` pure helper; append last in `buildLLMMessages`
    under the widened trigger predicate.

- **P4 — Validator layer**
  - Implement `editLoopContract.ts`; wire `validateEditLoop` into the render
    path to compute the gate decision.

- **P5 — UI layer (visible phases + gate)**
  - Render phase sections; anchor the inline diff in `UPDATED`; implement the
    blocked banner with **Re-run with loop** (reprompt) and **Override & review**.

- **P6 — Validation**
  - `npx tsc --noEmit`; `npx vitest run -c ./plugin/vitest.config.ts`
    (targeted files first, then full plugin suite).

- **P7 — Release cleanup**
  - Bump `manifest.json`, `package.json`, `pyproject.toml` → `0.14.0`; update
    `CHANGELOG.md`.
  - Mark roadmap item 1 complete; delete this plan from active `.agents/plans/`
    after merge.
