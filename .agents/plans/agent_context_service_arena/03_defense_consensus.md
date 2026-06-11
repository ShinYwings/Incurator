# Defense And Consensus: Unified ContextService Contract
Date: 2026-06-11 | Agent Persona: system_synthesizer

## 1. Defended Principles

- One backend context contract remains mandatory.
- Progressive, budgeted packs and snapshot-bound expansion remain mandatory.
- External and Obsidian clients must share retrieval truth and provenance.
- Feedback must preserve lineage and never mutate source truth silently.

## 2. Revisions Accepted From Red Team

1. `ContextService` is an application façade over explicit internal ports, not a
   monolithic implementation.
2. One root `QTR-*` and complete snapshot are owned by ContextService. Plan A
   attaches exactly one `RTR-*` child execution; ContextService never duplicates
   route planning, ranking, or retrieval execution.
3. Snapshot closure includes source/corpus, DB, search/index, policy, model/
   tokenizer, and relevant dependency epochs/hashes. Expansion supports typed
   conflict and explicit rebase/refetch.
4. Service budgets account for the pack only. Clients calculate remaining
   provider budget after system prompt, chat history, pinned/selected/local
   context, and tool overhead.
5. Cross-client parity means equivalent normalized backend pack for equivalent
   request/snapshot, not identical final prompts.
6. Packs expose omission categories, coverage/insufficiency warnings,
   contradictions, and prioritized expansion reasons.
7. Feedback is append-only and quarantined from truth/ranking effects until
   review and measured policy authorize use.
8. Compatibility surfaces must delegate completely and are covered by
   equivalence/deprecation tests.
9. Persistence defaults to ids, hashes, accounting, decisions, and minimum
   reproducibility data; raw excerpts follow explicit retention policy.

## 3. Locked Consensus

The target architecture consists of:

- one versioned normalized request/pack contract;
- one `ContextService` façade;
- internal ports for snapshot, policy, planning/retrieval, packing/budgeting,
  provenance validation, trace recording, verification, and feedback;
- one root transaction with ordered child actions;
- manifest → index → excerpt → source progressive disclosure;
- typed snapshot conflict/rebase behavior;
- transport-only MCP/CLI/plugin adapters;
- optional synthesis over the exact pack;
- append-only reviewed feedback lineage.

## 4. Dependency Consensus

Implementation cannot begin until:

- Program 1 truth/observability and evaluation contracts are merged;
- Program 2 provides trustworthy stable identities, minimal supporting evidence,
  structured locators, and freshness/invalidation behavior;
- static specs and guides define the target service contract;
- the user approves the Program-3 implementation plan.

## 5. Vulnerabilities & Flaws Resolved

- Removed duplicated route planning/retrieval execution from ContextService.
- Defined one root QTR/complete snapshot with one Plan-A `RTR-*` child.
- Separated backend-pack parity from client-local final prompts.

## 6. Suggested Alternatives Adopted Or Rejected

- Adopted a façade over explicit ports, progressive bounded packs, and
  append-only feedback lineage.
- Rejected a monolithic service, silent truncation, and mixed snapshots.
