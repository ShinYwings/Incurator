# Critique On Source-Pair And Claim Integrity Proposals

Date: 2026-06-11 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### R1 — Semantic hashes can silently merge distinct claims

Whitespace/case normalization is safe for prose but not enough for equations.
Algebraically similar formulas may differ in assumptions, direction, units, or
boundary conditions. A semantic hash must never be an automatic semantic merge.

### R2 — A support validator can become a second hallucinating LLM

If support verification is model-only, the system merely moves hallucination
from extraction to validation. Deterministic expected spans and human-labeled
holdouts must remain the release oracle.

### R3 — `source_spans.metadata` can become an unqueryable junk drawer

Recovery candidates have lifecycle, provenance, and possibly multiple attempts.
Embedding all of that in one JSON object may make reconciliation and DB sync
fragile. Normalize it if experiments show multiple candidates or indexed audit
queries.

### R4 — Source-level transactions can be falsely atomic

SQLite rollback does not roll back projection files, model calls, or external
cache writes. The design needs staging plus publish/commit semantics, not only a
database transaction.

### R5 — Retiring stale units without downstream closure is corruption

Graph entities, relations, reports, synthesis, projections, dependencies, and
search rows can retain retired claim content. Reconciliation must prove closure,
not merely mark a unit retired.

### R6 — Formula centrality can bloat every claim

Prompt instructions to preserve formulas may duplicate long derivations. The
contract needs concise claim text plus an exact formula evidence reference as a
valid outcome.

### R7 — Recovery can produce cleaner but false LaTeX

A plausible recovered equation is dangerous. Low-confidence recovery must never
become verified automatically because it parses.

### R8 — Existing `source_span_ids` broad fallback can survive indirectly

Removing one fallback in report/synthesis code is insufficient if prompts receive
an over-broad allowed span set and cite arbitrary real spans.

## 2. Suggested Alternatives

- Use semantic hashes for reconciliation candidates, never unconditional merges.
- Require minimal-support labels and negative distractor spans in fixtures.
- Stage DB rows and projections under a compile-run id, then atomically promote
  the authoritative generation; clean failed staging deterministically.
- Define formula recovery as `candidate`, `reviewed`, or `rejected`.
- Pass claim-scoped support into graph/report/synthesis prompts instead of the
  whole source/community span pool.
- Make downstream closure audit a release gate.
