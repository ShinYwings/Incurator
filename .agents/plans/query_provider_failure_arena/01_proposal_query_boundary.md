# Query Boundary Proposal: One Expected-Failure Path
Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Keep `LLMError` as the one typed provider boundary. Provider clients must reject
blank output; `FailoverClient` must catch every `LLMError` subtype, including
Codex, and retain a bounded provider-labelled attempt summary when every
configured provider fails.

`ContextService.context_fetch()` already persists the QTR and returns the full
evidence pack before answer synthesis. `QueryOrchestrator.run()` should catch
only `LLMError` around its answer/explore synthesis call, recover the already
closed PTR rows with `db.list_prompt_runs_for_query()`, fill the existing result
fields, and always call its existing QTR synthesis-action updater.

```python
result = QueryResultV031(trace_id=pack["trace_id"], provenance=pack[...])
try:
    synthesize(result)
except LLMError as exc:
    runs = db.list_prompt_runs_for_query(paths.state_db, result.trace_id)
    result.prompt_trace_ids = [row["trace_id"] for row in runs]
    result.error = format_provider_failure(exc, runs[-1] if runs else None)
update_context_trace_after_synthesis(result)
return result
```

Use one query-result serializer for both successful and failed
`QueryResultV031` instances. The plugin API owns the backend-local JSON
contract; MCP `curator_query` delegates to it with an explicit English output
default so the duplicated orchestration/catch/trace mapping is removed without
dropping existing MCP fields.

CLI `_run_query_repl()` returns a failure flag. `commands/core.py::query` exits
1 after cleanup when any query failed. `CliQueryCallbacks.on_complete()` prints
the answer when no stream rendered it. The hidden plugin command always prints
the returned JSON, then exits 1 when `ok` is false.

## 2. Pros & Cons

Pros:

- Fixes the failure where the QTR and PTR already exist, instead of wrapping or
  re-running the provider call.
- Preserves unexpected programming exceptions as real defects.
- Uses existing JSON and DB fields, keeping v0.37.1 a patch release.
- Removes the duplicated MCP query pipeline that allowed error contracts to
  diverge.
- Makes provider success/failover semantics model-independent.

Cons:

- MCP receives an additive superset of its current successful query payload.
- Provider attempt summaries need strict length bounds to avoid verbose output.
- Cancellation and trace-storage outages remain separate failure classes.
