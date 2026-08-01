# v0.32.0+ Stability Regression Audit — Remaining Plan

Updated: 2026-08-01
Status: ACTIVE — P1–P7 shipped through v0.40.1; P8 is approved and active on
`release/v0.40.2`.

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

### P7 Review Follow-Up — Approved 2026-08-01

The user's `fix them` instruction approves this plan-first follow-up for all
four findings from the Codex review of PR #106 head `4b354fd`.

#### Objective

Make surface cancellation ownership and MCP restart framing match the existing
v0.40.1 contracts without adding settings, commands, persisted fields, or other
public API surface.

#### Non-Goals And Stop Conditions

- Do not introduce a generic task manager or alter provider selection.
- Do not make Obsidian `requestUrl` physically cancellable; prevent eager work
  when already aborted and keep the caller Promise cancellation-safe.
- Stop and re-plan if a new public setting, schema change, or provider contract
  is required.

#### Locked Decisions

- RF1: requests with an explicit caller signal own their cancellation and do
  not replace the legacy global pointer used by sidebar Stop/session actions.
- RF2: `streamChat` and `complete` reject cancellation both before and after the
  asynchronous launch hook, before any fetch, `requestUrl`, `spawn`, or
  `execFile` transport is constructed.
- RF3: Ollama streaming and non-streaming error mapping rethrows `AbortError`
  unchanged before reachability/request-error classification.
- RF4: every MCP generation starts with an empty protocol buffer, and stdout
  handlers ignore bytes unless their child is still the current generation.

#### Strict Gates And TDD Phases

1. P0 Contract: clarify the existing English/Korean guide and plugin schema
   language for RF1–RF4; no version change because v0.40.1 is unreleased.
2. P1 Red: add regressions proving sidebar abort ignores caller-owned work,
   already-aborted requests launch no HTTP/CLI transport, Ollama preserves
   `AbortError`, and stale MCP stdout cannot corrupt replacement startup.
3. P2 Green: implement only the four locked decisions and pass the focused
   provider/MCP/Quick Query suites plus TypeScript.
4. P3 Release proof: pass the complete plugin Vitest suite and production build,
   inspect the final diff, update the evidence ledger/relay, commit, and push to
   the same draft PR.

## P8 — Retrieval And Prompt Integrity

- Trace vector-query degradation explicitly, including vector-only failure.
- Require exact, finite embedding and reranker result cardinality.
- Attribute prompt traces to the provider/model that actually succeeds.
- Sort prompt versions numerically and reject malformed registrations.

### P8 Implementation — Approved 2026-08-01

The user's `go` instruction approves this phase of the already-approved
release-chain audit.

#### Objective

Make retrieval and prompt traces truthfully represent provider degradation,
reject structurally invalid provider responses before persistence or ranking,
and make versioned prompt selection deterministic beyond single digits.

#### Non-Goals And Stop Conditions

- Do not change ranking weights, lexical matching, vector similarity, schema,
  provider selection, or public command/config surfaces.
- Vector-only mode remains vector-only; a query-embedding failure returns no
  invented lexical candidates but records `fallback_mode=lex` and a stable
  `vector_failed` warning.
- Reject an invalid embedding batch atomically; do not persist a valid-looking
  prefix from a short/long/non-finite response.
- Stop and re-plan if the fix requires a schema or public configuration change.

#### Locked Decisions

- F08: vector query helpers return a typed outcome carrying data or a stable
  failure warning. Any runtime query-embedding failure disables later vector
  expansion attempts and records lexical degradation in hybrid and vec-only
  traces.
- F19: reranker scores must have exactly one finite numeric value per fused
  candidate. Invalid output preserves the complete RRF order and emits
  `reranker_failed`.
- F20: embedding output must have exactly one non-empty finite numeric vector
  per requested chunk. Invalid batches persist nothing and count every batch
  item as failed.
- F21: a completed prompt trace finalizes `model_provider` and `model_name`
  from the provider that produced its final response; a provider exception
  keeps the start-time attribution and never masks the original error.
- F22: prompt versions use `v<integer>(.<integer>)*`, are parsed into numeric
  tuples, and are sorted numerically for latest lookup and registry listing.

#### Strict Gates And TDD Phases

1. P0 Contract: synchronize the search, prompt, trace, and provider-output
   contracts in static specs plus English guides and their Korean pairs.
2. P1 Red: add regressions for hybrid/vec-only query embedding failure;
   short/long/NaN embedding and reranker output; successful failover trace
   attribution; v9/v10 ordering; and malformed prompt versions.
3. P2 Green: implement only the locked boundary checks and pass focused engine,
   embedding, prompt registry, prompt trace, and DB tests.
4. P3 Release proof: re-arm the consumed lexical holdout drift tripwire with a
   non-impact proof; pass all repository gates; document the isolated-test
   boundary; bump and release v0.40.2; push a draft PR; and verify latest-head
   CI.

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
