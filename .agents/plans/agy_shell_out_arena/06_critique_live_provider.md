# E4 live-provider critique: normalize denied empty envelopes at the boundary

Date: 2026-09-11. This revision uses the lead's bounded live agy 1.2.0
measurements; this reviewer made no additional provider calls or code changes.

## The observed root cause replaces the earlier speculative candidates

The forced harmless `printf` probe returned exit code zero and a JSON envelope
with `status: SUCCESS`, an empty `response`, and
`denied_actions: [{action: command, display_name: RunCommand}]`. Stderr explicitly
said jetski produced no output because the command permission was denied.

Current `_run` trusts the process exit status, then unwraps that envelope to an
empty string. The prompt runner treats the string as model output: validation
fails and may spend the JSON-repair call. The graph layer receives a failed
validation result instead of the provider exception its existing localized
retry loop handles. The denial crossed the provider boundary as an answer.

This is a concrete compatibility bug between agy's current result envelope and
Incurator's result interpretation. There is no need to change the model, graph
contract, batch cache, retry cap, or CLI permissions to correct it.

The other measured probe returned a useful graph with four entities and three
relations in 13.5 seconds at two turns. Thus turn count cannot decide whether a
result is failed, incomplete, or involved a denied tool.

## Narrow implementation gates

1. Keep the subprocess launch, arguments, sandbox, and permission rules intact.
   Classify the provider result in `_run` before its structured payload is
   returned to the prompt runner.
2. Treat an explicit error envelope as a provider error even if the process
   exited zero. Preserve the actual envelope error reason; let existing
   capacity detection apply to that failure. A populated payload cannot turn an
   explicitly failed provider response into success.
3. Recognize the measured nonempty `denied_actions` list as provider evidence.
   When it accompanies no answer, raise `AntigravityCliError` with a concise
   permission-denial reason naming the reported action(s). This lets the
   existing graph exception retry handle the same batch. Do not advise widening
   permissions, classify denial as quota, or turn it into an empty valid graph.
4. Preserve useful completed output. A denied action can be followed by a
   recovered answer: its mere presence is not a failure flag when the envelope
   supplies the answer. Keep returning a present structured result, including
   a contract-valid empty extraction such as `{entities: [], relations: []}`,
   when it represents a completed answer. Nonempty response text also belongs
   to the existing parse/validation path. This transport layer must not invent
   a graph-specific schema validator or reject answers because of turn count.
5. Distinguish absent output from a valid empty extraction. `_has_content`
   returns false for arrays of length zero, so using that helper alone would
   incorrectly discard a legitimate completed result. The implementation must
   expressly preserve the known empty-result contract shapes; do not infer
   that every structurally present value is valid either. The prompt runner's
   existing contract validator remains responsible for malformed payloads.
6. Do not add a generic retry taxonomy in this release. A normal
   `AntigravityCliError` already enters the intended graph retry path. The
   previously identified broad `except Exception` issue is separate and should
   not obscure the directly reproduced fix.

## Discriminating regression tests

- Reproduce the exact observed exit-zero SUCCESS envelope with empty response,
  no structured result, and denied command. `_run` raises
  `AntigravityCliError`; no empty string escapes to the prompt runner.
- The same envelope without a usable stderr still identifies denied actions;
  diagnostics must come from the structured signal, not stderr availability.
- A populated valid structured graph plus denied actions returns the graph;
  denial followed by recovery must not trigger a duplicate extraction.
- A completed valid empty structured graph plus denied actions remains an
  empty graph. Include empty units too if applying the shared behavior to all
  structured contracts. Do not confuse zero extracted facts with no response.
- Nonempty response text plus denied actions reaches normal parsing; a model
  that recovered in prose must still be able to satisfy the contract.
- Explicit ERROR status with exit zero raises, including an envelope carrying
  a misleading populated payload. Existing nonzero/error/capacity behavior
  remains covered.
- Ordinary zero-output envelopes without a denied action continue through the
  existing empty-output/validation behavior unless a separately documented
  change is required; avoid incidental policy expansion.
- Exercise the real Antigravity adapter with a fake subprocess sequence: first
  the measured denial envelope, then a valid graph. Through `run_prompt` and
  `extract_graph_data`, verify the denied attempt is a failed provider trace,
  the second call retries the same batch, and the final graph is complete.
  Assert no JSON-repair call is spent on an empty provider refusal.
- Preserve the existing capacity-deferral and graph resume/publication tests.
  These already establish that valid earlier batches survive later failures;
  no new persisted state is warranted.

## Critique of the synthesis

Accept the proposed narrow correction. It repairs the observed reason existing
resilience failed to activate, rather than adding a second retry mechanism or
granting tools. The completion claim should be precise: agy may still request a
forbidden command, but an empty denied turn becomes an observable provider
failure and is retried by the already-shipped per-batch mechanism.

Before landing, inspect the exact distinction between missing structured output
and a completed empty result. This is the highest-risk review edge: a simplistic
truthiness or `_has_content` condition can turn a correct empty extraction into
thirty unnecessary retries. Conversely, success status alone cannot be trusted,
as the live denial already demonstrates.
