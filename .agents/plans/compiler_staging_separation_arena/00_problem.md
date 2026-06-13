# Briefing: Staged/Authoritative Row Separation For The Source Compile Generation

Date: 2026-06-13
Origin: Plan B P6 review Flaw 3 (`.agents/USER_REPORT.md`). User chose the
spec-literal "staged-row separation (copy-on-stage)" approach over dual-context
eligibility.

## Problem

SYSTEM_BEHAVIOR §26.3 + SEARCH_ENGINE_SCHEMA §10.1 require:

> Query, evidence, and search surfaces read only authoritative-generation rows.
> Staged rows are invisible everywhere outside the compiler. Rows, dependency
> records, markdown projections, and search-derived state for the scope publish
> together or not at all.

Plan B P6 shipped staged compiler generations (`GEN-`) as a publish/audit/
idempotency **marker**, but did NOT enforce read-visibility: a unit's
`generation_id` is set in place and `list_eligible_knowledge_units` (the serving
+ compiler eligibility query) filters only `retired_at IS NULL AND
support_status='verified'`. Consequently a verified unit attributed to a NOT-yet-
authoritative (staged) generation — or one whose generation later fails the
publish gate — can be read by serving surfaces. The compiler mutates one row set
in place, so there is no separation between a staged row version and the
authoritative one.

## Constraints (from the codebase + frozen specs)

1. **Idempotency (§26.3):** unchanged source + same prompt contract reuses the
   authoritative generation's claim ids/hashes/counts. The current
   `recompile_source` short-circuits on an unchanged `content_hash` fingerprint
   (no staging happens), and this MUST be preserved.
2. **Stable-id reuse (§26.4):** `reconcile_source` reuses a prior stable
   `knowledge_unit` id for an unchanged claim after an edit; materially different
   claims retire. Stable-id reuse must survive the new staging model.
3. **knowledge_units PK is `id`** — a single physical row per logical unit. Two
   rows (staged + authoritative) for the same claim cannot share an id.
4. **Search-derived state is part of the generation (§10.1):** `search_documents`
   / `search_chunks` (PK `(record_type, record_id)` / `chunk_id`) and the ATM
   markdown projections on disk must also be staged and swapped atomically; a
   discarded generation must leave the prior search/projection state untouched.
5. **Compiler-internal reads vs serving reads:** `compile_source_l2` builds ATM
   pages, the graph, and search materialization FROM the units it just staged —
   so the compiler must be able to read the staged generation, while serving
   must not.
6. **SQLite single-process, no concurrent compiler.** Atomicity is achievable
   within a single transaction; we are not solving multi-writer concurrency.
7. **No backward-compat shims (repo invariant).** Legacy units with
   `generation_id IS NULL` (pre-v8 / P3 backfill) need a one-time migration to a
   synthetic authoritative generation, not a permanent NULL escape hatch.
8. **Plan-B scope only:** per-source L2 (knowledge_units + claim_supports + their
   dag_edges/artifact_dependencies + ATM projection + KU search docs). L3/L4
   community/synthesis are graph-derived = Plan C; explicitly out of scope.

## Success criteria

- A staged generation's units / claim_supports / ATM pages / search docs are
  invisible to query/evidence/search until the generation publishes.
- Publish flips DB rows + dependencies + projections + search materialization
  together; discard removes all staged artifacts and leaves the prior
  authoritative generation and its served state byte-identical.
- The P6 oracles stay green: unchanged-rebuild idempotency, failed-compile-no-
  partial-publish, F7 stale-span reconciliation, the compiler audit + lint
  surface, and F10 hydration.
- The compiler audit asserts zero staged rows visible in any served surface
  (SCHEMA §20.5 #4 strengthened to "zero staged rows visible to query/search").

## Open questions for the debate

- Single-table generation-filtered visibility vs physical staging tables?
- How is search materialization staged + swapped without leaking staged docs?
- ATM markdown projection: stage on disk (staging dir) or defer write to publish?
- Migration of legacy `generation_id IS NULL` units.
- Where does stable-id reuse happen now — at stage time or at publish time?
