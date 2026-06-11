# Problem Definition: Retrieval, Provenance, And Resolvable Source Locators

Date: 2026-06-11
Status: DRAFT ARENA BRIEF - planning only; no implementation is authorized
Program: Program 3 - Agentic Query Serving & Sensemaking
Plan: A - retrieval, provenance delivery, and locator resolution

## 1. Objective

Produce trusted compiled prior knowledge through one bounded, reproducible,
policy-aware retrieval transaction. Every selected evidence item must retain
exact provenance and a resolvable locator for the downstream Plan-F
ContextService.

This batch is primarily a serving concern. It begins only after:

1. Program 1 has merged the truth/evaluation/observability substrate and frozen
   the serving quality suite; and
2. Program 2 has merged a trusted compiler that supplies stable identities,
   minimal claim-level support, freshness, and exact source locators.

Retrieval cannot manufacture trust that the compiler did not preserve.

## 2. Vault-As-Codebase Intent

The serving runtime should give an agent the notes-vault equivalent of:

- repository manifest and health;
- symbol/reference search;
- dependency traversal;
- opening only relevant files/ranges;
- exact source navigation;
- reproducible build/test state;
- bounded route and evidence selection.

Notes remain human-semantic evidence, not code symbols. Serving must preserve
authored topology, extracted relations, source truth, generated knowledge,
contradictions, PDFs, headings, blocks, citations, and external references as
distinct concepts.

## 3. Current Serving Failures To Resolve

- Search hits can lose `source_span_ids` when converted to evidence.
- One logical query can create disconnected retrieval/orchestrator traces.
- `curate.yml` policy is resolved but not enforced through every evidence route.
- global evidence is query-independent and source-scoped evidence can be
  unbounded.
- route evidence is not consistently bounded or query-relevant.
- downstream consumers can lose or reshape retrieval detail.
- current answer navigation parses PDF page/section strings but lacks a complete
  structured note/file/heading/block/PDF/external locator contract.
- current projection paths are display locators and cannot be treated as source
  truth.
- ranking changes are not yet gated by a frozen per-family evaluation suite.

## 4. Required User Outcomes

1. Plan F can consume one transport-neutral retrieval result without launching a
   second retrieval path.
2. Every selected source-supported item preserves record identity, minimal
   supporting spans, freshness, ranking explanation, and structured locator.
3. Every resolved locator either reaches the intended source location or visibly
   degrades to a valid broader target with a trace warning.
4. Retrieval changes improve targeted query families without sacrificing direct
   factual quality, citation quality, policy compliance, or boundedness.

## 5. Scope

- one authoritative `RTR-*` retrieval execution attached to the caller-owned
  root QTR and one internal result contract;
- policy-aware route selection and evidence assembly;
- exact provenance delivery and verification;
- structured source locators and resolution state;
- source-link validation and safe fallback;
- measured retrieval improvements after the baseline is frozen;
- explicit Plan-F handoff fixtures.

## 6. Non-Goals

- no serving implementation before Program 1 and Program 2 merge;
- no repair of unstable compiler identities or unsupported claims in serving;
- no automatic source edits to insert anchors;
- no fabricated anchors or guessed links;
- no graph-only retrieval;
- no automatic entity merge or community compiler changes;
- no eager summarization of all knowledge;
- no web fallback disguised as vault evidence;
- no quota/provider UI;
- no ContextService, progressive pack, public adapter, cross-client, or feedback
  implementation owned by Plan F;
- no implementation during this planning task.

## 7. Completion Definition

Plan A is complete only when:

- one authoritative retrieval execution records route, candidates, ranking,
  selected evidence, provenance, degradation, and stop reason under the
  caller-owned root QTR and snapshot;
- every route enforces KRS, scope, freshness, boundedness, and degradation rules;
- source-supported selected evidence is verifiable and locator-resolvable;
- link fallback never creates a working-looking invalid target;
- frozen Program 1/2 quality suites show no prohibited regressions;
- Plan F consumes the result without information loss or a second retrieval.
