# v0.37.1 Query Provider Failure UX Evidence Ledger

Date: 2026-07-30
Status: COMPLETE — implementation and release validation passed.

## Rollback anchor

- Branch: `release/v0.37.1`
- Merge-base / clean master:
  `d539f67604d4d6e2d25b82f946d156d5ad9224cd`
- Starting release manifests: `0.37.0`
- Starting DB schema: v13; no migration planned

## Current repository reality

| Boundary | Current behavior |
|---|---|
| Prompt runner | Opens PTR; provider/repair exception closes it `failed`, retains first raw-output hash, re-raises original |
| ContextService | Persists QTR and evidence pack before synthesis |
| QueryOrchestrator | Appends PTR and updates QTR only after normal `run_prompt` return |
| CLI | Catches policy error only; result failure has no exit signal; non-streamed success answer is not printed |
| Plugin API | Broad-catches query exceptions and drops failure trace/provenance |
| MCP | Duplicates plugin query orchestration/serialization and drops failure trace/provenance |
| Hidden plugin CLI | Returned `{ok:false}` is printed with exit 0 |
| Plugin runner | Parses stdout JSON even on non-zero child exit |
| Plugin display | Query error survives normalization but MCP compaction drops top-level PTR/warnings and trace panel omits the reason |

## Measured reproduction

A deterministic lexical-only fixture seeded one source span/entity/report. Its
first synthesis call returned invalid JSON and its repair call raised
`AntigravityCliError("Antigravity CLI returned no output.")`.

Observed on the unmodified branch:

```text
escaped=AntigravityCliError: Antigravity CLI returned no output.
qtr_count=1 qtr_prompt_ids=[]
ptr_count=1 ptr_status=failed retry_count=1
synthesis_action_count=0
```

This proves the lower prompt trace is healthy and the missing boundary is the
orchestrator/surface handoff.

## Cross-provider audit

- Antigravity and DeepSeek explicitly reject blank responses.
- Ollama returns stripped message content without a blank guard.
- Claude returns stripped stdout without a blank guard.
- Codex returns stripped stdout without a blank guard.
- The failover tuple includes Claude, Antigravity, and DeepSeek errors but omits
  `CodexCliError`; it keeps only the last provider failure.
- Codex reads and returns its output file before checking `returncode`.

## Prior art and decision record

- Python's official exception model supports explicit cause chaining with
  `raise ... from ...`. Existing provider exceptions and the final failover
  aggregate retain their terminal cause; the query layer does not create an
  unnecessary wrapper:
  <https://docs.python.org/3/reference/simple_stmts.html#the-raise-statement>
- Click's official error contract renders expected command errors concisely and
  exits non-zero rather than printing an unhandled traceback. Typer uses this
  command model; the CLI will print the query error and raise `typer.Exit(1)`:
  <https://click.palletsprojects.com/en/stable/exceptions/>
- MCP's official tool specification distinguishes tool-execution failures from
  protocol failures and emphasizes actionable feedback visible to the model:
  <https://modelcontextprotocol.io/specification/2025-11-25/server/tools#error-handling>
  This patch retains the established Incurator `{ok:false}` domain envelope so
  existing clients keep QTR/PTR/provenance. A protocol-level `isError` contract
  change is explicitly deferred.
- RFC 9457 recommends stable machine structure, bounded human-readable detail
  focused on correction rather than debugging internals:
  <https://www.rfc-editor.org/rfc/rfc9457.html>
  Direct HTTP Problem Details adoption is rejected because these surfaces are
  CLI/MCP/local JSON and already have a stable query envelope.

## Existing safety nets

- `backend/tests/test_prompt_trace.py`:
  provider failure closes PTR; trace-write failure does not mask provider
  exception; repair failure retains the first output hash.
- `backend/tests/test_query_orchestrator.py`:
  successful QTR/PTR linkage and synthesis child action; validation-failure
  provenance preservation.
