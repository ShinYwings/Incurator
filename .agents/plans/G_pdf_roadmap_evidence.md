# Evidence Ledger — PDF Handling Unification (Plan G)

Date: 2026-06-19
Status: PRE-CODING. Populated during planning; P0 will append measured baselines.

## 1. Rollback Anchor

- Branch base: **`feature/agent-context-service`** (Plan F, committed checkpoint
  `3c05f08`). Plan G runs on `feature/pdf-unified-handling` branched OFF the F
  branch — a deliberate exception to the no-nesting convention, because Plan G's
  backend P2 (`asset_identity.resolve()` routing `_locator_from_span`) depends on
  Plan F's `context_service.py`, which does not exist on `master`
  (verified 2026-06-19: `git cat-file -e master:.../context_service.py` → MISSING).
- Consequence: Plan G CANNOT be merged before Plan F merges. When Plan F merges
  to `master`, rebase `feature/pdf-unified-handling` onto updated `master`.
- No DB schema migration is planned (additive-only if any). Rollback = revert the
  feature branch; no data migration to undo.

## 2. Current Repository & Schema Reality (verified 2026-06-19)

- `sources` table carries: `relpath` (NOT NULL UNIQUE — the stub for Reference
  Mode), `external_path`, `import_origin`, `is_reference`, `logical_source_id`,
  `content_hash`, `file_type` (`backend/src/curator/db.py:83-110`).
- Reference Mode: in-vault markdown stub + `external_path` to the real file;
  both `add_file` and `generate_l1_structural_context` resolve the real PDF via
  `_resolve_reference_source` (verified — L1 is NOT poisoned by the stub).
- Locator: `_locator_from_span` labels reference PDFs `source_kind="vault_pdf"`
  with `external_uri` set; SYSTEM_BEHAVIOR §29.2 now states `external_uri` is
  authoritative for opening (updated this session).
- Spans carry their own `page_number` (`pipeline/source_spans.py:94,123`), so
  reference-PDF page locators resolve independently of `source_pdf_pages`.

## 3. Current Dirty Worktree (do not overwrite)

Plan F P6 work is uncommitted on `feature/agent-context-service`, including this
session's locator fix (`incuratorQueryTrace.ts` + 3 tests), the SYSTEM_BEHAVIOR
§29.2 / PLUGIN_SCHEMA / EN+KR guide clarifications, and the audit entry in
`USER_REPORT.md`. Plan G must branch off `master`, not bundle Plan F's diff.

## 4. Baseline Measurements (P0 — recorded 2026-06-19)

- [x] **PDF module LOC baseline = 4601** (`wc -l` total of: externalPdfView,
      externalPdfState, pdfCapture, pdfReferenceContext, pdfTextLayout,
      crossReferenceResolver, quickQueryContext, providerContextFormat,
      utils/zoteroUtils + backend zotero{,_tools,_integration}). Net-LOC gate
      target: final total < 4601.
- [x] **Backend dedup-parity characterization pinned.** New test
      `test_copy_and_reference_of_same_file_stay_distinct_rows`
      (`backend/tests/test_mcp_source_tools.py`) confirms copy mode (dedup by
      relpath) and reference mode (dedup by logical_source_id/external_path)
      yield two distinct `sources` rows for the same file. P2 facade must keep
      this green (schema_guardian C4 gate). Suite: 16 passed.
- [x] **Persisted-doc format characterization pinned.** New test file
      `plugin/src/ui/externalPdfPersistence.test.ts` (4 tests) pins
      `STORAGE_KEY = "incurator-obsidian-agent-external-pdfs"`, the
      `[id, {id,name,path}]` serialized shape, and load-time retention via
      `isRetainablePersistedDoc`. P4 registry extraction must keep this green.
- [x] **Item-3 repro: ANALYTICALLY CONFIRMED, fix deferred to P3.** Repro path:
      a Zotero PDF with no initial local path caches its status under
      `zotero:<key>`; after add, `nextStatus.sourcePath` becomes truthy, so the
      re-render reads `incuratorStatusByPath.get(sourcePath)` and MISSES the
      `zotero:<key>` entry → badge shows `unknown`. Not unit-testable without DOM
      scaffolding; the single-`assetStatusKey` fix + regression test lands in P3.
- [ ] Testbed E2E snapshot for the three flows — deferred to P5 (no testbed init
      yet; consistent with Plan F deferral).

Plugin suite after P0: **389 passed** (was 385, +4). Backend source-tools: 16.

## 4a. P1 Contract Specification (recorded 2026-06-19)

- [x] **Backend `AssetIdentity` contract** added as SYSTEM_BEHAVIOR §29.6 (resolution
      authority absorbing `_resolve_reference_source`, `_default_logical_source_id`,
      `zotero_tools.resolve_pdf`; `resolution_status` enum; open-target rule). No
      DB schema change.
- [x] **Plugin `AssetSource` + `assetStatusKey` contract** added as PLUGIN_SCHEMA §1.2
      (single resolver/key; `as any` removal; item-5 badge states documented as
      intended). No wire/settings change.
- [x] **relpath-first consumer audit (items 1/2 follow-up)** — CLEAN. Only the
      Sources & Trace locator opened by relpath (fixed in P6). `providerContextFormat`
      formats text only; `incuratorDashboardModal` uses relpath as a display label
      only; other `getAbstractFileByPath` calls operate on open-note `ref.filePath`,
      not query-result locators. No further open-by-stub bug exists.
- [x] **Folded-in scope**: ROADMAP item 5's non-annotation follow-up
      (external-image-attachment-to-`.md` asset routing) recorded in master plan
      §1a; annotation system + in-PDF full-text search explicitly EXCLUDED.
- Spec-sync test: 9 passed (version headers intact; "Plan G target, vNEXT"
  sections follow the Plan F convention).

## 4b. P2 Backend Resolver Facade (recorded 2026-06-19)

- [x] **`backend/src/curator/asset_identity.py`** added: `AssetIdentity` dataclass +
      `from_source_row()` (cheap, no I/O) + `resolve()` (facade over Zotero
      resolution / logical-id derivation / sources-row lookup). No DB mutation,
      no dedup SQL change.
- [x] `_locator_from_span` (context_service.py) routed through
      `asset_identity.from_source_row` — is_reference + external open-target now
      come from the single authority. Behavior-preserving (P6 locator tests +
      Plan F contract tests stay green).
- [x] `ingest_raw._default_logical_source_id` delegates to
      `asset_identity.default_logical_source_id` (single source of truth; identical
      hash, no behavior change).
- [x] Backend Zotero resolution stays on the single `zotero_tools.resolve_pdf`;
      `plugin_api.import_source` keeps its direct call to preserve its structured
      error payload (same single implementation — C2 honored).
- **dedup-parity gate: GREEN.** `test_copy_and_reference_of_same_file_stay_distinct_rows`
      still passes; no dedup branch merged (schema_guardian C4 satisfied).
- Validation: focused 46 passed; `ruff` clean; `mypy` no issues in 96 files;
      **full backend suite 933 passed, 6 skipped, 5 xfailed, 0 failed**.

## 5. Rollback Requirements

- No destructive op before P4 (deletions). Each P4 deletion is its own commit so
  it can be reverted independently.
- Renderer extraction commits must keep `externalPdfView.ts` importable and the
  persisted-doc map intact at every step; a failed rehydration test halts P4.
