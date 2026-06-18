# Architectural Code Review: Progressive Disclosure Budget Thrashing

## Target
`backend/src/curator/context_service.py` -> `context_expand()`

## Vulnerability Description
The progressive disclosure mechanism introduces a severe risk of infinite agent looping (Token Thrashing) due to how budgets are enforced during expansion.

### Code Reference
```python
        matched = [item for item in candidates if item.get("expansion_handle") in wanted]
        selected, omitted, budget = _budget_payloads(matched, limit_tokens=limit_tokens)
        # ...
        "next": [
            {
                "handle": item["expansion_handle"],
                "reason": "budget",
                "item_id": item["record_id"],
                "snapshot_id": current_snapshot_id,
            }
            for item in omitted
        ]
```

### Deep Analysis
1. **Missing Rejection Signal:** If an agent requests expansion for 5 handles, but the `limit_tokens` only allows 1 to be packed, the remaining 4 are silently pushed into the `omitted` list. 
2. **Infinite Loop Condition:** The `context_expand` response returns `ok: True` and provides `next` handles for the 4 omitted items with `reason: "budget"`. An autonomous agent (like Claude or the internal Obsidian agent) executing a `while next_handles:` loop will immediately request expansion for those 4 handles again. Since the budget hasn't changed, 1 will be packed, 3 omitted. If the budget is smaller than a single item, it will loop forever.
3. **Lack of Agent Context:** The agent has no programmatic way to distinguish between "I haven't asked for this yet" and "I asked for this, but the server refused it due to budget constraints."

### Recommended Rewrite
The `ContextService` must explicitly flag handles that were requested but rejected due to budget, rather than treating them as standard "next" handles. 
Add an `expansion_refused` or `budget_exhausted` array to the response payload so the agent knows to stop attempting to expand those specific handles in the current budget cycle.
