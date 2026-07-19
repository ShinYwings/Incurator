# Schema Proposal: Transactional Truth Over Optimistic Counters
Date: 2026-07-19 | Agent Persona: schema_guardian / source_pair_analyst

## 1. Core Logic & Implementation

- Preserve `SCHEMA_VERSION = 12` and the existing JSONL header/row layout.
- Let SQLite's per-file transaction roll back a tombstone when its target delete
  raises. Do not write a compensating row outside that transaction.
- Preserve `sources.sync_key` deletion and local integer-id remapping.
- Do not attempt to make composite primary-key tombstones work by guessing how
  `record_id` encodes multiple columns. That requires an explicit transport
  contract and belongs in a separate planned release.
- Peer file A may commit before file B fails. This is safe because import is
  row-idempotent, but the overall pass must return failure rather than a green
  aggregate.
- Curation policy errors occur before retrieval begins, so no evidence pack,
  query trace, or answer is created under a policy different from the requested
  workspace.

## 2. Pros & Cons

### Pros

- No migration or data rewrite.
- The reported deleted count matches committed database reality.
- A malformed source scope cannot leak out-of-scope evidence.

### Cons

- Composite-key delete propagation remains unsupported and must stay visible in
  the roadmap.
- Cross-file autosync is not globally atomic; making it so would require staging
  all peer files into one transaction and is disproportionate to this patch.

