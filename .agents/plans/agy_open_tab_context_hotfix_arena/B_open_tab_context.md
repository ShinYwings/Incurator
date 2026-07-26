# Open-Tab Context Domain Analysis

Date: 2026-07-26

## Design Constraints From The Codebase

- `iterateAllLeaves()` already sees all leaves, but `getOpenTabContexts()` drops
  every `0x0` leaf before recording identity or content
  (`plugin/main.ts:1812-1824`).
- `buildAutoContextRefs()`, system prompt tab lists/outlines/edit targets, chips,
  and the `+` menu all consume the same narrowed `openTabs` array.
- Prompt assembly can serialize the same tab in the system prompt, user context,
  outlines, and edit targets. Removing the visibility filter without a second
  inclusion gate can sharply increase prompt size.
- Normal PDF chat must remain ephemeral. A purple `Add source` badge is a manual
  durable-refinement control, never an ingest side effect.

## Alternatives And Trade-offs

### A. Remove the `0x0` visibility filter and auto-include everything

Rejected. It is the smallest diff but creates unbounded hidden-tab prompt growth
and can repeat full Markdown bodies several times.

### B. Keep current visible-only behavior and document it

Rejected. The `Add context from open tabs` menu remains unable to select hidden
open tabs, and users cannot see why tab/chip counts differ.

### C. Enumerate all leaves and separate visibility from prompt inclusion

Selected. Every eligible open Markdown/PDF leaf gets identity and visibility
metadata. Visible leaves start included; hidden leaves render as eye-off and
materialize into the prompt only after explicit inclusion.

## Final Decision

- Add `isVisible` to the internal `OpenTabContext` contract.
- Enumerate all Markdown, built-in PDF, and external PDF leaves; continue
  excluding chat/utility views.
- Render a chip for every unique eligible context identity.
- Default `includeInPrompt` from visibility, with a tri-state user override that
  survives tab switches for the session.
- Only prompt-included tabs may contribute page/body content, tab listings,
  outlines, continuity summaries, or edit targets.
- Hidden PDF identity chips may use cached/view state before full page capture;
  absence of `pdfPage` must not erase the chip.
- Refresh chips on layout/tab open/close as well as active-leaf change.
- Dedupe exact duplicate `(view type, portable source/file identity, page)` keys;
  preserve distinct pages of the same PDF.

## Implementation Pseudocode

```ts
for leaf in iterateAllLeaves():
    if leaf is chat or unsupported utility view:
        continue
    visible = leaf.container rect is not 0x0
    identity = portable file/runtime/Zotero identity
    tab = { identity, viewType, label, isVisible: visible }
    if visible or user explicitly included identity:
        tab.content/pdfPage = captureCurrentContext(leaf)
    tabs.push(tab)

for tab in tabs:
    key = contextKey(tab)
    include = override[key] ?? tab.isVisible
    renderChip(tab, eye = include)
    if include:
        promptRefs.push(materialize(tab))
```

## Required Tests

- One tab group: one visible plus multiple hidden leaves are all enumerated.
- Multiple splits: each visible leaf starts eye-on; hidden members start eye-off.
- Hidden tabs render chips but are absent from every prompt block.
- Eye-on/pin adds only the selected hidden tab.
- Open/close/switch refreshes chip state.
- Same PDF different pages remain distinct; exact duplicates follow the locked
  dedupe key.
- PDF context-not-ready and cached fallback paths preserve visibility semantics.

