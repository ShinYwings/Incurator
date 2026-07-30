# Domain Analysis B — DB Lifecycle, Compiler Publication, And Replica Convergence

Date: 2026-07-30
Confirmed findings: F01–F07, F17–F18.

## 1. Design Constraints And Invariants

- `state.sqlite` is authoritative; Markdown/search are derived.
- `wiki source rm` must remove or retire the complete derived dependency
  closure while keeping the source file unless explicitly requested.
- Generation publication is atomic: the schema contract says a partial
  authoritative publish is not representable.
- Authored relation membership authority is the exact sorted
  `audit_json.authored_relation_ids`, not relation-row LWW ownership.
- Every canonical status mutation advances its LWW revision monotonically.
- A source tombstone and a stale live row must converge under any application
  order, including a single surviving authoritative generation.
- Existing schema v13 is sufficient for all currently confirmed defects.

## 2. Confirmed Failure Modes

1. Source deletion leaves authoritative generations and knowledge units; search
   rematerializes deleted knowledge.
2. Generation reconciliation skips a single-generation/no-source group.
3. Authored lifecycle checks generation/source path but not audit membership.
4. Repair uses an equal maximum timestamp, so a peer rejects the corrected
   payload under strict-greater LWW.
5. Retirement can move relation/report clocks backward.
6. Endpoint-only report invalidation retires a winner report that already
   depends on newly imported topology.
7. Post-publish projection failure leaves authoritative DB plus partial ATM/DAG
   projection and stale search.
8. Markdown label nesting and double target decoding remain parser defects.

## 3. Alternatives And Trade-Offs

### Hard-delete every source-owned generated row

Simple locally, but canonical synced rows require tombstones and some retired
records are audit history. It also risks deleting shared graph entities and
relations supported by other sources.

### Add schema-v14 ownership foreign keys

Could make cascade ownership explicit, but is unnecessary for current schema:
`source_id`, generation audit, support rows, and artifact dependencies already
encode the closure. A migration would widen risk.

### Transactional lifecycle service over existing schema

Compute the exact closure in one connection, retire shared/canonical artifacts,
delete device-local rows, emit tombstones for hard-deleted canonical rows, then
materialize search after commit. Use a logical-clock successor for every repair.

## 4. Final Decision

- Implement a source-deletion closure helper over existing ownership and
  dependency tables; no schema change.
- Separate canonical retirement/tombstone emission from device-local hard
  deletion.
- Introduce one timestamp-successor helper used by reconciliation and retirement
  so `new_revision > all_observed_revisions`.
- Reconcile every authoritative source group, including size one and missing
  source rows.
- Make authored lifecycle require exact generation audit membership.
- Invalidate reports by dependency/revision, not endpoint membership alone.
- Treat post-publish projections as a retryable derived-state phase with stable
  persisted atom ids and a deterministic full re-emit on failure.
- Parse nested labels with bounded depth and decode each target exactly once.

## 5. SQL And Pseudocode

```sql
-- Serving units must never outlive their source.
SELECT ku.id
FROM knowledge_units ku
JOIN compiler_generations g ON g.id = ku.generation_id
JOIN sources s ON s.id = g.source_id
WHERE ku.retired_at IS NULL
  AND ku.support_status = 'verified'
  AND g.status = 'authoritative';
```

```text
delete_source(conn, source):
    closure = resolve_source_dependency_closure(conn, source.id)
    retire shared canonical artifacts with successor revisions
    tombstone canonical rows that are hard-deleted
    delete device-local jobs/pages/search derivatives
    delete source row
commit
materialize_search()
assert no served row references the removed source
```

```text
successor(observed):
    parsed = max(parse_utc(value) for value in observed)
    return format_utc(max(clock.now(), parsed + 1 microsecond))
```

