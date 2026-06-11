# Problem Definition: Current-System Failure Atlas And Quality Observatory Groundwork

Date: 2026-06-11
Status: DRAFT ARENA BRIEF - planning only; no implementation is authorized
Program: Program 1 - Truth Contract & Quality Observatory
Batch: D - current-system diagnosis, failure reproduction, and observatory groundwork

## 1. Objective

Establish a reproducible, evidence-backed account of how the current Incurator
RAG + DAG system behaves before changing compiler or serving architecture.

This batch must turn each suspected defect into one of four explicit outcomes:

1. reproduced defect with a minimal fixture, captured trace, metric, and exact
   pipeline boundary;
2. disproven concern with repeatable counter-evidence;
3. accepted current limitation with a written contract and user-visible warning;
4. approved downstream requirement assigned to Program 1 observability,
   Program 2 compiler integrity, or Program 3 serving.

The deliverable is not a list of opinions. It is a quality observatory
groundwork package that later programs can use as their test oracle and
regression baseline.

## 2. Vault-As-Codebase Intent

Incurator must let agents use a notes vault with codebase-like discipline:

- inspect a compact manifest before opening large content;
- resolve a claim to stable records and exact source evidence;
- follow authored and derived dependencies without conflating them;
- reproduce a result against a known corpus/config/model snapshot;
- rerun quality checks after source changes;
- identify stale, unsupported, contradictory, or degraded knowledge.

The analogy does not permit forcing notes into code-symbol semantics. Human
meaning, authored topology, PDFs, headings, blocks, citations, formulas, and
external Reference Mode sources remain first-class evidence.

## 3. Current Reality To Diagnose

The existing umbrella Arena identified credible foundations and critical
suspicions:

- `state.sqlite` is authoritative; search and projections are derived.
- DB-native lexical/vector/RRF/rerank retrieval already exists.
- L1-L4 records, prompt runs, query traces, and artifact dependencies exist.
- `retrieval/evidence.py::_search_hits()` drops hydrated search-hit
  `source_span_ids`.
- `HybridEngine.search(..., persist=True)` and `QueryOrchestrator` can persist
  disconnected `QTR-` records for one logical request.
- `QueryOrchestrator` resolves `CurationPolicy`, but evidence construction does
  not receive or enforce the policy.
- global/source-scoped evidence routes are unbounded or query-independent.
- `EvidencePack.evidence_block()` uses a fixed 16,000-character cutoff.
- generated reports/synthesis may fall back to broad upstream span sets.
- rebuild idempotency, atomicity, stale reconciliation, and dependency closure
  are not proven.
- current testbed assets retain retired EXH/qmd assumptions and cannot be
  accepted as the current architecture's oracle.

These are hypotheses until this batch records reproducible evidence.

## 4. Core Questions

### Truth and lineage

- Does every selected evidence item preserve its authoritative record id,
  minimal supporting span ids, and exact locator?
- Does a cited span contain evidence that supports the associated claim, rather
  than merely being a valid upstream span?
- Can one logical query be reconstructed from one authoritative transaction?

### Retrieval and policy

- Which query families succeed or fail under full-quality and degraded modes?
- Does `curate.yml` inclusion/exclusion policy govern every evidence route?
- Are source/global/explore routes bounded, relevant, and deterministic?

### Compiler and update behavior

- What happens after edit, delete, rename, split, failed build, unchanged
  rebuild, policy change, or source drift?
- Which authoritative and derived records become stale or duplicated?
- Does regeneration stay within the correct dependency closure?

### Client parity

- Do MCP, CLI, backend answer synthesis, and Obsidian provider grounding consume
  equivalent evidence for the same request?
- Are answer links real locators or display strings that only look actionable?

## 5. Scope

This Arena plans:

- deep failure reproduction;
- a frozen diagnostic scenario suite and holdout partition;
- ground-truth labeling rules;
- an experiment manifest and evidence-bundle format;
- baseline metric collection;
- an approved classification and downstream handoff process;
- only the minimum observatory substrate required to measure later programs.

## 6. Non-Goals

- no retrieval-weight tuning;
- no new graph/community algorithm;
- no entity merge behavior;
- no formula-recovery implementation;
- no production compiler repair except a separately approved measurement blocker;
- no unified context-service implementation;
- no answer-link implementation;
- no quota/provider UI;
- no edits to source truth or external Reference Mode files;
- no implementation during this planning task.

## 7. Completion Definition

Plan D is complete only when:

- every umbrella failure F1-F13 has a stable status and evidence reference;
- every reproduced defect has a minimal fixture and boundary diagnosis;
- every baseline report declares corpus/config/model/provider/commit identities;
- deterministic and LLM-sensitive results are separated;
- holdout labels and human-review sampling are defined before thresholds;
- later Programs 2 and 3 can consume the evidence without reinterpreting it;
- no production behavior was changed merely to make diagnosis pass.
