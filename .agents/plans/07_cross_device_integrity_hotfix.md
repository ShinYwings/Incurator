# v0.32.1 Cross-Device Integrity Master Implementation Plan

Date: 2026-07-05
Status: APPROVED — user explicitly requested inclusion in the current update.

## 1. Objective

Make two independently running device replicas converge without source loss,
deletion resurrection, generation rollback, unsafe JSONL import, or synchronized
machine-local files. Keep the release in the open v0.32.1 PR.

## 2. Explicit Non-Goals

- Supporting v11 JSONL snapshots after schema v12 activates.
- Supporting simultaneous edits to the same logical source.
- Moving `.curator/Collections` out of the vault.
- Reintroducing `wiki paths` or a manual path migration command.

## 3. Strict Quality Conditions & Release Gates

- Disjoint id-1 sources converge to two sources with correct child provenance.
- Source deletion converges and remains deleted after stale snapshot replay.
- Authoritative generations cannot regress to staged/discarded stale state.
- Import rejects non-allowlisted tables and unknown columns.
- Machine-local files are absent from the vault after exercised workflows.
- Backend/plugin suites, Ruff, mypy, TypeScript, build, and testbed smoke pass.

## 4. Locked Design Decisions (Arena Consensus)

- Package/plugin version remains v0.32.1 by explicit user override; DB schema is
  v12.
- `sources.sync_key` is the transport identity; integer `id` stays local.
- Child `source_id` values are remapped during import.
- Source deletes emit `sync_key` tombstones.
- `compiler_generations.updated_at` and source revisions are monotonic.
- JSONL headers carry `export_id`; peer state does not use mtime as identity.
- Machine state lives in repo `.cache/vaults/<vault-key>/`.
- Shared sessions/profiles use serialized merge and explicit tombstones.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: simultaneous same-source semantic merge and central-server
  coordination.
- **Stop Conditions**: stop before touching production if both old and new DB
  locations exist or SQLite integrity fails.

## 6. Evidence Ledger

- Current branch: `hotfix/v0.32.1-sync-device-identity`.
- Current package version: v0.32.1; DB schema: v11.
- Worktree was clean before this expanded plan.
- Production backup already exists under
  `.cache/migrations/v0.32.1/20260704T042823Z/`.
- Detailed pre-change evidence is in
  `.agents/plans/07_roadmap_evidence.md`.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Baseline**: preserve reproduced failures and storage inventory.
- **P1 — Contract Specification**: update all core specs and paired EN/KR guides.
- **P2 — DB Schema/Transport**: tests first; schema v12, source remap,
  tombstones, generation revision, allowlist, export identity.
- **P3 — Storage Boundary**: tests first; cache paths and one-time relocation.
- **P4 — Plugin/Shared State**: tests first; temp paths, serialized saves,
  reset/session/profile behavior.
- **P5 — Integration**: full local CI and cross-device replica tests.
- **P6 — Testbed/Release**: complex-math testbed, roadmap cleanup, final release
  commit, push, and PR update.