- `backend/tests/test_mcp_tools.py` and `backend/tests/test_plugin_cli.py`:
  successful query payloads and hidden JSON command behavior.
- `plugin/src/agent/incuratorClient.test.ts`:
  successful trace-field normalization.

## Planned regression matrix

| Scenario | Required assertion |
|---|---|
| First provider call raises `LLMError` | failed result, QTR/PTR/provenance, no second repair |
| Invalid JSON then repair raises | retry 1, first output hash, failed PTR/QTR child, original diagnosis |
| Two invalid JSON outputs | validation failure remains distinct, QTR/PTR retained |
| Blank primary + working fallback | fallback succeeds |
| Any `LLMError` subtype from primary | configured fallback is attempted |
| All configured providers fail | bounded provider-labelled attempt order retained |
| Codex non-zero + valid-looking output file | `CodexCliError`, no partial answer |
| Unexpected `RuntimeError`/DB error | propagates; never called provider failure |
| CLI success | answer printed, exit 0 |
| CLI provider/validation failure | concise error, QTR/PTR, exit 1, no traceback |
| Plugin API vs MCP | same existing-field failure meaning and retained provenance |
| Hidden plugin failure | one parseable JSON object, exit 1 |
| Plugin display | error + QTR/PTR/warnings remain parseable and visible |

## Deferred audit findings

- Cancellation/`BaseException` can leave a pending PTR.
- Trace/QTR finalization storage failures need a separate precedence/recovery
  contract.
- Malformed Ollama/DeepSeek response shapes can escape outside `LLMError`.
- A PTR opened before failover can name the initially active provider rather
  than the provider that ultimately responded.
- Antigravity early timeout/not-found paths can leave a temporary log.
- Generic `IncuratorClient.callBackendJson()` still collapses no-JSON runner
  errors to `null`; provider query will always return JSON after this patch, but
  the general boundary remains G13-7 follow-up work.

## Testbed reality

- The current materialized `testbed/` is the ResNet Dynamics workspace.
- Checked-in scenarios are `complex_math_backprop` and `testbed_template`; no
  checked-in Gaussian Splatting scenario exists.
- Gaussian production/cache data is not a disposable test fixture and will not
  be mutated or copied into the testbed.
- Implementation validation will use deterministic fake-provider failure tests
  plus non-destructive ResNet status/lint and a live provider query when external
  authentication/capacity permits.

## Pre-validation

- Branch was created from clean synchronized `master`.
- Planning-only worktree changes are confined to `.agents/`.
- No application source files have changed.
- Existing prompt/query safety nets pass unchanged:
  `scripts/backend-check pytest backend/tests/test_prompt_trace.py
  backend/tests/test_query_orchestrator.py -q` → `20 passed`.

## Post-validation

- Focused provider boundary: `46 passed`; Ruff passed.
- Query/prompt boundary: `23 passed`; Ruff passed.
- Backend surface contract: `45 passed`; Mypy passed.
- Plugin focused surface suite: `125 passed`; production build passed.
- Full backend suite:
  `1325 passed, 6 skipped, 5 xfailed, 7 warnings in 464.33s`.
- Full plugin suite: `68 files / 725 tests passed`.
- Full Ruff and Mypy gates passed (`125` source files checked).
- Plugin production build passed and `npm audit` reported zero vulnerabilities.
- Non-destructive ResNet testbed checks:
  `wiki status` completed, `wiki lint` scored `100/100` with zero issues, and
  an authenticated Antigravity query exited `0` and printed its non-streaming
  answer without a traceback.
- The materialized testbed remains intentionally stale at schema v0 with no L3
  concepts; it was not reinitialized or migrated because Gaussian production
  data is not a disposable fixture. The authenticated query nevertheless
  validated provider transport and CLI success rendering against the current
  backend.
- No DB migration or new public field was introduced. The patch preserves the
  existing query envelope and schema v13.
