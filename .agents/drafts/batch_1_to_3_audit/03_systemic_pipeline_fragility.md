# Systemic Architectural Review (Batch 3): Strict Pipeline Fragility

## Target Scope
**Batch 3 (Program 3)**: Agentic Query Serving & Sensemaking (Plan A, Plan F)

## Architectural Vulnerability Description
The design of `ContextService` and the `QTR-*` / `SNAP-*` boundaries enforces mathematical purity at the cost of extreme **Pipeline Fragility**. It demands 100% metadata preservation across the entire stack.

### Deep Analysis
1. **The Domino Effect**: The system is designed so that Batch 3 (Serving) completely trusts the output of Batch 2 (Compiler), which in turn trusts Batch 1 (Truth Contract). If the Markdown parser (Batch 2) drops a single `span_id` due to a formatting quirk, the DB compilation succeeds but leaves an orphaned reference. When Batch 3 retrieves this, the `ContextService` strictly enforces locator validation. Because the locator is missing, the evidence is either discarded or raises an error.
2. **Snapshot Conflict Paralysis**: The `ContextService` enforces strict `expected_snapshot_id` validation during expansion (`context_expand`). If a background ingest worker finishes parsing a single changed file while an agent is mid-conversation, the `db_epoch` changes. The agent's next expansion request will be rejected with a `snapshot_conflict`. If the client doesn't implement a robust "rebase" or "refetch" logic, the agent gets permanently stuck and must start a new conversation.
3. **Over-Engineering UX Friction**: Forcing agents to interact via `manifest` -> `index` -> `excerpt` (Progressive Disclosure) assumes the agent is highly capable of planning its budget. Weaker models or context-starved agents will thrash, spending all their tokens requesting expansions rather than answering the user.

### Recommended Mitigation
1. **Graceful Degradation (Soft Snapshots)**: The `snapshot_conflict` error must be downgraded for non-overlapping data. If the DB epoch changed because "Note B" was edited, but the agent's current pack is only citing "Note A", the `ContextService` should allow the expansion (auto-rebase) instead of rigidly blocking the transaction.
2. **Pipeline Healing**: Implement an asynchronous `integrity_worker` that specifically scans the DB for orphaned `source_span_ids` or broken locators created by parser edge cases, automatically repairing or flagging them before they hit the synchronous `ContextService` path.
