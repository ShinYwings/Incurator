# Operations Proposal: Protocol-Safe Observability
Date: 2026-07-19 | Agent Persona: Runtime Operations Reviewer

## 1. Core Logic & Implementation

Use module loggers for suppressed failures. `debug` is appropriate for optional
cleanup/fallback detail; `warning` is required when a requested user-visible
operation degraded. Never print diagnostics to stdout inside MCP stdio. Reuse
existing CLI `_warn` and structured `warnings` fields where already contracted;
do not invent a new envelope in this patch.

Official Python guidance supports this split: runtime errors should be raised,
while a long-running process that suppresses an error should use
`logger.error/exception/critical` as appropriate. Module-level loggers preserve
origin and allow handlers to route output safely.

## 2. Pros & Cons

Pros: failures become diagnosable without protocol corruption. Cons: logs alone
are not user-visible in every surface, so later slices may need contract-level
warning fields after separate approval.
