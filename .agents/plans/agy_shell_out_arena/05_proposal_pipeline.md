# Pipeline proposal: preserve the existing durable compiler, fix the provider boundary

Date: 2026-09-11 | Persona: pipeline/schema reviewer | Scope: E4 graph extraction

## Finding: the old all-batches-in-one-run premise is obsolete

The retained briefing describes the 2026-08-21 implementation, not the current
compiler. Current source already contains both changes its option C proposes:

- `backend/src/curator/pipeline/graph_index.py:63-75,249-289` retries raised
  exceptions for one batch up to 30 attempts. A client capacity block propagates
  immediately instead of consuming that retry budget. Exhaustion produces
  `GraphData(ok=False)` and the batch's reason; it does not silently succeed.
- `graph_index.py:149-237,300-321` reuses and persists validated graph batches
  using `(source_id, rendered_prompt.input_hash)`. Successful batches survive
  later refusal, capacity deferral, validation failure, or publish failure.
  `backend/src/curator/db/_entities.py:3391` commits each staged payload on its own
  connection. Only validated output is saved; refused output is never cached.
- `backend/src/curator/pipeline/compile.py:518-535,899-934` releases staged
  knowledge units for reuse when compilation fails. It preserves their support
  rows and discards the failed generation rather than deleting the extraction.
- `compile.py:441-492` rejects an incomplete graph and joins graph persistence,
  authoritative-generation publication, and cache deletion in one transaction.
- `graph_index.py:182-204` already scopes allowed span IDs to the batch. The old
  all-source-span prompt inflation was fixed too.

Consequently, the old `0.57**87` clean-run probability is not the probability of
current eventual publication. An unchanged subsequent compile reuses successful
batches and only asks for missing results. It still needs every batch validated
before publication, which is the correct completeness invariant. Claims that
current large sources are mathematically unpublishable must be removed from the
active E4 description rather than used to justify new storage infrastructure.

## Remaining defect and uncertainty

The provider still receives an agentic runtime for a structured extraction task.
Native structured output and a flattened schema reduce shell selection but do
not establish that shell access is unavailable. Historical observations show the
model sometimes tries to recover its supplied units from its transcript. That is
the provider-boundary failure to reproduce with the current installed CLI; a
second durable batch table cannot prevent it.

Current retry handling has a separate confirmed overbreadth:
`graph_index.py:261` catches **every** ordinary exception and repeats it 30 times
unless `capacity_blocked_for()` reports a positive delay. This includes missing
CLI, unavailable OS sandbox, invalid model, authentication failure, and local
trace/database exceptions. The 30-attempt cap was justified using a historical
stochastic permission-denial rate; it does not justify repeating deterministic
setup failures. `_run` allows each subprocess 900 seconds (`llm.py:1290`), so the
outer policy can also amplify a persistently slow failure. No probability claim
in a comment proves the current model has independent retry outcomes.

This proposal does not claim the current live model still exhibits the August
denial rate. No live provider invocation or user-vault access was made here.

## Proposed smallest safe design

1. Keep durable graph batches, generation lifecycle, batch boundaries, and atomic
   publication unchanged. No schema migration is necessary for a provider launch
   or exception-classification fix.
2. Use the provider review's measured tool-control mechanism, if the installed
   CLI exposes one, on structured extraction calls whose full input is supplied.
   Require a real test to prove that the production command accepts it and still
   yields useful validated entities/relations. Do not infer tool restrictions
   from `--sandbox`, `num_turns == 1`, or a correctly assembled argument list.
3. Keep the OS sandbox and permission boundaries. Do not substitute blanket
   approval, transcript access, arbitrary shell access, or provider rerouting.
   The graph compiler already has the necessary units; query/read capabilities
   have different requirements and are outside this extraction fix.
4. If E4 changes retry handling, classify failures at the provider boundary and
   retry only the intended transient/recoverable category. Distinguish model
   tool denial from authentication, missing executable, unsupported flags,
   sandbox unavailability, quota, and local implementation failures. Preserve
   capacity deferral. Avoid burying text-matching copies inside the compiler.
5. Preserve the existing bounded retry behavior for intermittent extraction
   failures until measurements justify changing its budget. Reducing 30 to an
   arbitrary number without an effective tool-control fix trades successful
   compilation for shorter failures. Permanent failures should exit promptly;
   that is a classification correction, not a change to batch completeness.

If current CLI tool control cannot prevent shell selection while preserving
valid extraction, report that limitation. Checkpointing already makes retries
survivable; presenting the same retry loop as a newly completed root-cause fix
would be inaccurate. Provider replacement or allowing arbitrary execution is a
separate product/security decision.

