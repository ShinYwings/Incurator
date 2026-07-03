# v0.31.0 Master Implementation Plan

Date: 2026-07-03
Status: APPROVED — implementation and production repair verified

## 1. Objective

Make pipeline counts and per-source L1-L4 status converge from authoritative DB
state across devices, repair the Reference Mode L1 failure path, and safely
reconcile the production `second_brain` vault. Done means the dashboard reports
31 L1 contexts for the measured baseline, L3/L4 readiness requires actual
serving artifacts, status-only mutations sync, impossible L1/downstream
combinations are prevented, and stale projection files are re-emitted rather
than treated as truth.

## 2. Explicit Non-Goals

- Do not reverse-import CTX/ATM/CON/SYN Markdown into the DB.
- Do not edit `03_Notes`, `04_Resources`, or `06_Archives`.
- Do not redesign the L1-L4 model or introduce a central sync server.
- Do not claim recovery of historical L4 rows absent from every peer snapshot.
- Do not continue unrelated System Stability Overhaul decomposition.

## 3. Strict Quality Conditions & Release Gates

- DB-derived L1 count equals `COUNT(sources WHERE l1_status='done')`.
- L2/L3/L4 counts equal the serving sets used by projection re-emission.
- A source status mutation with no artifact change triggers export and wins LWW
  on a peer with an older source revision.
- Import preserves the remote source revision and a second import is a no-op.
- Missing derived CTX repair cannot downgrade an otherwise valid L1 row.
- Unresolved reference stubs never ingest their own placeholder text as the PDF.
- A source cannot be `l3_ready` without a live community report grounded in that
  source's spans.
- `l4_ready` requires at least one current shared synthesis node; a completed
  no-eligible pass is `skipped`, not a false ready state.
- Schema v10→v11 migration is idempotent and covered by upgrade tests.
- English docs/specs are updated before synchronized Korean guides.
- Full backend pytest/ruff/mypy and plugin vitest pass.
- The active Reference Mode testbed scenario reproduces before and passes after.

## 4. Locked Design Decisions (Arena Consensus)

- Add schema-v11 `sources.updated_at`; use it as source LWW metadata.
- Backfill and normalize existing source revisions during migration.
- Cover raw SQL mutation sites with a guarded DB mechanism, while proving import
  does not restamp remote rows.
- Parse timestamp instants in export gating instead of comparing mixed timestamp
  strings lexically.
- Replace filesystem `layer_counts` with authoritative serving DB counts.
- Derive per-source L3 completion from live report provenance; use `skipped` for
  an exception-free pass with no eligible L3 output. L4 done means a current
  shared synthesis corpus exists.
- Separate source validity from disposable projection repair.
- Recognize `zotero_attachment_key` and legacy `zotero_key`.
- Recover production canonical data only from peer JSONL snapshots or rebuild.
- Absorb the related deferred v0.30.1 sync-hardening work: atomic JSONL/state
  writes, serialized read-merge-write Zotero profiles, MCP/worker export hooks,
  export deduplication, and shared recent-item limits.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: UI redesign, new pipeline stages, old projection reverse parser.
- **Stop Conditions**:
  - stop before production repair without verified backups;
  - stop if schema migration changes row counts or fails `PRAGMA integrity_check`;
  - stop if peer snapshots contain irreconcilable equal-revision source rows;
  - report/rebuild rather than fabricate L4 if canonical synthesis rows are gone;
  - stop testbed LLM stages only on a documented provider/auth blocker.

## 6. Evidence Ledger

- Evidence file: `.agents/plans/07_roadmap_evidence.md`.
- Production DB and filesystem were inspected read-only.
- User-owned untracked draft is preserved.
- Rollback requires DB/WAL/SHM and sync-snapshot backups before repair.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Approval + Baseline**: confirm the active testbed scenario; record
  rollback commit and production backup hashes. Verify DB integrity and peer
  snapshot inventory.
- **P1 — Contract Specification**: update all four static spec titles to v0.31,
  define source revisions, serving-count semantics, projection repair, and
  Reference Mode resolution. Update English guides first, then Korean pairs.
- **P2 — Failing Migration/Sync Tests**: add schema-v11 migration, timestamp
  preservation, status-only export, same-instant gate, idempotence, and loop
  tests. Run targeted pytest + ruff.
- **P3 — Source Revision Implementation**: add/backfill `sources.updated_at`,
  wire LWW/export gating, and pass P2 plus existing DB sync suites.
- **P4 — Failing Status/L1 Tests**: reproduce 65-vs-31 counts, retired/staged
  exclusion, false L3 done with zero reports, per-source report provenance,
  L4 done without synthesis, missing-projection downgrade, emitted Zotero-key
  resolution, and downstream invalidation rules.
- **P5 — Status/L1 Implementation**: implement serving DB counts, projection-safe
  L1 publication/repair, and portable reference resolution. Run targeted pytest
  + ruff.
- **P6 — Deferred Sync Hardening**: atomic temp+rename JSONL/state writes;
  queued read-merge-write profile persistence; MCP/worker export triggers;
  one export per compound command; shared profile LRU limit. Add Python and
  TypeScript tests and update paired docs.
- **P7 — Projection and Testbed Validation**: initialize the confirmed scenario,
  reproduce before/after including Reference Mode, re-emit projections from DB,
  and run status/add/build/sync smoke checks. Restore any temporary vault config.
- **P8 — Production Repair**: back up production state, import available peer
  snapshots, migrate, re-emit projections, retry only invalid L1 sources, and
  verify 31 L1 plus truthful L2-L4 counts. Never use stale Markdown as recovery.
- **P9 — Full CI and Release**: run `scripts/backend-check pytest`, `ruff`,
  `mypy`, and plugin vitest; bump backend/plugin manifests to 0.31.0, synchronize
  static spec title lines, update CHANGELOG, clean roadmap/report/plan artifacts,
  commit `chore(release): v0.31.0`, push, and open the PR.
