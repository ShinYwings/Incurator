# v0.37.0 Master Implementation Plan

Date: 2026-07-30
Status: ACTIVE — schema/wire contract approved; docs-first implementation underway.

## 1. Objective

Make cross-device deletion converge for every synchronized scalar- and
composite-primary-key table. A tombstone must identify one portable logical row,
delete it transactionally, defeat stale peer rows, permit a genuinely newer row,
and be emitted by real local hard-delete paths.

Definition of done:

- all six composite tables round-trip and delete correctly;
- stale scalar and composite rows cannot resurrect;
- source-scoped keys contain no replica-local id;
- malformed/legacy composite tokens fail closed without data destruction;
- local delete/reinsert operations leave tombstones only for rows truly absent;
- two-device plus stale-third-peer tests converge and become quiescent;
- specs/guides/tests/version/changelog and full local CI are green.

## 2. Explicit Non-Goals

- Query-provider failure UX and wikilink topology work.
- General delta sync, CRDTs, event sourcing, or whole-file database sync.
- Changing the L1–L4 storage model or sync table membership.
- Automatic repair of an ambiguous legacy composite token.

## 3. Strict Quality Conditions & Release Gates

- `SCHEMA_VERSION = 13`; all three release manifests target `0.37.0`; all four
  static spec titles target `v0.37`.
- No dynamic table/key identifier may originate from JSONL input.
- Every malformed key class produces a deterministic actionable error.
- Delete/record/stats and row/tombstone supersession are atomic per import file.
- Dry-run performs no writes.
- Unit, import/export, autosync, migration-boundary, two-device, and
  stale-third-peer tests pass.
- `scripts/backend-check pytest`, `ruff`, `mypy`, plugin Vitest/build,
  version/spec parity, and active testbed smoke pass.

## 4. Locked Design Decisions (Arena Consensus)

- Keep `deleted_records.record_id`; scalar tokens remain backward-compatible
  locally, while composite tokens are `{"key":{...},"v":1}`.
- Use one closed transport-key registry and compact sorted JSON over a restricted
  string/integer domain.
- `source_pages` and `source_pdf_pages` use `source_sync_key` on the wire.
- Upserts consult tombstones. Newer/equal tombstone skips a row; a strictly
  newer mutable row removes the older tombstone and proceeds. Immutable rows
  never supersede an existing tombstone.
- Unsupported raw composite tokens are preserved and surfaced as a sync-blocking
  migration error; they are never guessed, omitted, or deleted automatically.
- Instrument real composite hard-delete paths through shared transactional
  helpers; clear an exact older tombstone when the same logical row is live
  again.
- A source tombstone applies the same dependent cleanup required by local source
  removal.
- The related provider-UX and wikilink work remain separate PRs.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: provider errors, plugin UI, graph topology behavior, and
  unrelated sync refactors.
- **Stop Conditions**:
  - stop now for approval of the v13 transport/migration contract;
  - stop if a production legacy composite tombstone exists in the active
    testbed or user DB, because its intended key cannot be inferred;
  - stop if a source-key codec requires transmitting a local integer id;
  - stop if test evidence shows the selected delete/reinsert rule loses a newer
    live row.

## 6. Evidence Ledger

- Current schema: v12; release: v0.36.8.
- Rollback/merge-base: `831e01dd0a416c5caeaeb53842ec90f04cc7abef`.
- Current branch started from a clean, synchronized `master`.
- Existing test explicitly expects warning-only composite behavior and must be
  replaced by deletion/convergence tests.
- Current production code emits tombstones only for source and atom removals.
- Current testbed is the ResNet Dynamics scenario; external PDF/reference paths
  must remain untouched during sync validation.
- Detailed evidence: `.agents/plans/02_composite_tombstone_evidence.md`.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Measured Baseline**
  - Freeze current failing behaviors: warning-only composite delete, stale-peer
    resurrection, realistic source-delete FK failure, and absent local composite
    emission.
  - Record current schema/manifest/testbed state.
- **P1 — Contract Specification**
  - Update all schema/system/plugin/search spec titles to v0.37.
  - Define v13 transport keys, timestamp ordering, migration failure, and source
    cleanup in schema/system specs and EN then KR guides.
  - Stop for approval before this phase begins.
- **P2 — TDD Oracles**
  - Replace warning characterization with failing exact-delete tests for six
    tables.
  - Add malformed-key, timestamp boundary, dry-run, source portability,
    realistic source cleanup, stale resurrection, and local emission tests.
- **P3 — Codec And Migration Boundary**
  - Implement the closed registry, exact validation, canonical encoder/decoder,
    source-key resolution, v13 boundary, and legacy fail-closed diagnostics.
  - Verify focused pytest + ruff.
- **P4 — Delete/Upsert Convergence**
  - Apply full-key transactional deletes and tombstone-aware upserts.
  - Centralize realistic source dependent cleanup.
  - Verify focused pytest + ruff.
- **P5 — Local Composite Emission**
  - Instrument actual hard-delete/reinsert sites so only absent logical rows keep
    tombstones.
  - Verify pipeline and DB characterization tests.
- **P6 — Integration And Testbed Smoke**
  - Run two-device/three-peer autosync, full backend/plugin CI, build, version
    parity, and ResNet testbed status/sync/lint without reinitializing or copying
    external resources.
- **P7 — Release**
  - Update changelog/roadmap/relay, delete completed v0.37 plan artifacts,
    create `chore(release): v0.37.0`, push, open PR, and monitor CI/review.
