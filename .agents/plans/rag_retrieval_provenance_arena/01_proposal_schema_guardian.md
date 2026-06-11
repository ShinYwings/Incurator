# Schema Guardian Proposal: Serving Contracts Without New Truth

Date: 2026-06-11 | Agent Persona: schema_guardian
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Authority boundaries

- `state.sqlite` remains authoritative.
- Program 2 records own claim support, truth/freshness, dependencies, and source
  locators.
- search documents/chunks/embeddings remain derived and rebuildable.
- serving transactions/packs record what was selected and why; they do not
  become knowledge truth.
- `.curator/Collections/` and rendered links remain derived presentation.

### Additive serving candidates

The exact schema is frozen only after Program 1/2 handoffs, but Program 3 may
need:

- authoritative query transaction identity and child-run references;
- snapshot/search/policy epoch fields;
- pack budget/omission/selection metadata;
- structured evidence-item locator snapshots;
- expansion handle state or deterministic regeneration contract;
- feedback lineage to pack/transaction/snapshot.

Avoid normalizing locators again if Program 2 already supplies an adequate
canonical locator contract.

### Integrity rules

- selected source-supported evidence must reference valid trusted Program 2
  records and minimal source spans;
- evidence from different snapshots cannot be mixed silently;
- policy-excluded/stale evidence cannot be selected without an explicit approved
  override and warning;
- answer claim/evidence associations reference selected pack items;
- pack records are bounded and have retention policy;
- compatibility fields cannot contradict the new normalized contract.

### Migration and rollback

- use additive, forward-only migration;
- back up DB before migration;
- derive/rebuild search and pack caches where possible;
- remove old serving paths only after parity tests prove delegation;
- rollback restores DB backup and previous client/backend versions; no
  destructive down-migration.

## 2. Pros & Cons

### Pros

- Keeps serving state from becoming a second knowledge source of truth.
- Preserves Program 2 compiler authority.
- Supports reproducible transactions and safe expansion.

### Cons

- Pack/transaction retention can grow rapidly.
- Compatibility fields can create ambiguity during migration.
- Snapshot identity requires coordination across DB, search, and policy state.
