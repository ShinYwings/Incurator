# XC-1 Plugin API Domain Analysis

## Constraints

`plugin_api/` contains 12 broad handlers but only one syntactically silent site:
topic classification in `promote_answer`. The documented behavior already has a
deterministic slug/category fallback. Other broad handlers form the plugin JSON
error boundary and are not part of this slice.

## Decision

Preserve promotion success when optional classification fails, but make the
failure observable through the module logger. Narrow only if the concrete LLM
and config exception contract is stable; otherwise retain a justified broad
catch at this optional third-party boundary.

## Pseudocode

```python
try:
    category, slug = classify(...)
except Exception as exc:  # optional classifier boundary
    logger.debug("topic classification unavailable; using slug fallback", exc_info=exc)
```
