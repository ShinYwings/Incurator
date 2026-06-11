# Problem Definition: Unified Agent Context Service

Date: 2026-06-11
Status: DRAFT — Program-3 architecture planning only; no implementation until dependencies and approval gates pass

## 1. Program Position

This Arena defines the Program-3 unified `ContextService` for external agents and
the Obsidian agent. It depends on merged Program-1 truth/observability contracts
and merged Program-2 compiler integrity. It must not start implementation on the
current untrusted substrate.

## 2. Objective

Give every agent one bounded, progressive, freshness-aware, source-grounded way
to inspect and reuse vault knowledge.

External MCP clients, plugin CLI clients, the Obsidian sidechat agent, and
backend answer synthesis must consume the same normalized evidence-pack contract.
Client-specific presentation may differ; retrieval truth, policy, provenance,
budgets, snapshots, and feedback lineage may not.

## 3. Current Failure To Eliminate

- `curator_fetch_context`, `curator_query`, raw search, plugin JSON, and Obsidian
  grounding do not share one authoritative context transaction.
- Search evidence can lose `source_span_ids` during evidence assembly.
- Hybrid retrieval and orchestration can create disconnected `QTR-*` traces.
- KRS policy is not enforced consistently through every route.
- Global and source-scoped routes can be unbounded or query-independent.
- `EvidencePack.evidence_block()` uses a fixed character cutoff rather than an
  explicit token budget and omission contract.
- Progressive expansion and snapshot conflict handling do not exist.
- The Obsidian agent often injects a synthesized backend answer into another
  reasoning model instead of grounding it with the exact evidence pack.
- Feedback, correction, stale reports, insights, and promotion do not yet share
  a complete pack/snapshot/evidence lineage contract.

## 4. Required Operations

- `context_manifest`: compact vault/source/layer/index health and change map.
- `context_fetch`: initial bounded evidence pack for a query/purpose.
- `context_expand`: expand selected handles under a new budget and the same
  expected snapshot.
- `context_verify`: inspect exact claim/source/dependency/contradiction lineage.
- `context_feedback`: record relevance, incorrectness, staleness,
  insufficiency, duplication, new insight, correction, or promotion request with
  full lineage.

Existing public names may remain as compatibility surfaces, but they must
delegate to the same service.

## 5. Core Invariants

1. One request creates exactly one authoritative query/context transaction.
2. Every selected source-supported item has resolvable record and minimal source
   evidence ids.
3. Every route applies the same KRS, scope, authority, freshness, and budget
   policy.
4. Context packs are snapshot-bound and expansions cannot silently mix epochs.
5. Token accounting is explicit, model-aware where possible, and conservative
   when the tokenizer is unavailable.
6. Omitted evidence is reported and expandable; truncation is never silent.
7. External and Obsidian agents receive semantically equivalent normalized packs.
8. Feedback never mutates source truth silently and always retains lineage.

## 6. Non-Goals

- No Program-2 compiler, entity-resolution, hierarchy, or formula work.
- No autonomous edits to source/reference spaces.
- No unbounded agent loop or web fallback presented as vault truth.
- No requirement that agents use backend answer synthesis.
- No compatibility shim that preserves divergent retrieval behavior.
- No implementation until Program-1/2 dependencies and static specs are approved.

## 7. Completion Criteria

- All public query/context surfaces delegate to one `ContextService`.
- Pack, item, snapshot, budget, expansion, verification, and feedback contracts
  are versioned and tested.
- Every route is bounded, policy-enforced, snapshot-consistent, and traceable.
- External MCP and Obsidian normalized packs are equivalent for the same request.
- The Obsidian Sources & Trace UI renders the exact pack used for reasoning.
- Feedback and promotion retain originating trace, pack, snapshot, target, and
  reviewed evidence lineage.
