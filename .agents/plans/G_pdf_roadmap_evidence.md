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

## 4c. P2 Review Hardening (recorded 2026-06-19)

Reviewer findings on `asset_identity.py`, all addressed with tests:
- [x] **Stale-path trust** — `from_source_row(..., verify_exists=True)` stats the
      external file; a Reference Mode source whose file moved/was deleted is
      downgraded to `path_unresolved` with `abs_path=None`. `resolve()` uses
      `verify_exists=True`. (`from_source_row` default stays no-I/O for the
      locator hot path.) Tests: `test_verify_exists_downgrades_phantom_external_path`,
      `test_resolve_downgrades_tracked_reference_with_deleted_file`.
- [x] **Ambiguous param / collision** — `resolve()` now does a strict, isolated
      `WHERE logical_source_id = ?` query instead of smuggling the logical id
      through `db.get_source_row`'s `relpath` OR clause. The isolated query is
      kept LOCAL to `asset_identity` rather than added to `db.get_source_row`,
      because `db.py`'s whole-file SHA256 is pinned by the frozen Plan D2 holdout
      (`docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`); editing `db.py` for an
      unrelated refactor would break that consume-once integrity artifact. The
      reviewer's intent (isolated matching, no collision) is fully satisfied.
      Test: `test_logical_source_id_lookup_is_isolated_from_relpath_collision`.
- [x] **State leakage via `replace()`** — a matched vault (non-reference) row no
      longer inherits caller-provided Zotero/reference identity; only
      `content_hash` is backfilled. Reference rows still merge same-entity fields.
      Test: `test_vault_row_does_not_inherit_caller_zotero_identity`.
- [x] **UNTRACKED `is_reference` inconsistency** — effective Zotero key derived
      from `zotero_key` OR a `zotero:<key>` logical id, so `is_reference` and
      `zotero_key` are consistent even when only `logical_source_id` is passed.
      Test: `test_untracked_zotero_logical_id_implies_reference_and_key`.

## 4d. P3 Review Round 2 — fact-check verdicts (recorded 2026-06-19)

Reviewer re-sent findings; fact-checked against committed code:
- **Popover (quickQueryPopover.ts) 5 findings** — DUPLICATE of the earlier
  message; already captured in `USER_REPORT.md` + folded into ROADMAP 4.1,
  queued AFTER Plan G. No action.
- **chatSidebar status-key collision (old 2049 vs 2147)** — ALREADY FIXED in P3
  `49da211` (single `refStatusKey`/`assetStatusKey` for read+write). Reviewer
  cited pre-P3 lines.
- **chatSidebar `as any` Zotero probe** — ALREADY FIXED in P3 (typed). The new
  sub-point (identity coupled to open UI leaves via `getLeavesOfType`) is VALID
  and now FIXED: `isZoteroPdf = Boolean(ref.zoteroAttachmentKey)` — durable ref
  identity, tab-scan removed entirely. Contract test updated.
- **externalPdfView god-class (147-212): registry/persistence/Zotero traversal
  in UI module** — matches Plan G **P4** (extract `externalPdfRegistry.ts`;
  delegate Zotero to backend). Pending P4.
- **externalPdfView stale localStorage path cache (330)** — folded into P4: when
  backend AssetIdentity resolves a NEW physical path, the persisted
  `externalPdfDocs`/localStorage entry must be overwritten/invalidated (extends
  the §1.2 cache-invalidation contract to the docId→path map). Pending P4.
- **externalPdfView getActivePdfContext capture/RAG coupling (551)** — ADDED TO
  SCOPE per user (2026-06-19) as **P4b**: extract a decoupled `PdfCaptureService`
  from the view (capture/RAG/Canvas extraction) so it is unit-testable without an
  Obsidian `ItemView`. Distinct from `pdfCapture.ts` module internals (still a
  non-goal).

### Device-portability (user note 2026-06-19)
Vault and Zotero locations differ per device/OS (macOS `/Users/...` vs Linux
`/home/...`; `~` expands per home dir). Handling:
- `zoteroCacheEpoch()` now folds in `process.platform` + the OS-resolved
  (`~`-expanded) base path, so the in-memory per-device cache can never serve a
  path resolved for another device/OS (committed in P3 c follow-up).
- Persisted / synced absolute paths (`externalPdfDocs` localStorage, backend
  `external_path`) are hints only and MUST be re-resolved per device via the
  backend resolver / Reference Mode rebind — enforced in P4. Documented in
  PLUGIN_SCHEMA §1.2.

### Device-sync audit addendum (recorded 2026-06-19)

User asked to re-check Plan G against the actual macOS/Linux sync topology before
continuing P4. Facts verified:
- Active vault `.stignore` ignores `.obsidian/workspace.json`,
  `.obsidian/plugins/incurator-obsidian-agent/data.json`, `.curator/state.sqlite`,
  `.curator/runtime/`, and `testbed/`. It does **not** ignore
  `.curator/sessions.json`; plugin docs explicitly allow session sync.
- Backend `sources.external_path` lives in ignored `state.sqlite`, so it is
  device-local. Reference stubs and Zotero logical ids are the portable shared
  surface.
- Plugin `data.json` is ignored, so `zoteroBasePath` and backend launcher paths
  are device-local.
- `externalPdfDocs` is Obsidian/Electron localStorage, not a vault file, so it is
  local to the current Obsidian profile; nevertheless P4 still treats it as a
  stale local hint and re-resolves paths when possible.
- **Gap found:** `.curator/sessions.json` stores `ChatMessage.contextRefs`.
  `ContextRef.filePath` and `ContextRef.backendStatus.sourcePath/currentPath/
  candidatePath` can contain absolute paths captured from external PDF tabs.
  Because sessions can sync, a macOS path could land on Linux or vice versa.