## Publication and resume invariants to retain

- A missing, denied, malformed, or semantically invalid batch prevents publication.
- The previous authoritative generation and graph survive any staging failure.
- A successful batch is durably reusable after a later batch or publish failure.
- Refusals and invalid output are never persisted as successful graph batches.
- Cache cleanup commits atomically with successful publication and rolls back if
  publication fails; it must use the same DB connection.
- Changed unit IDs, prompt content, or batch boundaries produce a cache miss;
  current diagnostics already identify a complete miss. Do not reuse a batch
  merely because its ordinal/source matches.
- Cached payloads reconstruct through the contract output model, retaining
  citations and optional relation fields; do not introduce a lossy dict adapter.

## Verification and discriminating regressions

Executed against the current code, with fake providers and isolated test DBs:

```text
scripts/backend-check pytest \
  backend/tests/test_entity_relation_extraction.py \
  backend/tests/test_graph_resume.py \
  backend/tests/test_graph_batch_results.py \
  backend/tests/test_graph_batch_span_scope.py \
  backend/tests/test_compile_pipeline.py

52 passed in 4.27s
```

These cover a refusal then success, refusal exhaustion, immediate capacity
propagation, reuse of only missing graph batches, uncached refusals, durable
staging, publish rollback, successful cache cleanup, KU reuse after graph
failure, and per-batch span scope. They demonstrate that option C and durable
resume already exist; they do not prove live agy accepts a new launch policy.

New tests should discriminate behavior rather than repeat argument construction:

1. Current provider invocation + real graph contract: a representative supplied
   units batch returns valid, nonempty grounded output without shell execution.
   Use an isolated fixture and existing OS containment; never reindex the vault.
2. Fake executable attempts a prohibited action and returns a denial: no file is
   created, no incomplete graph publishes, validated earlier batches remain.
3. Permanent provider/setup failure is invoked once; ordinary programming/DB
   exceptions are not multiplied into 30 provider attempts.
4. Intermittent typed denial followed by valid output still completes; capacity
   remains deferred immediately. Persist and resume an earlier successful batch
   while exercising this actual exception path through `compile_source_l2`.
5. If a shared provider exception type is introduced, exercise configured
   `FailoverClient` as well so attribution, fallback policy, and capacity state
   are not lost when wrappers propagate the classification.

## Cross-critique questions

- Does the installed agy CLI offer a tool-disable control that is distinct from
  sandboxing/approval, and is that control actually effective with JSON schemas?
- If it does, why change the graph schema or retry cap in the same release?
- If it does not, what measured behavior distinguishes a retryable model denial
  from deterministic CLI configuration failure?
- Does a proposed solution silently alter the query/vision tool capability when
  only the supplied-input extraction path needs no execution?

## Cross-critique of the independent provider proposal

Read `05_proposal_provider.md`. Its exit-zero explicit ERROR observation is a
stronger immediate correctness bug than the stale E4 probability argument. An
error envelope must be rejected before its payload can become a cached valid
empty graph. The graph compiler should not compensate by treating all empty
graphs as errors: a successful extraction can legitimately be empty. The
transport/provider boundary knows the distinction and must preserve it.

The lead's current isolated exact-contract probe reportedly succeeded in 13.5
seconds with 4 entities, 3 relations, and `num_turns=2`. This is evidence against
the old claim that a successful structured call necessarily has one turn. It is
one successful sample, not a tool-disable guarantee or denial-rate estimate.

For the smallest retry fix, prefer an internal typed recoverable provider error
over a new setting or policy schema. Graph extraction checks active capacity
first, retries explicitly eligible errors with its existing bound, and lets
permanent/unexpected exceptions reach the compile failure boundary immediately.
Provider error classification belongs beside interpretation of the actual
stderr/envelope, not in a broad compiler substring search. Existing tests that
model a refusal with bare `RuntimeError` should use the actual typed provider
failure and retain proof of retry and resume.

One additional integration trap: `FailoverClient.chat_with_provider`
(`llm.py:1978-1984`) wraps exhausted delegates in a generic `LLMError` chained
only to the **last** provider. Checking only the outer exception loses typed
retryability. Merely walking `__cause__` also misses an earlier recoverable agy
denial followed by a permanently unavailable fallback. Preserve aggregate
retryability explicitly when at least one attempted delegate is recoverable;
an all-permanent failure set must still stop after its first pass. Add both
mixed-order tests, plus capacity-only delegates, so ordering does not decide
whether extraction converges or wastes another thirty rounds.

The shared type need not create a configurable retry framework. A narrow marker
or subclass and an aggregate that preserves the same property is sufficient;
keep existing provider error strings, trace attribution, and fallback order.
