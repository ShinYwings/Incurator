# v0.39.2 Equation-Reference Domain Analysis

Date: 2026-07-31

## Design Constraints From The Codebase

- `ChatSidebarView.buildMessages()` resolves references only inside an included
  context item's own `ref.content`; it never resolves references written in the
  latest user request.
- The current synchronous resolver can only use already-loaded page text. The
  existing `resolveSelectionReferencesBlockAsync()` already defines the safe
  fetch-and-re-resolve boundary needed by this hotfix.
- `buildIncuratorProviderContext()` already has the richest PDF identity and the
  read-only `getPdfContext()` transport. No new backend command, schema, or
  provider permission is needed.
- Antigravity must retain the v0.23.0 containment posture: no
  `--dangerously-skip-permissions`, no broad trust flag, and no arbitrary
  external root widening.

## Documentation And Spec Invariants

- Selected pointer contexts are documented as producing
  `<resolved_cross_references>` before generic page context.
- The same precedence must extend to an explicit pointer in the latest user
  request, because that is the actual requested target.
- External PDF absolute paths remain machine-local hints. They must not become
  persistent synced state or broad CLI read roots.

## Alternatives And Trade-Offs

1. Add the entire active external PDF directory to `agy --add-dir`.
   Rejected: it widens native-agent file access and leaves correctness dependent
   on the provider deciding to inspect the right page.
2. Add `command` and target-specific `read_file` permission rules.
   Rejected: the user asked a read-only question already answerable through the
   established PDF context service; provider-native tools are unnecessary.
3. Resolve the latest user request through the existing async PDF resolver and
   fetch missing target pages via `getPdfContext(radius=0)`.
   Selected: it supplies deterministic evidence, preserves containment, and
   reuses existing read-only boundaries.

## Final Decision

Before final provider message assembly, inspect the latest user request for PDF
references. For each included PDF tab, resolve against the known window/index;
when unresolved, fetch a small bounded adjacent-page set through the existing
PDF context API and emit a high-priority `<resolved_cross_references>` block.
Do not add filesystem permissions or roots.

## Implementation Pseudocode

```text
for each included PDF tab:
    source = current page/window/outline/index
    block = await resolveSelectionReferencesBlockAsync(latest_user_text, source,
        page -> getPdfContext(identity, page_num=page, radius=0).pages[page])
    if block:
        append block before generic pdf_window context
```

For an unresolved bare equation number with no outline, the resolver may inspect
only a small ordered neighborhood around the current page (next page first, then
previous/remaining adjacent pages), stopping as soon as the exact label is found.
