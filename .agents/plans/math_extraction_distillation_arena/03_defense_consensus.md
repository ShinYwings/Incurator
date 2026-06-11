# Arena Defense And Consensus: Claim-Level Compiler Integrity

Date: 2026-06-11 | Agent Persona: system_synthesizer

## 1. Resolved Decisions

1. Raw source evidence remains immutable. Recovery is additive and cannot replace
   parser/source text.
2. Formula recovery is conditional on a measured parser/L1 loss boundary.
3. Recovery lifecycle is explicit: `candidate`, `reviewed`, or `rejected`;
   syntactic validity alone cannot verify a candidate.
4. `source_span_ids` remain required but are insufficient. Each
   source-supported claim needs minimal support records and a support verdict.
5. Claim semantic hashes support reconciliation candidates only. They never
   automatically merge semantically distinct claims.
6. Formula centrality permits two valid representations: concise claim text with
   the central formula intact, or concise claim text linked to exact formula
   evidence. Incidental formulas may be omitted with reason.
7. The implementation uses staged compile generations. SQLite rows,
   dependencies, projections, and search materialization publish only after all
   required compiler stages validate.
8. Reconciliation retires/removes stale source-derived records and invalidates
   the complete measured downstream dependency closure.
9. Claim-scoped evidence, not whole-source/community allowed-span pools, feeds
   downstream graph/report/synthesis generation.
10. Model-based support checking is secondary. Deterministic and human-labeled
    gold fixtures are release gates.
11. Existing rows are not silently marked verified. Migration backfills them as
    unchecked and rebuilds them under the new contract.
12. Plan B changes compiler integrity only. Entity resolution/hierarchy,
    retrieval tuning, agent serving, and quota remain excluded.

## 2. Required Implementation Contracts

- Program 1 evaluation and locator specifications are merged and frozen.
- Static schema and system behavior specs define support lifecycle, recovery
  lifecycle, staged compile generations, and reconciliation before code.
- Prompt contracts are versioned for minimal support and formula centrality.
- The compiler audit proves every active L2-L4 generated claim reaches minimal
  source support or an explicit unsupported/uncertain state.
- Failure injection proves no partial authoritative publish.

## 3. Stop Conditions

- Stop if Program 1 has not produced approved support labels and evaluation
  oracles.
- Stop if selective recovery cannot be distinguished from raw evidence.
- Stop if staging cannot cover projections/search-derived state.
- Stop if downstream dependency closure cannot be measured.
- Stop after three repeated QA failures and return to planning through the
  rollback strategist.

## 4. Vulnerabilities & Flaws Resolved

- Scoped broad-fallback removal so Plan C is not blocked by a circular gate.
- Rejected silent formula replacement and partial compiler publication.

## 5. Suggested Alternatives Adopted Or Rejected

- Adopted additive recovery, minimal support, and staged generations.
- Rejected always-on VLM extraction and semantic-hash auto-merge.
