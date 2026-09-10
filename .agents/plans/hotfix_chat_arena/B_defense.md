# Defense and Revised Provider Consensus
Date: 2026-09-10 | Agent Persona: Provider Runtime / Edit Integrity

1. Accept A's critique of completion duplication. The Codex accumulator must
   track stable item identity, latest item snapshots and emitted final suffix.
   File reconciliation extends the SAME last item when it is a prefix, appends a
   different intact final item once, and never deduplicates two distinct IDs by
   length. Item-aware regression fixtures are required. Status/phase metadata
   should keep non-answer progress separate where the CLI provides it.
2. Accept A's capability objection. Search-off means automatic prior-knowledge
   enrichment off; explicitly attached/current document references and their
   image/text reads survive. Settings must be captured per call, never mutated
   temporarily in the provider layer.
3. Reject my optional schema-buffered alternative. The new user evidence is a
   five-minute agy text-mode timeout. Native stream-json was measured on
   installed agy 1.2.0: `step_update.agent_response.text_delta` arrives incrementally,
   and result.response contains the final prose. A direct equation explanation
   returned correct prose in one turn, model duration 1.61 seconds. Implement
   real deltas plus tool statuses, final reconciliation, partial-timeout warning
   and truncation detection without blanket retries.
4. A documented custom-agent whitelist is NOT yet a viable fix. Official
   https://antigravity.google/docs/subagents/ describes `tools`, `mainAgent`,
   `inheritMcp` and `commandExecutionPolicy`, but also warns unmapped tools may
   hang. Disposable live agent with `tools: [view_file]`, mainAgent true,
   inheritCustomizations false, inheritMcp false, commandExecutionPolicy off
   started and answered the math question, yet its init advertised all tools.
   Asking it to execute harmless printf produced repeated agent/error steps
   followed by a 35-second timeout with no response. Subsequent CLI-log review
   by the root agent identified RESOURCE_EXHAUSTED / Individual quota reached
   retries as the cause: that failed probe cannot establish either whitelist
   success or failure. This probe changed no user settings and broadened no
   permission. Do not treat the doc or successful plain answer as proof of
   tool exclusion; the live behavior remains unverified.
5. Prompt surface precision remains a necessary prevention improvement, but
   cannot alone support a claim that every command denial is fixed. Preserve
   narrow grants and OS sandbox. Stream-json gives explicit denied_actions
   evidence rather than burying errors in a generic buffered spinner. A genuine
   command requirement or unsupported CLI capability remains visible.

Probe artifacts (device-local, ignored): `.cache/provider-probe/probe.jsonl`,
`command-probe.jsonl`, corresponding stderr and disposable agent definition.
No graph extraction or roadmap E4 code changed.
