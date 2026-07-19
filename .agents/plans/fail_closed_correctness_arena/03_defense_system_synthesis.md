# Defense And Consensus: Fail Closed Without Global Transactions
Date: 2026-07-19 | Agent Persona: system_synthesizer

## 1. Resolved Critiques

- Missing files remain valid first-run/default-policy cases. A file that existed
  but disappears during read is an error, not silent absence.
- Autosync remains per-file transactional. The error contract explicitly says
  earlier peer files may already be applied and retry is idempotent.
- JSON mode returns a structured failure object. Human mode exits non-zero.
- `AutosyncResult.conflicts` means successfully imported and archived conflicts,
  not merely detected filenames. A failed item never enters that list.
- Tombstone `DELETE` rowcount zero remains success; only exceptions abort.
- The shared policy resolver validates semantic errors and the parser rejects
  wrong-shaped security-relevant source-scope fields.
- Tests exercise `ContextService.context_fetch` and `QueryOrchestrator.run` or
  `fetch_context`, not only the helper.
- Plugin scheduler behavior remains unchanged; backend failures map to the
  existing `ok:false` notice path, so polling retries are coalesced and never
  displayed as success.
- Composite-key tombstone encoding is recorded as a follow-up because fixing it
  correctly changes the transport contract and cannot be guessed in a patch.

## 2. Final Consensus

Implement two surgical domains: sync fail-closed behavior and curation-policy
fail-closed behavior. Write docs/specs first, failing tests second, then the
minimum application changes. No schema migration, no hash guard, no new retry
loop, and no production-state repair is permitted.

