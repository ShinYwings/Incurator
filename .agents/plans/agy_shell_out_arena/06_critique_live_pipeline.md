# Cross-critique: the live denied envelope bypasses the existing graph retry

Date: 2026-09-11 | Persona: pipeline reviewer

## Verdict

Accept the revised minimal direction. The live shape supplied by the lead is a
specific provider-boundary regression, distinct from the stale no-resume claim:

```json
{
  "status": "SUCCESS",
  "response": "",
  "denied_actions": [{"action": "command", "display_name": "RunCommand"}]
}
```

The process exits zero, has no `structured_output`, and prints jetski's
no-output denial diagnostic on stderr. `_run` considers nonempty **stdout** a
successful answer even though the JSON envelope contains no answer.
`_structured_from_envelope` then returns the empty response. The prompt runner
treats this as malformed model output and spends its JSON repair attempt; if
that attempt also refuses, graph extraction receives an invalid result rather
than the exception its existing per-batch retry was designed to handle.

Normalize this no-answer tool denial to `AntigravityCliError` at `_run` before
returning the unwrapped value. That restores the existing retry, trace failure,
capacity separation, and durable resume paths. No compiler, retry-budget,
schema, fallback-order, or permission-policy change is required.

## Scope critique

Defer the earlier typed retry-eligibility proposal to a separately scoped item.
Its broad-exception concern remains real, but solving it now expands this
measured hotfix into error taxonomy and failover aggregation. The denial bug
can be fixed at its source using the error class the compiler already handles.

Do not equate presence of `denied_actions` with complete turn failure. An
agentic runtime may deny an action and then provide a valid usable answer.
Keep populated structured output and usable prose available to existing
validation. Likewise, an explicit successful empty graph payload is different
from a missing answer and must not become a refusal merely because its arrays
are empty. Shape/presence, content selection, and denied-action metadata have
distinct roles; `_has_content` alone cannot decide whether an empty graph is a
legitimate answer.

Recognize the structured denied-action field as the strongest signal for the
measured envelope. Preserve the error reason, but avoid copying arbitrary
transcript/log contents into the error. A denial must not start a capacity
cooldown merely because some incidental diagnostic contains quota-like words
or numeric text. Retain existing genuine-capacity tests.

The ordinary graph live probe returned useful output with `num_turns=2`.
Correct stale documentation/test claims that one turn proves no shell use.
This fix restores handling when an operation is denied; it does not prevent
agy from ever choosing a tool. State the narrower result accurately.

## Tests that will actually fail before this fix

A single `denial -> valid` sequence is **not sufficient** as the principal
pipeline regression. The current broken path may consume the valid response as
its JSON repair and still return a valid graph, making that test pass before
the fix. Use at least two denied responses before success, or distinguish the
original batch retry from JSON repair through prompt/trace evidence.

Recommended integration test:

1. Instantiate the real `AntigravityCliClient`; fake only `subprocess.run` and
   sandbox construction/environment setup as necessary for fixture isolation.
   Use the real registered graph contract, schema flattening, prompt runner,
   graph extraction, and isolated SQLite DB.
2. Return the exact exit-zero denied envelope twice, then a valid cited graph
   envelope. Require success after three subprocess calls. Before the fix the
   runner consumes two denials (original + repair), returns invalid, and never
   reaches the successful third result.
3. Check that all three graph input prompts are the same original batch and do
   not include the repair instruction `Your previous response failed
   validation`. Check failed trace rows preserve the denial reason and the
   successful row alone becomes the validated graph cache entry.

Recommended durable-resume test:

1. Force two batches via a small client chunk budget. The first returns a valid
   graph; the second returns the real denial envelope until the graph retry
   bound is exhausted. It is acceptable to reduce the bound in the test so the
   failure lifecycle is cheap; do not alter the production bound.
2. Require `GraphData(ok=False)`, exactly the first batch staged, and no failed
   batch cache entry. The test must not synthesize `AntigravityCliError` directly:
   use the envelope through the real client so the original defect is covered.
3. Resume with only one successful envelope available. Require exactly one
   provider call, both batches in the returned graph, and the first batch's
   original trace/provenance retained.
4. Existing compile publication/rollback tests already prove incomplete graph
   failure stays behind the generation gate. Keep them in the targeted suite;
   no generation-storage rewrite is justified by this provider fix.

Provider boundary table:

| Envelope/outcome | Expected behavior |
|---|---|
| Exit zero, SUCCESS, no answer, command denied | `AntigravityCliError`, original denial reason |
| Same result with empty/whitespace response | Same denial classification |
| Denied action followed by populated valid graph | Return graph for validation |
| SUCCESS, explicitly valid empty graph, no denial | Preserve legitimate empty graph |
| SUCCESS, no denial and no answer | Remains visibly invalid; never successful cached graph |
| Genuine capacity error | Existing capacity/cooldown path |

The separate explicit `status=ERROR`/exit-zero case is worth a test if handled
by the same normalization, but do not claim it was the live incident: the
decisive measured incident declares `status=SUCCESS`.

## Closure criterion

Exact live graph extraction succeeds under the unchanged containment; the live
forced-command probe establishes the envelope shape and denial; fake-process
integration proves that this exact envelope enters localized graph retry and
durable resume without incomplete publication. That closes the measured
pipeline regression. It does not justify a claim that arbitrary future agy
tool behavior is eliminated or that the current model has a measured long-run
success rate.
