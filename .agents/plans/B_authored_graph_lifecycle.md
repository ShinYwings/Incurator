# Domain B — Authored Graph Lifecycle, Publication, and Consumers

Date: 2026-07-30
Status: LOCKED FOR v0.39.0 PLAN REVIEW

## 1. Design Constraints from the Codebase

- `graph_relations` already has `edge_class`, `lifecycle_status`,
  `topology_weight`, `generation_id`, and `source_span_ids`.
- `graph_relation_supports` encodes extracted KNU-backed evidence and its
  independent source-lineage rule.
- Existing upsert helpers do not accept explicit ids or all authored fields.
- Existing compiler publication is staged and transactional; new graph writes
  must join that transaction.
- Connected components use active relations. Community reporting assumes active
  relations have extracted factual supports.
- Relation-neighborhood traversal currently ignores lifecycle.
- Cross-device sync already includes graph tables by id.

## 2. Alternatives and Trade-offs

### A. Dedicated `authored_edges` table

Clear storage separation, but duplicates synchronization, lifecycle,
materialization, traversal, and deletion behavior. It also requires a schema
migration without proving the existing edge-class contract insufficient.
Rejected.

### B. Store authored links as extracted relations with synthetic supports

Avoids consumer changes, but falsely represents structure as corroborated fact
and violates the meaning of `graph_relation_supports`. Rejected.

### C. Existing table with edge-class-specific proof and consumer rules

Preserves one topology store while making the epistemic distinction explicit.
Requires precise lifecycle and report changes but no schema migration.
Accepted.

## 3. Final Decision

Extend graph upsert APIs with optional explicit identity and authored metadata.
Default behavior for extracted relations remains unchanged.

For `edge_class='authored'`, a relation is active only when:

- its source structure resolves exactly in a registered visible Markdown file;
- both endpoints have canonical portable identities;
- its `generation_id` is the current successful generation for the source;
- it has not been retired by edit, rename, or source deletion.

It does not require `graph_relation_supports`. For `edge_class='extracted'`,
the existing corroboration lifecycle remains unchanged.

Deterministic ids are derived only for F9-created note/asset/tag entities and
authored relations. `generation_id` plus the compiler-generation source join
is the ownership boundary. No new schema column is planned.

## 4. Publication and Reconciliation Pseudocode

```python
def publish_generation(conn, source_id, generation_id, staged_result):
    # Existing staged validation happens before this transaction.
    publish_extracted_outputs(conn, staged_result)

    previous = authored_relations_owned_by_source(conn, source_id)
    current_ids = set()
    for relation in staged_result.authored_relations:
        upsert_deterministic_entities(conn, relation)
        relation_id = upsert_authored_relation(
            conn,
            explicit_id=stable_relation_id(relation),
            edge_class="authored",
            lifecycle_status="active",
            generation_id=generation_id,
            assertion_source="source_states",
            source_span_ids=relation.source_span_ids,
        )
        current_ids.add(relation_id)

    retire(previous.ids - current_ids)
    mark_generation_current(conn, source_id, generation_id)
```

The whole transaction rolls back together. Source deletion invokes the same
source-ownership lookup and retires/deletes the source-owned authored rows in
the existing deletion transaction.

## 5. Consumer Contract

| Consumer | Authored active | Extracted active | Non-active |
|---|---:|---:|---:|
| Connected-component topology | yes | yes | no |
| Explore/memory path traversal | yes | yes | no |
| Community factual relation ids | no | yes, verified only | no |
| Community membership dependency hash | yes | yes | no |
| Factual source citations | no | yes, verified only | no |
| Inspection/materialized diagnostics | labeled | labeled | labeled |

Authored-only components do not emit fabricated factual reports. Backlinks are
incoming traversal over the single forward relation; no reverse duplicate row
is stored.

## 6. Required Failure Tests

- unchanged rebuild is byte/logically idempotent;
- link edit retires only stale source-owned edges;
- source deletion removes or retires all source-owned authored edges in the
  same transaction;
- rename publishes the new portable identity and retires the old outgoing set;
- failed compile preserves the prior current generation and authored set;
- two replicas compiling the same note converge to one logical row per endpoint
  and relation;
- ambiguous, hidden, external, traversal, code-block, and unresolved targets
  produce no edge;
- active-only traversal excludes quarantined and retired rows;
- authored topology changes community membership without entering factual
  report support.
