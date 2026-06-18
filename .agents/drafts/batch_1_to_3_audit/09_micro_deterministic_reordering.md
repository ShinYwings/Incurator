# Micro-Level Code Review: Deterministic Reordering (Rank Destruction) Bug

## Target
`backend/src/curator/context_service.py` -> `_selected_refs_from_payloads()`
`backend/src/curator/retrieval/orchestrator.py` -> `_run_answer_from_context()`

## Vulnerability Description
The system explicitly destroys the retrieval ranking order (BM25 + Rerank scores) of source spans right before feeding them into the LLM prompt for synthesis or validation, destroying the "Lost in the Middle" attention optimization.

### Code Trace & Line-by-Line Analysis
In `_selected_refs_from_payloads` (`context_service.py`):
```python
    return {
        "source_span_ids": sorted(source_span_ids), # <--- DESTRUCTIVE MUTATION
        "community_report_ids": sorted(community_report_ids),
        # ...
    }
```

In `_run_answer_from_context` (`orchestrator.py`):
```python
        if context_pack["route"] == "global":
            input_obj = contract.input_model(
                # ...
                valid_span_ids_block="\n".join(context_pack["source_span_ids"]),
            )
```

1. **Rank Obliteration**: `ContextService` receives an explicitly ordered list of `items` (sorted by `item.score` from the reranker). However, when it extracts the `source_span_ids` to track provenance, it casts them to a `set` and then calls `sorted()`, which sorts them alphabetically/lexicographically by UUID/Hash.
2. **LLM Attention Destruction**: When `QueryOrchestrator` passes `valid_span_ids_block` to the prompt validation logic, it passes this lexicographically sorted list. The most critical, highest-scoring span might end up buried in the exact middle of the list.
3. **Plan F Validation Failure**: P3 explicitly claimed: "retrieval now restores the original `span_ids` order before assembling items." While `_span_items()` was fixed, the `_selected_refs` utility downstream breaks it all over again.

### Recommended Architectural Fix
Provenance ID arrays MUST preserve the rank-order of their originating items.
```python
# context_service.py
def _selected_refs_from_payloads(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    source_span_ids: list[str] = []
    seen_spans = set()
    for item in items:
        for sid in item.get("source_span_ids", []):
            sid_str = str(sid)
            if sid_str not in seen_spans:
                source_span_ids.append(sid_str)
                seen_spans.add(sid_str)
    # Return the ordered list, do NOT use sorted()
```
