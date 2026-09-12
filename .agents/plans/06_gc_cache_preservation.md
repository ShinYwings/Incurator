# v0.82.6 Master Implementation Plan

Date: 2026-09-11
Status: APPROVED — independent Arena proposals, cross-critique and revisions concluded; proceed under standing authorization.

## 1. Objective

Correct the existing temporary-vault cache collector: planning must not initialize
or migrate candidate databases, a source-less database containing retained work
must survive, and a changed candidate must not be deleted from an old preview.
Done means regression coverage, matching guides/spec, local checks, actual review
skill, green CI, merged patch and cleanup. B1/B2 remains open afterward.

## 2. Explicit Non-Goals

No prompt-run or session policy change, new Dashboard controls, history expiry,
tombstone expiry, schema/transport change, production GC, migration or reindex.
Do not ship BEGIN IMMEDIATE as a substitute for prompt ownership: the independent
critique proved a normal writer can publish after GC commits.

## 3. Strict Quality Conditions & Release Gates

- A current initialized empty temporary namespace still qualifies.
- Every durable row class, partial/unknown schema, unknown file, symlink and
  inspection failure prevents collection. Offline volumes remain protected.
- Closed partial database bytes/schema remain unchanged by inspection.
- Marker/root/content/namespace changes after preview prevent removal.
- Use isolated fixtures plus the existing testbed; no production deletion.
- TDD, backend pytest/ruff/mypy, plugin vitest/tsc, version consistency, required
  code-review skill and green GitHub CI before merge.

## 4. Locked Design Decisions (Arena Consensus)

- Centralize cache inspection for discovery and execution. Store private planned
  filesystem identity and marker text in Reclaimable; JSON response is unchanged.
- Only real namespace directories and regular markers are eligible. Resolve the
  recorded root and require it absent and under a canonical temporary prefix;
  inability to establish absence is retention, not deletion permission.
- Allow only marker plus optional state.sqlite. Preserve backups, runtime dirs,
  logs, unknown files and pre-existing SQLite sidecars; their activity/ownership
  is not established by this collector. This keeps empty fixture collection.
- Inspect a private temporary database copy with SQLite URI mode=ro, never open
  candidate SQLite, use immutable=1, db.connect/get_stats or candidate schema setup.
  Read-only WAL connections create sidecars, so isolation is required to leave
  the original namespace unchanged. Require original named file signatures
  (device/inode/size/mtime/ctime), directory identity, membership, marker and root
  to remain unchanged before/after inspection. Reject original sidecars before
  copying. Build expected schema-object definitions and table types once from
  trusted SCHEMA_SQL in memory; require them and one current schema_version.
  Unknown/old/partial layouts remain untouched.
- Probe all ordinary/logical virtual tables for any rows, except exact schema
  version and SQLite sequence infrastructure. Skip only shadow tables identified
  as shadows in the trusted schema, never arbitrary name prefixes.
- Revalidate immediately before rmtree and compare planned directory, marker and
  database identity plus root text. This fixes stale preview authority, not
  general atomic exclusion of writers starting after the last observation.
- Narrow conservative retention is enforcement of the existing provably-debris
  contract; no new useful-history deletion capability is removed.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions:** prompt lifecycle, malformed prompt-reference JSON, backend/plugin
  session writer protocol, GC Dashboard, new history windows and fleet ack floor.
- **Stop Conditions:** actual production deletion/migration requires user
  authorization. Review/CI failures block merge. If preserving supported empty
  cache collection needs a product reduction, return to Arena rather than silently
  making GC a no-op. No claim of complete concurrent-writer exclusion.

## 6. Evidence Ledger

See `06_gc_cache_evidence.md`; component analysis is
`retention_followup_arena/A_cache_preservation.md`. Independent proposals,
cross-critiques and explicit transaction-fix retraction remain in that folder.
Baseline master `218176e3`, v0.82.5, schema 14. Only current-session agent
bookkeeping was dirty when the branch was created; no user's WIP or config changed.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Measured Baseline:** completed independent Arena, disposable
  reproductions, read-only live row counts, actual cache inventory.
- **P1 — Contract Specification:** update English USER_GUIDE first then Korean;
  add exact preservation contract to SYSTEM_BEHAVIOR. No schema migration.
- **P2 — Regression Tests:** reproduce partial-schema mutation, source-independent
  durable data, unknown content, sidecars and stale-plan deletion before logic.
- **P3 — Core Logic:** implement the centralized predicate and execution recheck;
  focused pytest and ruff must pass before integration validation.
- **P4 — Testbed Smoke and Review:** testbed read-only gc plan plus isolated CLI
  deletion fixture, docs tests, full local checks and actual code-review skill.
- **P5 — Release:** align manifests 0.82.6 and changelog, release commit, PR/CI,
  merge and remove implemented plan/branch. Retain unresolved Arena findings in
  roadmap and relay for the next independently planned B1/B2 release.

## Test-Driven Revision — 2026-09-12

Normal mode=ro creates persistent WAL/SHM in closed WAL-mode candidates; 41/43
tests passed but repeated collection became a no-op. The independent reviewers
validated a private inspection copy plus original stability checks. See
`retention_followup_arena/04_inspection_revision.md`. No original sidecars are
removed and no candidate journal mode is changed. Additional regression proves
repeated preview leaves the exact original namespace file bytes unchanged.
