# Critique on XC-1 Proposals
Date: 2026-07-19 | Agent Persona: Red Team

## 1. Vulnerabilities & Flaws

- A static rule based only on `except Exception: pass` can be gamed by adding a
  log statement without narrowing the handler.
- Narrowing guessed exception tuples can expose undocumented third-party errors
  and turn optional startup into a crash.
- Warning logs from MCP may corrupt JSON-RPC if configured to stdout.
- Treating every close failure as warning can create noisy logs during normal
  teardown.
- Updating all 148 broad handlers in one patch would be unreviewable and could
  change dozens of public envelopes.

## 2. Suggested Alternatives

Keep the patch limited to the 28 silent sites. The policy test must carry a
reasoned allowlist and separately reject unlogged silent bodies. Use behavior
tests at each seam, logger-only diagnostics for MCP internals, and no new public
fields. Defer catch-and-return boundary review to a later XC-1 slice.
