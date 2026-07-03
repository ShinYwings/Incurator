# Defense and Consensus

Date: 2026-07-03 | Agent Persona: system_synthesizer

## 1. Resolved Design

- Schema v11 is accepted; source `updated_at` is the only source LWW clock.
- The guarded trigger is accepted only with import-preservation and no-loop tests.
- Export-gate comparison will parse instants.
- Dashboard counts will reuse serving predicates, not raw table counts.
- Projection failure will not downgrade a valid L1 source.
- L3 done requires a live report grounded in the source; an empty/no-eligible L3
  pass records skipped. L4 done continues to mean current shared-corpus
  synthesis availability, and requires at least one current synthesis node.
- Missing canonical L2-L4 rows will be recovered only from peer JSONL or rebuilt.
- The release retains distinct phases/gates for the incident and deferred
  hardening so the incident can be verified independently.

## 2. Remaining Stop Conditions

- Stop before production repair if no verified backup exists.
- Stop before destructive reconciliation if peer snapshots disagree about the
  latest source revision.
- Do not claim historical L4 recovery if no peer retains synthesis rows.
