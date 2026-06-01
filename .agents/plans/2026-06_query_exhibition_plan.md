# Goal Description

The user clarified: "It is correct NOT to create L4 if there is no L3."
The goal is to fix the issue where `wiki query` or the Obsidian agent (via MCP) crashes and returns an error when there are no L3 Concepts present in the chat session. Previously, the pipeline aborted entirely if the generated answer didn't hit any `L3 Concepts`, raising a `ValueError`. This prevented agents from getting the answer back from the MCP query tool.

## Proposed Changes

### `backend/src/curator/query.py`

Modify `run_query` to catch the `ValueError` raised by `_save_curation_page` when no L3 Concepts are present. By catching this error silently, the query pipeline completes successfully, returning the synthesized answer back to the agent or CLI without attempting to save the invalid Exhibition.
This properly aligns with the rule that L4 Exhibitions MUST be grounded in L3 Concepts, while preventing the user-facing chat session from crashing.

#### [MODIFY] [query.py](file:///Users/shin/shinywings/Incurator/backend/src/curator/query.py)

```python
        except ValueError:
            # Skip saving silently if no L3 Concepts were found, preserving the query answer.
            pass
```

### `backend/tests/test_query_exhibition.py` (Updated File)

Modify the tests to ensure that `_save_curation_page` correctly enforces the presence of L3 Concepts by throwing `ValueError` in all cases when `core_concepts` is empty, confirming that the constraint remains intact.

## Verification Plan

### Automated Tests
- Run `uv run python -m pytest tests/test_query_exhibition.py -s`.
- Verify the test passes, demonstrating the strict `core_concepts` check is preserved.

### Manual Verification
- Ask the user to run `wiki query "test question" --curate` in the testbed or vault. Verify it answers successfully but does NOT generate a `04_Exhibitions/` session file when no L3 matches exist.
