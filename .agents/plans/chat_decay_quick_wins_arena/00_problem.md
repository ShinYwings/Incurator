# Arena Briefing: Chat Context Decay & Minor Quick Wins

Date: 2026-06-21 | Branch: `feature/chat-decay-quick-wins`
Source drafts: `.agents/drafts/chat_context_decay.md`, `.agents/drafts/minor_quick_wins.md`
(Web Search feature is EXCLUDED per RELAY.md.)

## Problem Set

This milestone bundles three independent, plugin-only quick wins. They share no
code paths and can ship in any order, but they belong to one Minor release
(`0.20.0 → 0.21.0`) because each adds or changes a user-facing surface.

### Item A — Chat Context Decay on `Cmd+Shift+L` (the headline bug)

**Reported symptom**: In a long chat session — especially after the user has
asked for whole-document inspections/edits early on — pressing `Cmd+Shift+L`
(`incurator-obsidian-agent:line-reference`) to ask a *question* about a small
localized excerpt no longer works. The agent ignores the localized question and
instead proposes an `ai-agent-edit` block for the entire file, reverting to the
earlier whole-document behavioral pattern.

**Verified code reality (NOT the draft's stale model)**: The draft assumes there
is "no dynamic prompt weighting or recency anchoring." This is **out of date**.
v0.19.0 already shipped a substantial mitigation:

- `buildRecencyAnchor()` in `plugin/src/context/promptRegistry.ts:78` emits a
  `<critical_invariants>` block at the very END of the payload (recency-effect
  position) that says: *"Answer ONLY about the `<primary_focus_selection>` …
  Do NOT explain, summarize, or modify the whole document unless the latest
  request explicitly asks for it, regardless of earlier turns."*
- It is wired into the latest user turn at `chatSidebar.ts:1356-1361`, gated on
  `lastUserHasPrimaryContext`.
- `Cmd+Shift+L` produces a `line-range` ContextRef (`main.ts:1607`), and
  `isPrimaryUserContext()` (`chatContextPriority.ts:11`) classifies `line-range`
  as primary, so the selection IS wrapped in `<primary_focus_selection>` and the
  anchor's selection clause DOES fire.

**So why does it still decay?** The residual root cause is a **direct prompt
contradiction**, not missing anchoring. The very same `line-range` ref also
satisfies `editableRefs` at `chatSidebar.ts:1175-1181` (type `line-range` +
`filePath` + numeric `lineStart`/`lineEnd`). That has two consequences on a
localized *question* turn:

1. `editableSelectionInstruction(true, …)` is injected as `<editable_selection>`
   (`chatSidebar.ts:1186-1192`) — an affordance telling the model it MAY edit the
   selected lines.
2. `editLoopLikely` becomes true (`chatSidebar.ts:1268-1275`), appending the
   `<edit_review_loop>` contract. `editLoopLikely` is ALSO latched true by
   `priorAnswerOpenedEditLoop` — i.e. once any earlier assistant turn emitted an
   edit, every later turn (including pure questions) inherits edit-bias.

The model therefore receives, in the same payload, both "answer only, do not
modify the document" (recency anchor) and "you may edit these lines / you are in
an edit-review loop" (editable_selection + edit_review_loop). In a long, edit-
heavy context the edit-bias wins. **The fix is to resolve the contradiction:
when the latest turn is a localized *question* (primary selection present AND the
turn is not an edit request), suppress the edit affordances so the recency anchor
is unopposed.**

### Item B — Convert-to-LaTeX Fast/Light Model setting

`convertSelectionToLatex()` (`externalPdfView.ts:1294`) reuses the main chat
model for a trivial transcription task. There is no per-task model override.
Need: a settings field for a "Fast/Light model" used only by LaTeX conversion,
defaulting to `qwen2.5:0.5b` on Ollama, falling back to the main model when unset
or when the provider is not Ollama. Config plumbing should be generic enough to
reuse for future light-task surfaces, but only the LaTeX surface is wired now.

### Item C — Zotero recent-first ordering

Importable Zotero *items* already sort recent-first via `prioritizeZoteroItems`
(`zoteroWizardModal.ts:136-140`). The gap: the **Import Profile dropdown**
(`zoteroWizardModal.ts:211-226`) and its default selection iterate
`settings.zoteroProfiles` in stored insertion order, so a profile used today can
sit below stale ones. Need recent-first ordering for the profile list + default.

## Cross-cutting constraints

- Plugin-only (TypeScript). No backend/schema/DAG impact → no migration.
- Every behavioral change needs a `.test.ts` and doc updates
  (`PLUGIN_GUIDE.md` + `PLUGIN_GUIDE_KR.md`, plugin spec).
- Minor bump `0.20.0 → 0.21.0`; all three manifests + spec titles to `v0.21`.
- Success for Item A is measurable: with a primary selection on a non-edit
  question turn, the assembled payload must contain NO `<editable_selection>`
  and NO `<edit_review_loop>` block, while still containing the recency anchor.
