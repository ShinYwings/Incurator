# Frontend Proposal: Resolve the edit-affordance contradiction + two settings surfaces

Date: 2026-06-21 | Agent Persona: lead_architect (Plugin/Prompt Frontend)

## 1. Core Logic & Implementation

### Item A — Suppress edit affordances on localized question turns

The mechanism is already mostly correct; we only need to stop the payload from
contradicting itself. Introduce a single derived predicate in
`chatSidebar.ts::buildLLMMessages` (the existing prompt-assembly method) and gate
the two edit-affordance blocks on it.

```ts
// Latest turn carries a primary localized selection (e.g. Cmd+Shift+L line-range,
// text selection, PDF crop) AND is not itself an explicit edit request.
const latestIsLocalizedQuestion =
  lastUserHasPrimaryContext && !latestIsMarkdownEditRequest;
```

Then gate the affordances:

```ts
// editable_selection: only offer the "you may edit these lines" affordance when
// the turn is NOT a pure question about the selection.
const editInstruction = latestIsLocalizedQuestion
  ? ""
  : editableSelectionInstruction(editableRefs.length > 0, Boolean(openMarkdownEditTargets));
if (editInstruction) systemText += `\n\n<editable_selection>\n${editInstruction}\n</editable_selection>`;

// edit_review_loop: do not latch edit-bias from prior turns onto a localized question.
const editLoopLikely =
  !latestIsLocalizedQuestion &&
  (latestIsMarkdownEditRequest ||
    editableRefs.length > 0 ||
    Boolean(openMarkdownEditTargets) ||
    priorAnswerOpenedEditLoop);
```

Why this is the minimal correct fix:
- It does NOT remove the edit loop for genuine edit turns — `latestIsMarkdownEditRequest`
  still flips `latestIsLocalizedQuestion` to false, so "edit lines 5-7 to …" keeps
  full edit affordances.
- It does NOT touch the recency anchor, which already says the right thing.
- The whole change is "remove the contradicting voice," so the anchor wins by
  being unopposed rather than by being shouted louder.

`isMarkdownEditRequest` already exists and is the single source of truth for
"is this an edit ask," so question-vs-edit detection is reused, not reinvented.

### Item B — LaTeX fast/light model setting

1. `types.ts`: add `latexModel?: string` to `PluginSettings` (optional; empty =
   use main model). Generic-ish name kept narrow on purpose — YAGNI on a full
   per-task model registry until a second surface needs it.
2. `settings.ts`: add a text field "Convert-to-LaTeX model (fast/light)" with
   placeholder `qwen2.5:0.5b`, shown for all providers, `desc` noting empty =
   reuse main model. Persist via `saveSettings`.
3. `externalPdfView.ts::convertSelectionToLatex`: resolve the model as
   `this.plugin.settings.latexModel?.trim() || this.plugin.settings.model` and
   pass it to the LLM call. If the client call takes a model override param, use
   it; otherwise call the existing client path with the resolved model.

### Item C — Zotero profile recent-first ordering

1. `types.ts`: `ZoteroImportProfile` gains `lastUsedAt?: number` (epoch ms).
2. When a profile is applied/saved (`loadProfile` / the save path around
   `zoteroWizardModal.ts:450` / wherever `zoteroProfiles` is persisted), stamp
   `lastUsedAt`. Reuse the existing `rememberRecentZoteroItem` ordering idiom
   (most-recent-first array) rather than inventing a parallel scheme.
3. In `onOpen`/dropdown build (`:195`, `:211-226`), sort a copy of `profiles` by
   `lastUsedAt` desc (undefined sorts last, stable for ties) before
   `firstProfile` selection and before `forEach(addOption)`.

## 2. Pros & Cons

**Pros**
- Item A is ~6 lines and removes a contradiction rather than adding weight —
  lowest-risk way to make a prompt behavior deterministic.
- All three are independently testable at the payload/string level without a
  live LLM (assert presence/absence of blocks).
- No backend, schema, or migration surface.

**Cons / limitations**
- Item A relies on `isMarkdownEditRequest` heuristic quality; a question phrased
  imperatively ("rewrite this line") will correctly be treated as an edit, but a
  genuinely ambiguous turn could still mis-route. Acceptable: it degrades to
  today's behavior, not worse.
- Item B's `latexModel` is a single field, not a general task-model map; if a
  future "fast summary" surface lands we extend then (documented as a known
  non-goal).
- Item C assumes profiles are mutated in-memory then saved; must confirm the
  persistence call sites so `lastUsedAt` isn't dropped on serialization.
