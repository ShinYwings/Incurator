# Defense And Revision: Full Tombstone Convergence Contract

Date: 2026-07-30 | Agent Persona: Schema Guardian / System Synthesizer

## 1. Vulnerabilities & Flaws Resolved

The revised plan accepts every red-team objection:

- Exact schema registries replace generic JSON-to-SQL behavior.
- Source-scoped keys are portable.
- Both tombstone application and row upsert participate in one timestamp rule.
- Real local deletion sites are part of the release gate.
- Source deletes clean local dependents transactionally.
- Legacy malformed composite tokens block sync without being discarded.
- The test matrix includes malformed tokens, timestamp boundaries, dry-run,
  realistic sources, two-device convergence, and stale-third-peer resurrection.

## 2. Final Consensus

Ship this as v0.37.0 because it changes the JSONL/schema contract. Keep query UX
and wikilink work on later branches. The contract must be approved before specs,
tests, or application code change.

