# Serving Architecture Proposal: One Context Service And Query Transaction

Date: 2026-06-11 | Agent Persona: lead_architect
Status: DRAFT PROPOSAL

> **Consensus scope transfer:** ContextService, progressive packs, public
> adapters, and feedback are owned by `../F_agent_context_service.md`. Plan A
> retains the retrieval coordinator, authoritative `RTR-*` child execution,
> selected-evidence result, provenance, and locator handoff required by it.

## 1. Core Logic & Implementation

### Entry contract

Program 3 accepts only trusted Program 2 records with:

- stable record identity and kind/layer;
- truth/authority and freshness state;
- minimal supporting source spans;
- immediate derivation dependencies;
- structured source locator candidates;
- dependency/search epoch identity.

Serving rejects or explicitly labels provisional/stale/unsupported evidence. It
does not attach broad upstream spans to make an item appear grounded.

### One backend `ContextService`

All query surfaces delegate to one service:

| Operation | Purpose |
|---|---|
| `context_manifest` | compact vault map, source/layer/index health, recent changes |
| `context_fetch` | initial bounded evidence pack |
| `context_expand` | expand selected handles under a new budget |
| `context_verify` | inspect exact claim/source lineage and contradictions |
| `context_feedback` | submit relevance/correction/stale/new-insight/promotion feedback with lineage |

Existing names can remain as external compatibility surfaces only if they
delegate to the service:

- `search_curator` exposes raw ranked search where appropriate;
- `curator_fetch_context` exposes a normalized pack;
- `curator_query` synthesizes over that same pack;
- CLI/plugin JSON and Obsidian grounding consume the same normalized result.

### One authoritative retrieval child execution

Final consensus: Program 1 supplies the root-QTR/snapshot substrate. Plan A
attaches one `RTR-*` child execution containing route, candidate, ranking,
selection, degradation, and stop detail. Plan F later owns root lifecycle for
context requests. Standalone diagnostic retrieval creates an explicit diagnostic
parent QTR through the Program-1 substrate.

```text
request
  -> policy/scope/freshness resolution
  -> route decision
  -> retrieval stages
  -> evidence selection and budget packing
  -> optional synthesis
  -> rendered locators / warnings / feedback lineage
```

Nested retrieval and prompt runs attach to the transaction. They do not create
unrelated top-level traces.

### Request seed

```json
{
  "query": "How is residual learning interpreted?",
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

### Response seed

```json
{
  "contract_version": "1",
  "pack_id": "PACK-...",
  "trace_id": "QTR-...",
  "snapshot": {
    "snapshot_id": "SNAP-...",
    "db_epoch": "...",
    "search_epoch": "...",
    "curate_spec_hash": "..."
  },
  "route": {"selected": "local", "reason": "..."},
  "policy": {"applied_filters": [], "excluded": []},
  "budget": {"limit_tokens": 6000, "used_tokens": 4310, "omitted_items": 7},
  "items": [],
  "next": [],
  "warnings": []
}
```

### Progressive disclosure

1. `manifest`: compact vault and quality map.
2. `index`: evidence cards with claims, authority, relevance, and locators.
3. `excerpt`: bounded supporting excerpts and nearby context.
4. `source`: exact raw source span/page/block and full lineage.

Expansion requires `pack_id`, handles, a new budget, and expected snapshot id.
A changed snapshot returns a conflict instead of mixing evidence epochs.

## 2. Pros & Cons

### Pros

- Gives every client one truth-preserving backend contract.
- Supports codebase-like progressive context use.
- Makes trace, policy, budget, and freshness explicit.
- Keeps backend answer synthesis optional.

### Cons

- A unified service touches backend, MCP, plugin, and documentation contracts.
- Snapshot/expansion state adds lifecycle complexity.
- Existing compatibility surfaces require careful migration or removal.
