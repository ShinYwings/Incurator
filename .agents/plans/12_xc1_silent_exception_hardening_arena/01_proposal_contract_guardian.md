# Contract Guardian Proposal: Classify Before Narrowing
Date: 2026-07-19 | Agent Persona: Contract Guardian

## 1. Core Logic & Implementation

Build an AST inventory test for broad handlers and classify each silent site as
`expected`, `best_effort`, `cleanup`, or `boundary`. Narrow `expected` sites to
the concrete parser/filesystem exceptions. Keep arbitrary-client cleanup broad
but add debug logging. Route user-relevant best-effort failures to existing
warning/log channels without writing to MCP stdout.

The public contract is the returned CLI/MCP/plugin payload, exit status, and
stdio cleanliness—not the absence of `Exception` text. Tests should inject each
failure at the owned helper and assert the same fallback plus new observability.

## 2. Pros & Cons

Pros: preserves compatibility, makes each handler explainable, and prevents raw
count reduction from introducing fatal regressions. Cons: some justified broad
cleanup catches remain, so success cannot be measured by zero broad handlers.
