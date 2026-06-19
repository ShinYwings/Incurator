# Architectural Code Review: Locator Coupling & False Truth State

## Target
`backend/src/curator/context_service.py` -> `_item_locator()`, `_item_payload()`

## Vulnerability Description
The current implementation of `ContextService` exhibits a dangerous decoupling between the existence of a span ID and the actual physical resolution of that span, leading to a false `truth_state`.

### Code Reference
In `_item_payload`:
```python
"truth_state": "source_supported" if item.source_span_ids else "derived",
```

In `_item_locator`:
```python
    if item.source_span_ids:
        return StructuredLocator(
            source_id=None,
            source_kind="vault_markdown",
            # ...
            locator_status="unavailable",
        )
```

### Deep Analysis
1. **False Grounding:** The system marks an item as `source_supported` purely based on the presence of a string in the `item.source_span_ids` array, regardless of whether that ID actually exists in the database.
2. **Silent Degradation:** If the outer join in `_locator_map` fails (e.g., the span was deleted from the DB but the L2/L3 record hasn't been recompiled yet), `_item_locator` catches the `None` and invents a dummy `StructuredLocator` with `locator_status="unavailable"`. 
3. **Agent Crash Risk:** The agent receives an item marked as `source_supported` but with an `unavailable` locator. If the agent attempts to call a tool to expand or verify this source, the operation will fail at runtime because the `source_id` and `relpath` are `None`.

### Recommended Rewrite
The `truth_state` MUST be dynamically calculated based on the actual resolution of the locator, not just the presence of the ID. If the locator fails to resolve, the item must be downgraded to an error state or explicitly marked as `stale`/`unsupported`, and the pipeline must trigger a reconciliation event.

```python
# Proposed Fix Concept
resolved_locator = _locator_payload(_item_locator(item, locators_by_span))
if item.source_span_ids and resolved_locator.get("locator_status") == "unavailable":
    truth_state = "orphaned_support" # Explicit failure state
else:
    truth_state = "source_supported" if item.source_span_ids else "derived"
```
