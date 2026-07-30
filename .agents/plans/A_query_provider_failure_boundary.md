# Domain Analysis A — Query And Provider Failure Boundary

Date: 2026-07-30

## Design constraints from the current codebase

- `ContextService.context_fetch()` persists a QTR before synthesis.
- `prompting.run_prompt()` opens a PTR before calling the client. On a provider
  or repair-call exception it closes that PTR as `failed`, retains the first
  response hash, protects the original exception from trace-write failure, and
  re-raises it.
- `QueryOrchestrator` appends the PTR id and updates the QTR only after
  `run_prompt()` returns. An exception therefore leaves a terminal PTR that is
  query-linked in `prompt_runs.query_trace_id` but absent from the QTR payload.
- All production backend provider exceptions derive from `LLMError`. Unexpected
  DB/programming errors do not.
- Antigravity and DeepSeek reject blank output; Ollama, Claude, and Codex can
  currently return it.
- The runtime failover tuple names selected provider subclasses and omits
  `CodexCliError`.
- Codex can read a last-message file before checking non-zero exit status.

## Docs/spec invariants

- Every prompt-provider exception and repair-call exception closes its PTR.
- Every orchestrated query persists one authoritative QTR with prompt-trace ids,
  warnings, and retrieved evidence.
- Synthesis failure never clears the retrieved ContextService provenance.
- Empty provider output is not a successful LLM answer.
- A configured fallback is the only provider retry layer; query code must not
  multiply the same failing dependency.
- `state.sqlite` remains authoritative; no DDL change is required.

## Alternatives and trade-offs

### Catch in the CLI only

Rejected. It can hide the traceback but cannot repair QTR/PTR linkage and leaves
MCP/plugin inconsistent.

### Wrap every provider exception in a new query exception

Rejected. The existing `LLMError` hierarchy already distinguishes expected
provider failures. A second hierarchy changes all prompt callers for no gain.

### Catch all exceptions in `QueryOrchestrator`

Rejected. It would hide DB and programming defects as recoverable provider
outages.

### Treat blank output in `run_prompt` only

Rejected as the sole guard. It protects a direct client but is downstream of
`FailoverClient`, so a blank primary would not trigger fallback.

### Provider-level non-empty contract plus orchestrator `LLMError` catch

Selected. It normalizes all model backends at the source, lets fallback work,
and turns only expected provider failures into query results.

## Final decision

1. Add one small shared provider-output guard and apply it to every backend
   provider's non-streaming `chat()` result.
2. Define failover errors in terms of `LLMError` and `OSError`, not an incomplete
   provider-subclass list. When every provider fails, retain bounded
   provider-labelled summaries in attempt order and chain from the final cause.
3. Check Codex `returncode` before accepting its output file or stdout.
4. Catch only `LLMError` around answer/explore synthesis after the QTR/result
   exists.
5. Recover all PTRs for the QTR, set the existing error string, and call the
   normal trace updater.
6. Preserve validation failure as a distinct non-provider result and propagate
   non-`LLMError` defects.

## Implementation pseudocode

```python
def require_output(value: object, provider: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMError(f"{provider} returned no output.")
    return value.strip()

FAILOVER_ERRORS = (LLMError, OSError)

def run(request):
    pack = context_fetch(request)          # persists QTR
    result = result_from_pack(pack)
    try:
        synthesize_into(result)            # run_prompt persists PTR
    except LLMError as exc:
        runs = db.list_prompt_runs_for_query(db_path, result.trace_id)
        result.prompt_trace_ids = [r["trace_id"] for r in runs]
        result.error = bounded_provider_message(exc, runs[-1] if runs else None)
    update_qtr_synthesis_action(result)
    return result
```

## Deferred findings

- User cancellation and `BaseException` trace finalization.
- Trace/QTR storage failure precedence and recovery.
- Malformed Ollama/DeepSeek wire-shape normalization.
- Actual responding-provider attribution when failover changes provider after
  the PTR opens.
- Antigravity temporary-log cleanup on early exceptions.
