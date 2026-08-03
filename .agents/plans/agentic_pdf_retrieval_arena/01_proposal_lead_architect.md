# [Agent Runtime] Proposal: Local Closed-Set PDF Tools

Date: 2026-08-03 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### A. Tool policy gains a third value (single decision point preserved)

`plugin/src/context/promptRegistry.ts`:

```ts
export type ToolPolicy = "auto" | "none" | "local-only";
```

- `"auto"` (sidechat): MCP tools + local tools.
- `"local-only"` (popover): local tools ONLY. No MCP, ever.
- `"none"`: no tools at all. Retained as the hard-off value so any future
  ephemeral surface can still opt out completely, and so the CLI/no-manager
  paths keep a name.

`POPOVER_PROFILE.toolPolicy` moves `"none"` → `"local-only"`.

`messageUtils.ts` keeps ONE injection decision per tool family, side by side,
so they can never silently diverge:

```ts
export function shouldInjectMcpTools(policy, hasMcpManager, useCli) {
  if (policy === "none" || policy === "local-only") return false;
  if (useCli) return false;
  return hasMcpManager;
}

export function shouldInjectLocalTools(policy, hasLocalRunner, useCli) {
  if (policy === "none") return false;
  if (useCli) return false;            // locked user decision
  return hasLocalRunner;
}
```

### B. Local tool definitions are pure data

New module `plugin/src/agent/llm/localPdfTools.ts` — pure, no I/O, unit-testable:

```ts
export const LOCAL_PDF_TOOL_NAMES = ["fetch_pdf_page", "search_pdf_anchor"] as const;

export interface LocalPdfToolContext {
  pageCount?: number;
  currentPage?: number;
  hasOutline: boolean;      // gates search_pdf_anchor exposure
}

/** OpenAI function-format definitions, gated by context. */
export function buildLocalPdfTools(ctx: LocalPdfToolContext): ExposedTool[];

/** Pure argument validation → a typed request or a typed refusal. */
export function parseLocalPdfToolCall(
  name: string, rawArgs: string, ctx: LocalPdfToolContext
): LocalPdfToolRequest | LocalPdfToolError;
```

`search_pdf_anchor` is emitted **only when `hasOutline === false`** (the
no-map fallback from the briefing §5). `fetch_pdf_page` is always emitted.

Bounds enforced in `parseLocalPdfToolCall`, not at the call site:
- `page_number` must be a finite integer, `>= 1`, and `<= pageCount` when known.
- Out-of-range / unparseable args return a typed error the loop feeds back as
  a `role: "tool"` message, so the model self-corrects instead of the turn dying.

### C. Execution is a narrow injected interface

```ts
export interface LocalPdfToolRunner {
  fetchPage(pageNum: number): Promise<string | undefined>;
  searchAnchor(query: string, topK: number): Promise<PdfRagHit[]>;
  describeContext(): LocalPdfToolContext;
}
```

`main.ts` supplies the only implementation, wrapping the **already existing**
`fetchActivePdfPage` / `getActivePdfDocumentIndex`. No new transport, no new
filesystem reach, no vault access — the runner cannot express anything except
"give me page N of the currently open PDF" and "BM25 over pages already seen".

### D. Loop dispatch: one router, two families

`LLMClient.streamChat`'s existing `MAX_RECURSION = 5` loop is reused verbatim.
The only change is how a tool call is routed:

```ts
const localTools = injectLocal ? buildLocalPdfTools(runner.describeContext()) : [];
const activeTools = isLastTurn ? undefined : [...mcpTools, ...localTools];
// dispatch:
if (isLocalPdfToolName(tc.function.name)) { ...runner... }
else { ...mcpManager.callTool(route)... }
```

Both families produce a `role: "tool"` message, so the loop's existing
termination, last-turn-drop, and abort semantics are untouched.

### E. Prompt boundary wording

`boundaryConstraints` gains a `"local-only"` branch stating precisely what is
and is not permitted, replacing the blanket "NO tools" claim which will become
factually false for the popover:

> You have NO filesystem access and NO MCP tools. Never list, browse, create,
> or execute files, scripts, or shell commands, and never invent folder, file,
> or directory names. Your ONLY tool is a read-only reader for the PDF the
> user already has open: you may fetch a page by number to follow a reference.
> Answer from the provided context plus any page you fetch.

## 2. Pros & Cons

- **Pros**: reuses the existing bounded loop, the existing page-fetch stack,
  and the existing single-decision-point discipline; the popover's real
  security properties (no filesystem, no scripts, no vault, no MCP) are
  preserved and now stated *accurately* instead of approximately; tool surface
  is two functions, one of them context-gated.
- **Cons**: the v0.19.0 wording and its locking test must change, which is a
  contract edit requiring careful spec/guide sync; `ToolPolicy` grows a value,
  so every switch over it must be re-checked; the popover can now issue up to
  4 extra page fetches per turn (latency/cost), bounded by MAX_RECURSION.
