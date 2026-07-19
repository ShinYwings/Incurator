# XC-1 MCP Domain Analysis

## Constraints

`mcp/server.py` contains 69 broad handlers and 23 silent sites. Tool-level
catch-and-return handlers are public MCP behavior and remain. Silent sites cover
path fallback, persona/client cleanup, suggestion generation, optional ingest
worker startup, record decoding, and daemon model provisioning. MCP stdout is
reserved for protocol messages.

## Decision

Use the module logger for internal degradation. Narrow JSON, filesystem, and
conversion sites; retain broad cleanup/client catches only with explicit reasons
and debug logging. Do not `print` warnings and do not change tool result schemas.

## Pseudocode

```python
try:
    value = parse_or_resolve()
except (OSError, ValueError, JSONDecodeError) as exc:
    logger.debug("MCP fallback used: %s", exc)
    value = fallback
```
