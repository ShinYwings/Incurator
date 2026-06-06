# Incurator Master Roadmap Evidence Ledger

This file records the factual baseline that the Stabilization, Sync Bridge, and Native PDF Annotation roadmap must obey.
It exists so that documentation, database schema migrations, and plugin behavior do not drift away from the actual repository and vault state.

The ledger is intentionally operational. It is the evidence table that must be refreshed before any destructive repository operation such as SQLite schema changes, JSONL export mappings, or PDF viewer DOM modifications.

## 1. Current Repository Reality

[To be filled by planning agents during deep research]

- Observed repository root:
- Current top-level layout:

## 2. Current Schema Reality To Recheck Before Migration

[To be filled by planning agents]

- Existing `sources`, `synthesis_nodes`, `knowledge_units` schema.
- Expected tombstone table (`deleted_records`) schema.

## 3. Current Dirty Worktree Categories

[To be filled immediately before executing codebase changes]

Because changes may belong to the user or another agent, no command may revert them casually.
Observed categories:
- 
- 

## 4. Known Validation Results From Current Work

[To be filled during Test-Driven Development]

- Backend tests passed:
- Plugin tests passed:
- Testbed verification:

## 5. Rollback Requirements Before Destructive Operations

[To be defined during planning]

- Git rollback anchors.
- Database (`.curator/state.sqlite`) backup steps.

## 6. Execution Updates (Phase-by-Phase)

[To be appended as each milestone executes]

- Knowledge Sync Bridge Update:
- RAG Stabilization Update:
- PDF Annotation Update:
