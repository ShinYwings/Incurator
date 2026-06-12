# Client Routing Proposal: Explicit State-Gated Handoff
Date: 2026-06-12 | Agent Persona: Client Integration Engineer

## 1. Core Logic & Implementation

Replace implicit auto-indexing with an explicit state machine in provider-context
assembly:

```text
local viewer context exists
  -> use local PDF.js context
  -> status lookup may update badge, but never mutates source state

local viewer context missing
  -> read source status
  -> unregistered: read-only plugin pdf context fallback
  -> registered + l1_complete: request durable L1 context
  -> registered + l3_complete: durable L1 context + optional PDF RAG/query
```

Remove the `void client.registerSource(sourcePath)` passive mutation. Keep
`ingestPdf()` reachable only from Add Source badge/modal actions.

Extend `getPdfContext()` response with a serving marker such as
`contextSource: "ephemeral_parse" | "durable_l1"` and durable `toc_id` fields
where available. The plugin uses the marker for diagnostics and prompt labels;
it does not infer durability merely from `sourceTracked`.

Gate workspace-wide `curatorQuery()` when the active turn is a PDF-specific
question and the relevant source is unregistered or L3-incomplete.

## 2. Pros & Cons

Pros:
- Restores explicit approval and makes routing behavior testable.
- Preserves fast local PDF.js path.
- Does not block Add Source on L2/L3.

Cons:
- Requires a focused integration test around provider-context assembly, which
  currently lacks behavioral coverage.
- Workspace-wide query gating needs careful scoping so ordinary non-PDF vault
  questions continue to work.
