# Defense & Revision: Local Closed-Set PDF Tools (Consensus)

Date: 2026-08-03 | Agent Persona: lead_architect (accepting red_teamer terms)

All seven critique items are accepted. The design is revised as follows and
these terms are **locked** for the Master Plan.

1. **Exhaustive `ToolPolicy` handling (accepted).** Every consumer switches
   over `ToolPolicy` with a `never`-typed default so a future added value is a
   compile error, not a silent fallthrough. A test enumerates all values and
   asserts each maps to an explicit MCP decision.

2. **Behavioral negative test replaces the string guarantee (accepted, and
   strengthened).** The prompt-wording assertion may be updated, but it is no
   longer the security guarantee. Two behavioral tests become the contract:
   - `shouldInjectMcpTools(POPOVER_PROFILE.toolPolicy, m, c) === false` for
     every `(m, c)` combination.
   - The tool array assembled for a popover call contains only names in
     `LOCAL_PDF_TOOL_NAMES` — asserted at the assembly function, so it holds
     without instantiating the UI.

3. **Unknown `pageCount` ⇒ no fetch tool (accepted).** `buildLocalPdfTools`
   emits nothing unless the captured context reports both an active PDF and a
   positive `pageCount`. An unbounded fetch tool is strictly worse than none.

4. **Per-request context capture with identity pinning (accepted).** Both the
   runner and its resolved `LocalPdfToolContext` — including a
   `documentId` — are captured into local consts once at the top of
   `streamChat`, mirroring the existing `mcpManager` capture and its stated
   rationale (`LLMClient.ts:802-805`). Every local tool call re-checks that
   the runner's current `documentId` still equals the captured one; on
   mismatch it returns a typed `document_changed` error instead of reading a
   different PDF.

5. **No active PDF ⇒ no local tools (accepted).** Same predicate as (3); a
   markdown-only question never sees a PDF tool.

6. **Conservative `hasOutline` (accepted).** Derived from the captured
   context; "outline not yet parsed" is treated as *has outline*, so
   `search_pdf_anchor` is withheld rather than wrongly exposed. This keeps the
   briefing's narrowing honest: search appears only for documents proven to
   have no map.

7. **Explicit page-fetch budget (accepted).** A per-request budget
   (`LOCAL_PDF_FETCH_BUDGET`, distinct from `MAX_RECURSION`) caps total pages
   fetched across all rounds. Exhaustion returns a typed error message so the
   model answers with what it has instead of stalling.

## Resulting invariant set (what the tests must lock)

- Popover receives **zero** MCP tools under every input combination.
- Local tools are emitted only with an active PDF, a known positive page
  count, and a stable document identity.
- `search_pdf_anchor` is emitted only when the document is proven outline-less.
- Every out-of-range, unparseable, budget-exhausted, or identity-changed call
  produces a typed tool-role error, never a thrown turn or a silent wrong read.
- CLI provider paths inject neither family (unchanged v0.23.0 sandbox contract).

No unresolved objections. Proceed to Master Plan synthesis.
