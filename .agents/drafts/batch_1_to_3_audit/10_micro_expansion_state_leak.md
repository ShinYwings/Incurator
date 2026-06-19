# Micro-Level Code Review: Expansion State Machine Leak (Infinite Handles)

## Target
`backend/src/curator/context_service.py` -> `context_expand()`, `_append_context_action()`

## Vulnerability Description
The `context_expand` operation is an incomplete state machine. It logs an expansion action but fails to mutate the root trace's `omitted_items` list. This allows an agent to repeatedly expand the exact same handle infinitely, bypassing all token limits and creating phantom `CTXA-*` records.

### Code Trace & Line-by-Line Analysis
In `context_expand`:
```python
        trace, context = self._find_context_pack(pack_id)
        # ...
        candidates = list(context.get("omitted_items", [])) + list(context.get("selected_items", []))
        matched = [item for item in candidates if item.get("expansion_handle") in wanted]
        selected, omitted, budget = _budget_payloads(matched, limit_tokens=limit_tokens)
        # ...
        self._append_context_action(...)
```

In `_append_context_action`:
```python
        actions = list(context.get("actions", []))
        actions.append(action)
        updated_context["actions"] = actions
        retrieval_trace["context_service"] = updated_context
        db.insert_query_trace(...) # Overwrites trace in DB
```

1. **State Leak**: When `context_expand` successfully selects an item from `omitted_items` and budgets it into the new payload, it calls `_append_context_action` to record the event. However, `_append_context_action` ONLY appends to the `actions` array. It DOES NOT remove the expanded item from `context["omitted_items"]` or move it to `context["selected_items"]` in the database.
2. **Infinite Expansion Exploit**: If an agent calls `context_expand(pack_id="PACK-ROOT", handle="EXP-123")`, it receives the expanded text. If the agent calls the exact same function again, `self._find_context_pack` loads the root trace from the DB. Because `omitted_items` was never mutated, `"EXP-123"` is still in the `candidates` list! The system will happily re-expand it, re-budget it, and append another action.
3. **Database Bloat**: A malicious or looping agent can expand the same handle thousands of times, appending useless `CTXA-*` actions to the `QTR-*` root until the JSON payload exceeds DB column limits or crashes the serialization layer.

### Recommended Architectural Fix
The expansion operation must be purely functional, creating a NEW `ContextPack` state instead of mutating the root, OR it must correctly update the root state if it uses an event-sourcing model.
If using an event-sourcing append-only log (current design), `_find_context_pack` MUST replay all `CTXA-*` actions to compute the *current* state of `selected_items` and `omitted_items` before resolving candidates, rather than statically reading the arrays that were frozen during `context_fetch`.
