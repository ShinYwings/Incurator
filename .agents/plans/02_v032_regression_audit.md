# v0.32.0+ Stability Regression Audit — Remaining Plan

Updated: 2026-08-01
Status: ACTIVE — P1–P6 shipped through v0.40.0; P7 is in progress.

## Objective

Close the remaining confirmed release-chain defects as small patch releases.
Cross-check original release intent, merged diffs, tests, docs, and adjacent
failure transitions. Do not change schema or public contracts without stopping
and re-planning as a Minor release.

## Domain References

- `.agents/plans/C_retrieval_provider_analysis.md`
- `.agents/plans/02_v032_regression_evidence.md`

## P7 — Provider, MCP, And Process Lifetimes

- Use request-local cancellation for overlapping UI and CLI requests.
- Preserve selected model and augmented GUI PATH in non-streaming CLI calls.
- Dispatch MCP calls through a collision-free exposed-name map.
- Reject every pending request on shutdown and await bounded process exit.
- Add command-class timeouts and output limits without truncating legitimate
  long operations.

## P8 — Retrieval And Prompt Integrity

- Trace vector-query degradation explicitly, including vector-only failure.
- Require exact, finite embedding and reranker result cardinality.
- Attribute prompt traces to the provider/model that actually succeeds.
- Sort prompt versions numerically and reject malformed registrations.

## P9 — Final Release-Chain Dry Pass

- Re-read every v0.32.0–v0.39.x release row against final code.
- Run two consecutive dry passes per release.
- Fix newly confirmed findings in the smallest matching patch.
- Close only with no P0/P1 and every P2 fixed or explicitly queued with reason.

## P10 — Validation And Closure

For every patch: docs-first, failing tests first, full relevant local gates,
isolated testbed/Reference Mode smoke, version/changelog consistency, push, PR,
and latest-head CI. After the last merge, delete this plan and ledger and reset
RELAY through the repository's documented IDLE procedure.
