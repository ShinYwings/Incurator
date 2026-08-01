# Frontend Context Proposal: Exact-Evidence and Focus-Gated Resolution
Date: 2026-08-01 | Agent Persona: Frontend Context Architect

## 1. Core Logic & Implementation

Keep the fix inside the existing plugin context pipeline.

1. In `pdfReferenceContext.ts`, distinguish exact equation-label resolution
   from generic BM25 object selection. For single-number equation pointers that
   requested adjacent expansion, scan the existing bounded next-first queue.
   If no exact label is found, convert the reference to `unresolved` before the
   block is serialized instead of returning the last loose match.
2. In `ChatSidebarView.ts`, determine whether each included PDF tab is eligible
   for latest-user reference resolution. Eligibility requires either:
   - the PDF tab is the active source for the current turn; or
   - the user's explicit context references identify that PDF document.
3. Leave existing selected/cropped reference resolution and generic PDF context
   inclusion unchanged. Only the new latest-user pointer resolver is gated.
4. Add focused tests for the false-positive text, a Markdown turn with a
   background PDF, the current real fixture, and an explicitly referenced PDF.

Pseudocode:

```text
latest = resolve(current_page)
if latest contains single-number equation requiring expansion:
    for adjacent_page in [next1, prev1, next2, prev2]:
        candidate = resolve(adjacent_page)
        if candidate has exact equation label:
            return candidate
    mark remaining expanded equation references unresolved
return serializable resolved references only

for included_pdf in prompt_context:
    if is_pdf_focused_for_turn(included_pdf, active_tab, explicit_refs):
        resolve_latest_user_references(included_pdf)
```

## 2. Pros & Cons

Pros:

- Repairs both failures at their decision points without changing schemas or
  provider permissions.
- Retains existing request caps and successful exact-label behavior.
- Makes mixed Markdown/PDF workspaces deterministic.

Cons:

- The focus predicate must reuse existing tab/context identity semantics; an
  ad-hoc path comparison would introduce cross-platform path bugs.
- A generic-number page that genuinely explains an equation but omits its
  exact label will now fail closed, which is the intended contract.
