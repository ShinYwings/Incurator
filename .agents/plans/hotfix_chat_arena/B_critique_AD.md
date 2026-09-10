# Critique on A_latency and D_models
Date: 2026-09-10 | Agent Persona: Provider Runtime / Adversarial Reviewer

## 1. Vulnerabilities & Flaws

1. A's early fetch is safe only when the promise is immediately given rejection
   handling. Local context failure or abort must not leave an unobserved rejection.
   Snapshot workspace path, document identity and knowledge flag before awaits;
   reuse those captured values for result acceptance. Existing `LLMClient`
   image state is instance-shared, so do not introduce concurrent calls to it
   while parallelizing independent backend reads.
2. Off cannot be implemented only by suppressing prefetch. Current API `auto`
   injects curator MCP and current CLI inherits tools. If on/off means automatic
   prior-knowledge retrieval, state that precisely and ensure the model prompt
   no longer advertises automatic curator_query. An explicit user request to
   consult notes remains user-requested context and should not silently vanish.
3. Root's new timeout example (sections 4.2–4.6 based on user's own notes)
   requires research. Skipping that research would miss the task. Native agy
   text output is buffered; stream-json emits `agent_response.text_delta` and
   `tool_info`, observed on agy 1.2.0. Exposing real deltas and tool statuses is
   required alongside preparation scheduling, so partial output survives timeout
   and actual work is visible. Tests must not merely replace spinner wording.
4. D's retired-selection handling is unresolved. Leaving persisted
   gemini-3.5-flash selected defeats the user's actual upgrade: new menu entries
   do not repair a saved unusable model. Existing normalization/default helpers
   must deterministically handle specifically retired bundled IDs while keeping
   unknown custom IDs untouched. State which default replaces 3.5 and test real
   plugin settings load and backend configuration validation.
5. New catalogue effort dimensions must be verified per provider, not borrowed
   from same-named API models. Model label/ID default changes also affect usage
   probes, fallback choices, and live tests; verify those active references.

## 2. Suggested Alternatives

- Parallelize independent context I/O only; assert max independent duration and
  unchanged evidence ordering, trace identity and explicit selected content.
- agy stream parser handles chunked JSON, EOF without newline, final result
  reconciliation, quota/error/timeout with partial output. Preserve human prose
  as answer and tool progress separately; no transcript JSON rendered to user.
- Prefer a measured declarative read-only agy agent with MCP when supported;
  its documented `tools` whitelist must be tested behaviorally before shipping.
  First live init unexpectedly advertised all builtins despite tools=view_file,
  so documentation cannot yet be treated as enforcement proof.
- Fixed retired-ID mapping is scoped migration of a provider choice, not a
  general unknown-model fallback. Explain the mapping in release notes.
