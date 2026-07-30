# Defense And Revision: Existing-Field Failure Contract
Date: 2026-07-30 | Agent Persona: Surface Validator / System Synthesizer

## 1. Vulnerabilities & Flaws Resolved

The revised plan accepts the query/provider objections while keeping the patch
bounded:

- `LLMError`, not a new exception hierarchy or broad catch, is the typed
  expected-failure boundary.
- Blank output fails at the provider contract so fallback can run; the prompt
  runner remains responsible for terminal PTR recording.
- Codex participates in failover and cannot publish output from a non-zero
  process.
- The orchestrator recovers PTRs, retains retrieval evidence, and writes the
  normal failed synthesis child action before returning.
- The existing `error`, `trace_id`, `prompt_trace_ids`, provenance, and `trace`
  fields are the entire public failure contract. No `error_type`, `retryable`,
  DB column, or schema version is added.
- MCP delegates to the backend-local query API with explicit language semantics;
  the plugin API stays independent of MCP.
- CLI, MCP, and hidden plugin tests compare the same failure meaning, while the
  plugin display preserves the error and prompt-trace ids.
- CLI success output and failure exit status are both locked by tests.

## 2. Final Consensus

Ship as v0.37.1, a backward-compatible bug-fix/refactor release. The structured
failure shape is:

```json
{
  "ok": false,
  "answer": "",
  "question": "...",
  "error": "Query provider failed during JSON repair: ... Retry, switch provider/model, or configure a fallback.",
  "trace_id": "QTR-...",
  "prompt_trace_ids": ["PTR-..."],
  "source_span_ids": ["SPAN-..."],
  "community_report_ids": [],
  "synthesis_node_ids": [],
  "memory_path_ids": [],
  "warnings": [],
  "trace": {
    "trace_id": "QTR-...",
    "prompt_trace_ids": ["PTR-..."],
    "source_span_ids": ["SPAN-..."]
  }
}
```

The hidden plugin command emits this JSON to stdout and exits 1. MCP returns the
same domain envelope as a normal tool result so the calling model can inspect
the trace and self-correct. Unexpected non-`LLMError` exceptions are not
converted to this provider-failure result.
