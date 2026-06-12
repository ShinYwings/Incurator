# Program 1 Final Handoffs (D2, v0.7.0)

This is the final Program 1 handoff after D1 diagnosis, Plan E research, and
D2 observatory work. Downstream programs must satisfy the cited Failure Atlas
oracles; changing an oracle requires a new atlas-version decision.

## Program 1 Closure

- F1 retired: search-hit evidence preserves hydrated source-span provenance.
- F2 retired: one orchestrated request persists one authoritative QTR with its
  retrieval trace.
- F13 retired: the tracked testbed template is the current-architecture oracle.
- Frozen holdout Q06 has one valid no-tuning result after two transparently
  audit-invalidated methodology runs. All binding D2 metrics passed; see
  `D2_HOLDOUT_RESULT.yml`.

## Program 2: Evidence Compiler Integrity

Owned cases: F6, F7, F8, F9, F10.

- Zero synthesis broad-span fallbacks.
- Unchanged rebuild idempotency and correct mutation invalidation.
- Zero homonym false merges and bounded, meaningful graph communities.
- Authored topology is preserved.
- Full exact source evidence remains retrievable beyond preview windows.
- Adopt formula-preserving distillation; benchmark context-enriched chunks,
  denoised hierarchy, and selective formula recovery later.
- Reject whole-corpus heavy visual recovery as the default.

## Program 3: Agentic Query Serving And Sensemaking

Owned cases: F3, F4, F5, F11, F12.

- KRS policy governs every route.
- Global and source-scoped evidence is bounded and query-relevant.
- Context omissions are explicit and progressively recoverable.
- Iterative retrieval is bounded, stop-aware, and single-snapshot.
- Clients share normalized backend evidence while preserving client-owned
  immediate context.
- Adopt query-relevant global retrieval and progressive context disclosure;
  benchmark the other Plan E candidates later.
- Reject unfiltered graph-only PPR as a default.

## Shared Evaluation Contract

Every downstream release reports Recall@k, MRR, top-1 citation correctness,
citation completeness, provenance resolution, hard-negative outranks,
indexed-character cost, and latency separately per query family. Aggregate-only
and model-judge-only release gates are prohibited.

D2's frozen holdout covers direct-factual Q06 only. Programs 2/3 must add
pre-labeled, no-tuning holdouts for associative, source-scoped, and global
families before making release claims for those families.
