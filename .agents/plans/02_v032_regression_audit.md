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

### P8 Review Follow-Up — Approved 2026-08-02

Source: [PR #107 review findings](../USER_REPORT.md#-user-inbox), reproduced
against head `a423a38` on 2026-08-01. The user's `fix them` instruction on
2026-08-02 approves implementation of RF5-RF7 on the existing PR branch.

#### 1. Objective

Close the remaining dimensional-integrity and response-attribution gaps without
changing schema, provider selection, ranking weights, or public command/config
surfaces.

#### 2. Explicit Non-Goals

- Do not add a generic provider result wrapper across every LLM client.
- Do not rebuild or mutate the unrelated active testbed or production vault.
- Do not treat arbitrary SQLite/search corruption as provider degradation;
  only typed vector compatibility failures degrade to lexical search.
- Do not bump past v0.40.2 while the patch remains unreleased.

#### 3. Strict Quality Conditions And Release Gates

- Every accepted corpus-embedding run has one dimension across all rows and
  batches; no mixed-dimension prefix is persisted.
- A query/index dimension mismatch records `fallback_mode=lex` and
  `vector_failed`, including vector-only mode.
- Prompt traces bind provider and model to the exact response used as final
  output, even if primary recovery or another request changes active state.
- Focused tests, full backend/plugin gates, docs/version consistency, and the
  re-armed frozen-holdout fingerprint test all pass.

#### 4. Locked Design Decisions

- RF5: `_validate_embedding_output` returns a validated dimension. `embed_corpus`
  pins one run dimension from the first accepted batch or compatible ready
  rows, rejects any later mismatch before writes, and validates every row in a
  batch against that dimension.
- RF6: vector search raises a typed compatibility error for query/index or
  mixed-index dimension mismatch. `_vector_list` catches only that typed vector
  compatibility failure and returns a stable `vector_failed` outcome; unrelated
  DB/programming failures still surface.
- RF7: failover chat returns response-bound provider/model metadata from the
  same provider-local success path. `run_prompt` retains that immutable snapshot
  for the original response and replaces it only when a repair response
  succeeds. Trace finalization accepts explicit strings rather than rereading a
  mutable client.

#### 5. Scope Exclusions And Stop Conditions

- **Exclusions**: schema migration, ranking changes, provider catalogue changes,
  and general request-context refactors.
- **Stop Conditions**: stop if response-bound provenance requires a public LLM
  client contract change outside `FailoverClient`/prompt runner, or if repairing
  pre-existing mixed-dimension rows requires destructive index mutation rather
  than a normal reindex.

#### 6. Evidence Ledger

- Repository head and rollback anchor: `a423a38`; worktree was clean before
  review planning.
- RF5, RF6, and RF7 are reproduced with temporary current-schema DBs and fake
  providers; no tracked data, testbed, or production path was touched.
- D2 is consumed. Engine/embedding edits require another explicit lexical-Q06
  non-impact re-arm; the holdout itself must not be rerun.

#### 7. Execution Phases

1. P0 Contract: clarify uniform embedding dimensions, typed vector compatibility
   degradation, and response-bound prompt attribution in English/Korean guides
   and static specs.
2. P1 Red: add failing tests for mixed dimensions within/across batches,
   query/index mismatch in hybrid and vec-only modes, background primary
   recovery during validation, and provider/model atomicity.
3. P2 Green: implement the three locked decisions; pass focused engine,
   embedding, vector, prompt trace, failover, and DB tests plus Ruff/mypy.
4. P3 Release proof: re-arm affected D2 hashes without rerunning Q06, run all
   repository gates, update changelog/evidence/relay, commit to PR #107, push,
   and verify latest-head CI.

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
