# XC-1 Command Domain Analysis

## Constraints

`commands/` contains 67 broad handlers. Most of `commands/plugin.py` are public
JSON boundary adapters and intentionally convert unexpected failures to
`{ok:false,error}` plus exit status; they are out of scope. Silent sites occur in
optional Node/NVM setup, authentication launch, persona auto-evolution, model
retry fallback, and build-manifest loading.

## Decision

Narrow deterministic filesystem/JSON/subprocess setup failures where possible.
For optional external CLI launches, preserve non-fatal flow and emit `_warn` or
module debug detail. Keep plugin command envelopes byte/shape compatible.

## Pseudocode

```python
try:
    optional_step()
except EXPECTED_OPERATION_ERRORS as exc:
    logger.debug("optional step skipped: %s", exc)
    preserve_existing_fallback()
```
