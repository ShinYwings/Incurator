# E4 independent provider proposal — current-code reconciliation

Date: 2026-09-11. Read-only investigation; no provider call or production-data
mutation performed. Scope: backend provider boundary, structured output, graph
retry boundary, existing regression tests.

## What is already fixed

The retained August briefing cannot serve as the current implementation plan.

- `pipeline/graph_index.py::extract_graph_data` already catches provider
  exceptions and retries each graph batch up to 30 times. Capacity cooldowns
  re-raise. Validated batches persist in `graph_batch_results` and are reused by
  prompt digest on the next compile. The claim that one denied command always
  kills the complete compile, and the 87-independent-success calculation, no
  longer describe current code.
- `llm.py::AntigravityCliClient._run` already passes `--sandbox`, native
  `--json-schema` plus `--output-format json`, and a real OS sandbox prefix.
  `prompting/runner.py::_schema_for` already flattens schema references. Merely
  adding one of these is not a fix.
- The backend sandbox deliberately restricts writes, while allowing reads.
  macOS grants writes to vault/runtime roots; Linux uses a read-only root bind
  with writable exceptions. A CLI permission denial and an OS sandbox denial
  are distinct boundaries. E4 evidence names the CLI command permission gate.
- Current plugin permission tests record that `read_file(*)` works, while
  `read_file()` and exact-path rules do not. The briefing's claim that every
  persisted permission grant disappears is superseded by these later measured
  findings. None of this grants arbitrary shell commands.

## What remains unproven

Neither a flattened JSON schema nor `num_turns == 1` is a documented no-tools
enforcement mechanism. `_run` still claims in comments that `--sandbox`
auto-proceeds through permission prompts, contradicting the retained measured
experiments. Its structured-output capability comment overstates a sample
result as a guarantee that the model never reaches for a shell.

`test_live_the_real_contract_schema_returns_one_turn_and_valid_units` has two
gaps: it exercises `knowledge_unit_extract`, not the reported
`entity_relation_extract`, and despite its name/docstring it never reads or
asserts `num_turns`. `_run` unwraps that metadata before returning to the test.
Passing that test cannot establish E4 closure.

No current supported agy no-tools flag is established by the source inspected.
Do not invent one or apply Claude's `--tools`/`--disallowedTools` flags to agy.
Prompting the model not to use tools can be measured as a mitigation but cannot
be called runtime enforcement. Changing provider selection also requires a
product decision if it removes the selected provider's capability or adds cost.

## Smallest defensible direction

First measure one real `entity_relation_extract` invocation using the current
backend command, flattened registered contract, synthetic cited units, and an
isolated testbed DB. Record the outer exit status, JSON envelope status/error,
validated payload, elapsed time, and actual tool events when exposed by agy.
Then test the denied-command case separately under the unchanged OS sandbox.
A failing command probe is evidence about the permission gate, not evidence
that ordinary extraction currently fails.

Keep the already-shipped batch retry and resume mechanism while measuring.
Do not increase the retry cap: thirty calls at a 900-second outer deadline can
already consume 7.5 hours for one batch before any internal repair overhead.
Do not silently allow command execution or auto-approve all tools.

There are two concrete provider/pipeline boundary bugs worth addressing if the
live result confirms their relevance:

1. `_run` reads an envelope error but only acts on it when the exit status is
   nonzero or stdout is empty. A nonempty exit-zero `status=ERROR` envelope can
   flow through `_structured_from_envelope`; a valid-looking empty payload can
   even validate as an empty graph. Transport exit and provider envelope status
   are separate signals. An explicit error envelope must be an error before
   payload extraction, preserving the reported cause and capacity semantics.
2. Graph extraction retries every `Exception` except active capacity cooldown.
   This includes missing CLI, unsupported model, authentication failures,
   unavailable sandbox, and programming errors. Repeating deterministic setup
   failure thirty times cannot make a batch succeed. The provider boundary
   should expose narrowly classified failures; graph retry should handle the
   measured stochastic permission refusal and genuine transient failures,
   while permanent failures surface immediately. Avoid replacing this with
   broad message matching in the graph layer.

These fix failure interpretation and wasted work at their source. They do not
prove that agy will never elect to run a shell. E4 should only close under its
actual resilience criterion once exact-contract extraction plus denial/retry
and resume checks succeed; any residual provider choice must remain explicit.

## Tests

- Provider subprocess fakes: exit-zero explicit ERROR cannot return a valid
  empty graph; exit-nonzero JSON error preserves its reason; successful empty
  extraction remains valid; genuine capacity marks the provider cooldown;
  a permission error containing unrelated numeric text is not quota.
- Typed retry tests: stochastic refusal then success retries only the same
  batch; permanent auth/model/sandbox errors cause one attempt; capacity
  escapes to queue/backoff; unexpected programming errors are not retried.
- Existing graph cache tests plus a multi-batch scenario: earlier successful
  batches survive a later refusal and are not re-paid on the next invocation;
  failed/partial results cannot publish or enter the validated cache.
- Exact graph-contract live test must assert observable evidence rather than
  a misleading one-turn claim; retain real OS write-containment smoke tests.

## Tradeoffs / recommendation for synthesis

Prefer current-contract reproduction and precise failure boundaries over a new
permission contract. Do not implement a routing layer, a retrieval loop, or
scratch-command allowlist from this stale briefing alone. The old unread-PDF
debate concerns content discovery and is not evidence that graph extraction,
whose units are already supplied, needs any of those capabilities.

If extraction and existing localized retry/resume already pass today, the
smallest honest E4 result may be correcting stale roadmap/spec/test claims and
retaining a real exact-contract regression. Do not manufacture an application
change merely to match an obsolete diagnosis.

## Cross-critique of the pipeline proposal

Read `05_proposal_pipeline.md`. Its durable-cache/publication invariants and
rejection of a second storage mechanism are supported by current code. Its
existing 52-test run is appropriate evidence that localized retry/resume is
already implemented.

Two requirements need tightening before synthesis:

- The proposed live check says extraction succeeds "without shell execution."
  That needs actual tool-event evidence. The lead's current synthetic graph
  probe succeeded in 13.5 seconds with four entities and three relations at
  `num_turns=2`; this directly refutes the old one-turn-as-correctness claim.
  Successful validation proves useful extraction, not absence of a tool call.
- "Retry only transient/recoverable category" should not become an expansive
  new enum based on guessed agy error strings. A narrow typed tool-denial
  exception derived from actual observed diagnostics gives the graph boundary
  a concrete distinction. Timeouts/transport failures need an explicit decision
  and tests if their existing retry behavior changes; they must not disappear
  incidentally under a denial-only catch.

The exit-zero ERROR-envelope path is a code-admitted risk, not a measured agy
occurrence from this investigation. Keep it out of the release's claimed root
cause unless the lead's bounded diagnostic probe supplies that evidence; it can
otherwise be handled as a separately stated provider validation correction.
