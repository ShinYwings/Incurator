# v0.32.0+ Stability Regression Audit — Active Evidence Ledger

Updated: 2026-07-31
Rollback anchor for remaining work: merged v0.39.1 `bc61fab`.

## Completed Boundary

- P1–P5 are complete and preserved in Git history.
- v0.39.1 closed source deletion, serving-state eviction, and deterministic
  post-publish projection recovery.
- Remaining work begins only after the higher-priority v0.39.2 hotfix.

## P6 Findings

- F14: corrupt `sessions.json` can be mistaken for missing state and later
  overwritten by defaults.
- F15: malformed secret storage can collapse to `{}` and lose credentials on
  the next write.
- F16: runtime status shallow-copy can expose nested legacy credentials.

Required proof: byte preservation, fail-closed saves, atomic serialized writes,
concurrent/interrupted write tests, synced-session merge tests, and recursive
redaction fixtures.

## P7 Findings

- F09–F13: shared cancellation, non-streaming CLI model/PATH drift, lossy MCP
  names, unsettled shutdown promises, and unbounded backend subprocesses.

Required proof: overlapping request tests, dismiss/abort tests, MCP collision
and restart tests, hung-process timeout tests, and legitimate long-command
tests.

## P8 Findings

- F08 and F19–F22: hidden vector degradation, short/invalid provider outputs,
  stale primary attribution after failover, and lexical prompt-version sorting.

Required proof: lexical fallback, vector-only failure, short/long/NaN provider
outputs, failover trace attribution, and v9/v10 ordering tests.

## Validation Record Template

Each patch appends: branch and merge-base; failing tests; changed contracts;
focused and full gate results; isolated testbed and Reference Mode results;
production-path restoration check; release commit; PR and latest-head CI.
