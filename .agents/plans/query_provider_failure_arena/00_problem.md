# Query Provider Failure UX — Briefing

Date: 2026-07-30 | Branch: `release/v0.37.1`

## Problem

A real Gaussian Splatting query completed retrieval, then Antigravity returned
no output during the prompt runner's single JSON-repair call. The prompt runner
correctly closed the failed `PTR-*`, but the exception escaped before
`QueryOrchestrator` attached that prompt trace to the already-persisted `QTR-*`.
`wiki query` consequently exposed a Rich traceback. MCP and the hidden plugin
query caught the same class of failure independently and returned reduced
string-only errors that discarded the trace and retrieved provenance.

The audit also found three adjacent cross-provider defects on the same path:

- Ollama, Claude, and Codex may return blank output where Antigravity and
  DeepSeek raise a provider error.
- `FailoverClient` does not include `CodexCliError` in its runtime failover
  tuple and reports only the final attempt when all providers fail.
- Codex can return a valid-looking output file before its non-zero process exit
  is checked, turning a failed process into a successful answer.

Finally, the non-streaming orchestrator path calls `CliQueryCallbacks.on_complete`
without printing `result.answer`, so a successful `wiki query` can be silent.

## Required outcome

- Expected provider, timeout, quota, blank-output, and repair-call failures
  become a failed query result at the `QueryOrchestrator` boundary.
- The existing QTR, failed PTR, ContextService provenance, and original provider
  diagnosis remain auditable.
- All backend providers obey the same non-empty/non-zero success contract and a
  configured fallback is attempted for every `LLMError` subtype.
- CLI prints either the answer or one concise actionable error; a failed session
  exits 1 and never prints a traceback.
- MCP and hidden plugin query return the same existing failure fields; the
  hidden command prints parseable JSON before exiting 1.
- Successful payloads, L3-incomplete fallback, workspace-policy failures, and
  the normal plugin context-pack-first sidechat path do not regress.

## Non-goals

- A new public error taxonomy, new JSON fields, or a DB schema migration.
- Changing prompt retry count or adding repeated provider retries above the
  existing configured fallback chain.
- General cleanup of every broad catch or backend JSON command.
- Cancellation semantics, trace-storage outage recovery, provider-wire schema
  hardening, or prompt-run provider identity after failover.
- Authored-wikilink topology validation.
