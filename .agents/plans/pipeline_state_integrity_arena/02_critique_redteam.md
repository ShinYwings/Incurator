# Critique on DB-Authoritative Status and Revisioned Sources

Date: 2026-07-03 | Agent Persona: red_teamer / schema_guardian / source_pair_analyst

## 1. Vulnerabilities & Flaws

- A trigger can restamp imported rows and create sync loops if the import path
  executes UPDATE rather than replacement.
- Fractional and second-precision ISO strings do not sort safely as plain text at
  equal seconds.
- Counting all knowledge units or reports would expose retired/staged records.
- Automatically resetting downstream statuses on every L1 projection failure
  can destroy valid completion state.
- Marking all L2-complete sources L3 done from a corpus-global success can claim
  per-source concept grounding that does not exist.
- A non-empty global L4 corpus does not prove every source contributes evidence
  to it; the UI must define whether L4 means corpus availability or per-source
  participation and apply that definition consistently.
- Reverse-parsing the 353 ATM files would violate the single-source-of-truth rule.
- Bundling deferred hardening risks obscuring the production repair criteria.

## 2. Suggested Alternatives

- Test the exact `INSERT OR REPLACE` import path against the trigger and assert
  remote timestamp preservation.
- Parse timestamps for export gating and normalize source timestamps in migration.
- Reuse serving-set predicates from projection re-emission.
- Distinguish first-ingest/source-invalid failure from derived-projection failure.
- Derive L3 participation through live report span provenance; define L4 badge as
  current shared-corpus availability, consistent with the existing plugin contract.
- Make peer-snapshot recovery a stop condition; rebuild if canonical rows are gone.
- Keep separate test/doc phases for state integrity and deferred sync hardening.
