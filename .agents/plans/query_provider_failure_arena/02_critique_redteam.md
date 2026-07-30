# Critique on One Expected-Failure Path
Date: 2026-07-30 | Agent Persona: Red Teamer

## 1. Vulnerabilities & Flaws

- Catching `Exception` in the orchestrator would mislabel DB, parser, and coding
  defects as provider outages. The catch must be exactly `LLMError`.
- Guarding blank output only in `run_prompt()` is too late for a
  `FailoverClient`: the blank primary has already been accepted, so the fallback
  never runs. Blank output must fail at the provider/failover contract.
- The current failover tuple omits `CodexCliError`; an enum-like list of selected
  subclasses will repeat this omission for future providers.
- Codex reads its output file before checking the process return code. Partial
  JSON from a failed process can validate and become a false-success answer.
- The QTR updater runs only on the normal orchestrator path. A catch that merely
  builds a JSON error still leaves no failed synthesis action.
- The plugin/MCP adapters currently throw away trace fields for both provider
  exceptions and ordinary validation failures. Fixing only the exception branch
  leaves parity broken.
- Returning `{ok:false}` from `wiki plugin query` while exiting 0 is a
  machine-visible false success.
- A CLI regression test that asserts only "no traceback" can pass while a
  successful query still prints no answer.
- Full raw stderr/API bodies can be long or contain local diagnostics. Public
  text must be bounded; full prompt/trace inspection remains the explicit audit
  path.

Cancellation, trace-finalization storage failures, malformed provider wire
responses, post-failover prompt-provider attribution, and Antigravity temp-log
cleanup are real findings, but mixing them into this patch would create a broad
exception/storage/security release rather than the reported query UX repair.

## 2. Suggested Alternatives

- Make the provider contract reject non-string/blank output before returning.
- Catch the base `LLMError` plus `OSError` for failover rather than maintaining
  a provider-subclass tuple.
- Check Codex return code before reading any last-message output.
- Recover failed PTR ids from the QTR index and run the normal trace updater.
- Serialize success and failure through one helper and delegate MCP query to the
  backend-local plugin API.
- Bound and one-line-normalize public provider details; do not emit tracebacks.
- Test success, initial failure, repair failure, validation failure, configured
  fallback, blank output, Codex non-zero partial output, and every surface exit
  contract.
- Record the out-of-scope findings in the evidence ledger and Stability queue.
