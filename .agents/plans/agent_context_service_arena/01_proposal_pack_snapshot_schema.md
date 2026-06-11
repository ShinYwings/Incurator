# Schema Proposal: Versioned Evidence Packs And Snapshot Consistency
Date: 2026-06-11 | Agent Persona: schema_guardian

## 1. Core Logic & Implementation

Define versioned logical contracts before selecting physical tables.

### Request contract

```json
{
  "contract_version": "1",
  "query": "...",
  "workspace_path": "...",
  "purpose": "ground",
  "route": "auto",
  "scope": {"source_ids": [], "active_paths": []},
  "budget": {
    "max_tokens": 6000,
    "max_items": 12,
    "max_tokens_per_item": 700,
    "reserve_for_expansion": 1500
  },
  "detail": "index",
  "freshness_policy": "current_only"
}
```

### Pack contract

```json
{
  "contract_version": "1",
  "pack_id": "PACK-...",
  "trace_id": "QTR-...",
  "snapshot": {
    "snapshot_id": "SNAP-...",
    "db_epoch": "...",
    "search_epoch": "...",
    "policy_hash": "...",
    "model_config_hash": "...",
    "created_at": "..."
  },
  "route": {"selected": "local", "reason": "..."},
  "policy": {"applied_filters": [], "excluded": []},
  "budget": {
    "limit_tokens": 6000,
    "used_tokens": 4310,
    "reserved_tokens": 1500,
    "omitted_items": 7,
    "estimation_mode": "tokenizer"
  },
  "items": [],
  "next": [],
  "warnings": []
}
```

Every item carries stable record identity/hash/kind/layer, compact claim,
authority/truth/freshness state, ranking contributions, structured locator,
minimal supporting spans, immediate dependencies, token cost, and expansion
handles.

### Snapshot rule

Expansion requires `pack_id`, handles, new budget, and `expected_snapshot_id`.
Changed DB/search/policy/model epochs return a typed snapshot conflict. No route
may silently combine evidence from different snapshots.

### Persistence posture

- `QTR-*` is the authoritative context/query transaction.
- `PACK-*` may be durably persisted or reproducibly materialized from the QTR
  only after Program-1 evidence proves the correct storage choice.
- Expansion/feedback receipts must retain pack, trace, snapshot, and evidence
  lineage.

## 2. Pros & Cons

### Pros

- Makes context reproducible, inspectable, and cross-client compatible.
- Separates logical contract from premature physical schema.
- Prevents mixed-epoch evidence and silent truncation.

### Cons

- Snapshot epochs and model/tokenizer identity add schema/API complexity.
- Persisting full packs can increase storage; reconstructing them may fail if
  underlying state changes.
- Strict conflicts require explicit client retry UX.