Plan adjustment: P4 must add a session-sync guard before finalization. Persisted
context refs must strip or verify device-local absolute path fields and keep
portable identifiers (`zoteroAttachmentKey`, `fileHash`, vault-relative relpath,
page number) so the current device re-resolves via `AssetSource` / backend
resolution instead of trusting another device's path.

## 4e. P3 c/d/e (recorded 2026-06-19)

- [x] **(c) ZoteroPathCache wired into the live path.** `resolvePdfRefSourcePath`
      now routes Zotero resolution through `resolveAssetSource` + the view's
      `ZoteroPathCache` (cache hit skips the backend round-trip; local resolver
      only when offline). Epoch derived from settings via `zoteroCacheEpoch()`
      (zoteroBasePath + vault name + profile asset roots). The structured error
      resolution is captured by closure for the repair modal (no double call).
- [x] **(d) External-image identity preserved.** `attachNativeFile` injects
      `filePath: explicitPath ?? file.path` into the image ContextRef so the
      physical asset identity survives the UI boundary (was dropped → base64
      only). NOTE: the broader §1a backend routing of *editor-attached* note
      images to the profile asset location is a DISTINCT flow (not chat attach);
      verify separately in P5 — not claimed done here.
- [x] **(e) isAddedState unit-tested.** Extracted to pure
      `plugin/src/context/sourceStatus.ts` (no Obsidian deps) + `ADDED_STATES`
      single source of truth; chatSidebar imports it. `sourceStatus.test.ts`:
      5 tests covering layer-ready states, in-progress states, empty/fallback/
      drifted strings, and case-sensitivity (re-ingest gatekeeper, schema drift).
- Validation: plugin suite 407 passed (+5); tsc clean. (No backend changes.)

## 4f. P4 Registry Extraction + Device Sync Guard (recorded 2026-06-19)

- [x] **`externalPdfRegistry.ts` extracted.** `externalPdfView.ts` no longer owns
      `STORAGE_KEY`, `loadPersistedDocs`, `persistDocs`,
      `registerExternalPdf`, `registerExternalPdfByPath`, or local
      `resolveZoteroAttachmentPath`; callers import those from the registry
      boundary.
- [x] **Stale `docId -> path` replacement added.** Zotero URL open now reuses an
      existing external PDF leaf by `zoteroAttachmentKey` as well as by path, and
      updates the persisted doc path when the backend resolves the same
      attachment to a new physical path.
- [x] **Session sync guard added.** `normalizeSessionData`/`mergeSessionData`
      sanitize persisted message `contextRefs`: absolute device paths are
      stripped from `ContextRef.filePath`, volatile `backendStatus` is removed,
      and portable identity (`zoteroAttachmentKey`, `fileHash`, vault-relative
      path, page) is preserved.
- [x] Docs/specs updated: PLUGIN_SCHEMA §1.2, EN/KR plugin guide session sync,
      EN/KR sync ignore guide, and this Plan G/evidence note.
- Validation: `npx tsc --noEmit` passed; full plugin `npx vitest run -c
      ./vitest.config.ts` passed (**47 files / 411 tests**); `git diff --check`
      passed.
- LOC gate status: **not yet satisfied**. Current measured PDF module total is
      4649 vs P0 baseline 4601 (+48). P4b/P4 follow-up must reduce below 4601
      before Plan G can close.

## 4g. P4b PdfCaptureService Extraction (recorded 2026-06-19)

- [x] **`PdfCaptureService` extracted.** `externalPdfView.getActivePdfContext`
      now delegates to `plugin/src/ui/pdfCaptureService.ts`, passing only DOM
      nodes, page cache, current page state, document metadata, selection getter,
      and search index. Capture/RAG/canvas-image composition is unit-testable
      without instantiating an Obsidian `ItemView`.
- [x] **Service tests added.** `pdfCaptureService.test.ts` covers cached text +
      RAG composition and null page-element handling using fake DOM/search
      dependencies.
- Validation: `npx tsc --noEmit` passed; full plugin `npx vitest run -c
      ./vitest.config.ts` passed (**48 files / 413 tests**); `git diff --check`
      passed.
- LOC gate status: **still not satisfied**. Current measured PDF module total is
      4704 vs P0 baseline 4601 (+103). `externalPdfView.ts` dropped to 1889
      lines, but new service/registry modules mean Plan G still needs additional
      deletion/slimming before final closure.

## 4h. P4 Net-LOC Gate Closure (recorded 2026-06-19)

- [x] **Dead text extraction promise path deleted.** Removed unused
      `getOrExtractPageText()` and `pageTextPromises`; `extractPageTextFromPdfJs`
      is the single rendered-page text path used by the viewer.
- [x] **Toolbar duplicate button code collapsed.** Repeated icon-button creation
      now goes through `createToolbarIcon()`.
- [x] **Registry glue compacted.** `externalPdfRegistry.ts` keeps the same
      persisted `[id, {id,name,path}]` contract and stale path replacement API
      while removing excess wrapper/comment lines.
- LOC gate: **GREEN**. Current measured PDF module total is **4598**, below the
      P0 baseline **4601**. `externalPdfView.ts` is now 1822 lines.
- Validation: `npx tsc --noEmit` passed; full plugin `npx vitest run -c
      ./vitest.config.ts` passed (**48 files / 413 tests**); `git diff --check`
      passed.

## 5. Rollback Requirements

- No destructive op before P4 (deletions). Each P4 deletion is its own commit so
  it can be reverted independently.
- Renderer extraction commits must keep `externalPdfView.ts` importable and the
  persisted-doc map intact at every step; a failed rehydration test halts P4.
