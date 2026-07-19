# XC-1 Silent Exception Hardening Briefing

Date: 2026-07-19

## Problem

The 2026-06 diagnosis counted broad exceptions against the pre-CM-1 monoliths.
The current code is split into `commands/`, `mcp/`, and `plugin_api/`, but still
contains 67, 69, and 12 broad handlers respectively. An AST audit found 28
handlers whose bodies are syntactically silent (`pass`, `continue`, or empty
return). They mix four different intents:

1. expected parse/filesystem fallbacks that should catch specific exceptions;
2. optional feature degradation that should be observable through logging or an
   existing warnings channel;
3. cleanup paths where arbitrary client implementations may fail and a broad
   catch is justified, but must be documented/logged;
4. process/transport boundaries where broad catch-and-envelope behavior is
   intentional and out of scope for this slice.

Blind replacement would be dangerous: MCP stdout must stay protocol-clean,
plugin JSON envelopes must remain stable, and best-effort startup must not become
fatal. The patch must distinguish those contracts rather than chase a raw count.

## Success Criteria

- Every silent broad handler in the three target packages is classified.
- In-scope handlers are narrowed or made observable with module logging/existing
  warnings, while boundary envelope handlers remain unchanged.
- A static test prevents new unexplained silent broad handlers.
- Targeted failure-injection tests prove fallback outputs and exit/envelope
  behavior are unchanged.
- No DB/schema, MCP tool signature, plugin JSON envelope, or CLI command change.
