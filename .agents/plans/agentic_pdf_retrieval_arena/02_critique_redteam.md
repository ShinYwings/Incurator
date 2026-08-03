# Critique on [Local Closed-Set PDF Tools]

Date: 2026-08-03 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

1. **"Local-only" silently widens if a future surface forgets the third
   value.** `ToolPolicy` is a union consumed in several places
   (`boundaryConstraints`, `shouldInjectMcpTools`, prompt assembly). A new
   `switch` that handles `"auto"`/`"none"` and falls through on
   `"local-only"` would grant or deny tools by accident. The proposal relies
   on reviewers noticing.

2. **The security test becomes weaker, not just different.** Replacing
   `expect(text).toContain("NO tools and NO filesystem access")` with a
   looser assertion risks a future edit re-granting MCP to the popover with
   nothing failing. The *negative* property (popover never receives an MCP
   tool) is currently guaranteed by a string; after the change it must be
   guaranteed by a behavioral test or it is guaranteed by nothing.

3. **Page-bound enforcement is claimed but the runner is trusted.**
   `parseLocalPdfToolCall` bounds `page_number` against `pageCount` — but
   `describeContext()` supplies `pageCount`, and if it returns `undefined`
   (no active PDF view, backend-only context) the bound silently disappears
   and any integer is accepted. `fetchActivePdfPage` would then be called
   with arbitrary page numbers.

4. **The runner outlives the surface that authorized it.** `LLMClient` holds
   `localToolRunner` as instance state, like `mcpManager`. The popover and
   sidechat share one client. A popover request that starts, then a sidechat
   request that swaps context, could let one surface's tool call resolve
   against another surface's PDF. The existing code has a documented
   precedent for exactly this concern: `mcpManager` is captured into a local
   const specifically so "no state drift if this.mcpManager is swapped
   mid-flight" (`LLMClient.ts:802-805`).

5. **No-PDF case emits tools that always fail.** If no PDF is open, the
   runner still exists and `buildLocalPdfTools` still emits
   `fetch_pdf_page`. The model will call it, get an error, and burn
   recursion turns on a capability that cannot work — degrading a plain
   markdown question.

6. **`search_pdf_anchor` gating is computed once.** `hasOutline` comes from
   `describeContext()` at loop start. Fine — but if the gate is computed from
   an outline that is merely *not yet loaded* (async PDF.js outline parse),
   a race exposes the search tool on a document that does have a ToC, quietly
   contradicting the briefing's narrowing decision.

7. **Cost/latency is unbounded per user turn in practice.** MAX_RECURSION=5
   with parallel `tool_calls` per turn means a model could request many pages
   per iteration. The proposal bounds *rounds*, not *pages*.

## 2. Suggested Alternatives

1. Make `ToolPolicy` exhaustiveness a compile-time guarantee: every consumer
   must use a `switch` with a `never`-typed default, so adding a value breaks
   the build rather than silently defaulting. Add a test that enumerates all
   `ToolPolicy` values and asserts each maps to an explicit MCP decision.

2. Keep a **behavioral** negative test, not a string test: assert that for
   `POPOVER_PROFILE`, `shouldInjectMcpTools(...) === false` for every
   combination of `hasMcpManager` and `useCli`, and that the tool list handed
   to the provider for a popover call contains **only** names from
   `LOCAL_PDF_TOOL_NAMES`. String assertions on prompt wording may relax; the
   behavioral one must not.

3. Fail closed when `pageCount` is unknown: if `describeContext()` cannot
   state a page count, `fetch_pdf_page` must not be emitted at all. An
   unbounded fetch tool is worse than no fetch tool.

4. Capture the runner into a local const at the top of `streamChat` exactly
   as `mcpManager` already is, and additionally capture the resolved
   `LocalPdfToolContext` **once per request** so every round of the loop
   resolves against the same document identity. If the identity changes
   mid-flight, subsequent local tool calls must return a typed error rather
   than silently reading a different PDF.

5. Emit no local tools when `describeContext()` reports no active PDF —
   same rule as (3), one predicate.

6. Derive `hasOutline` from the same captured context as (4), and treat
   "outline not yet parsed" as *has* an outline (conservative: withhold
   `search_pdf_anchor`) rather than as absent.

7. Add an explicit per-request page-fetch budget (distinct from
   MAX_RECURSION), and have the runner return a typed "budget exhausted"
   error that the model can answer around.
