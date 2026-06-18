# vNEXT Master Implementation Plan — PDF Handling Unification & Simplification

Date: 2026-06-19
Status: APPROVED (2026-06-19) — Arena debate concluded; user approved execution.
Branch: `feature/pdf-unified-handling`, branched off `feature/agent-context-service`
(Plan F checkpoint `3c05f08`) because backend P2 depends on Plan F's
`context_service.py` (absent on `master`). Rebase onto `master` after Plan F merges.
Arena: `.agents/plans/G_pdf_unified_handling_arena/`

## 1. Objective

Reduce the structural complexity of the three PDF flows — **Reference Mode**,
**Add source (pin)**, and **Obsidian agent ↔ PDF viewer** — by introducing a
single PDF-identity resolution authority on each side (backend + plugin), routing
all call sites through it, and then deleting the redundant private resolvers and
slimming the `externalPdfView.ts` god class. Close audit items 3/4/5.

**Definition of done:**
1. Backend: one `asset_identity.resolve()` facade; `_resolve_reference_source`,
   `_default_logical_source_id`, and Zotero resolution reachable only through it.
2. Plugin: one `AssetSource` model + `resolveAssetSource()` + `assetStatusKey()`; badge
   status map keyed by exactly one canonical key; `as any` Zotero detection gone.
3. `externalPdfView.ts` reduced to render + view-state (registry/persistence
   extracted), target < ~1200 LOC. Its data-extraction / RAG-composition
   (`getActivePdfContext`) is moved out into a decoupled `PdfCaptureService`
   (review finding 5, added to scope per user 2026-06-19) so capture logic is
   unit-testable without instantiating an Obsidian `ItemView`.
4. Synced chat session state (`.curator/sessions.json`) never treats
   device-specific absolute PDF/Zotero paths or `backendStatus.*Path` fields as
   durable truth. Persisted context refs keep portable identity
   (`zoteroAttachmentKey`, `fileHash`, vault-relative relpath/page) and re-resolve
   paths on the current device; stale synced absolute paths are verified or
   stripped before use.
5. Audit items 3 (repro-or-close), 4 (fixed), 5 (clarified) resolved with tests.
6. Measured **net LOC decrease** across PDF modules, zero test regressions, all
   three flows verified in the testbed.

## 1a. Folded-in Scope from ROADMAP Item 5 (non-annotation only)

Per user direction (2026-06-19), Plan G also absorbs the **non-annotation** PDF
bug items from ROADMAP item 5 / `.agents/drafts/pdf_annotation_system.md`
("PDF / Zotero Asset Location Management"). Triage of that section:
- asset-location routing for extracted PDF images → SHIPPED v0.5.6 (no-op here);
- "Added" add-source button state → SHIPPED v0.5.6 (no-op here);
- Zotero reload relativepath bug → FIXED v0.5.5 (no-op here);
- **OPEN → in scope for Plan G**: external-image-attachment-to-`.md` routing —
  when a user attaches an external image to a markdown note, route it to the
  source's profile-matched asset location with `05_Assets` as the fallback,
  reusing the v0.5.6 `--asset-dir` mechanism. This shares Plan G's asset/path
  resolution concern (D1) and the add-source flow, so it rides the unified
  resolver rather than getting a separate ad-hoc path. **Verify-or-implement**
  during P3/P5 (confirm whether any partial handling already exists first).

## 2. Explicit Non-Goals

- NOT building the native PDF annotation system (`pdf_annotations` table,
  highlight/memo, Canvas integration, source_spans promotion) — that stays in
  ROADMAP item 5's annotation track, explicitly EXCLUDED per user.
- NOT adding in-PDF full-text search or strict-spelling mode (annotation-track
  features, not bugs).
- NOT refactoring `crossReferenceResolver.ts` or `pdfCapture.ts` internals
  (boundary-adapt only). NOTE: `externalPdfView.getActivePdfContext` capture/RAG
  extraction into a `PdfCaptureService` IS in scope (finding 5, P4b) — distinct
  from the `pdfCapture.ts` module internals.
- NOT changing the storage model or Reference Mode semantics (no hard-copy).
- NOT merging the dedup SQL of the reference vs copy ingest branches.
- NOT changing PDF.js rendering behavior, zoom/scroll/snipping UX.
- NOT adding new dependencies.

## 3. Strict Quality Conditions & Release Gates

- 100% of existing backend + plugin tests pass at every phase boundary
  (`scripts/backend-check pytest|ruff|mypy`, `npx vitest run`, `npx tsc`).
- **Dedup parity gate**: reference/copy/zotero ingest produce the same `sources`
  rows before and after (regression tests from P0).
- **Net-LOC gate**: total LOC of the PDF module set (see 00_problem table)
  strictly decreases; report the before/after delta in the PR.
- **Behavior-parity gate**: testbed E2E for all three flows matches pre-refactor
  output.
- schema_guardian sign-off before P2 lands.

## 4. Locked Design Decisions (Arena Consensus)

- Strangler pattern, not rewrite. Resolver introduced as a **facade** over
  existing functions; callers routed one at a time; dead resolvers deleted only
  when caller count hits zero.
- **Generic naming, not PDF-specific.** Because Plan G folds in external-image
  asset routing (§1a), the abstractions are named `AssetIdentity` /
  `asset_identity.py` (backend) and `AssetSource` / `assetSource.ts` (plugin) —
  NOT `Pdf*` — so they accurately cover PDFs, markdown, and images.
- `AssetIdentity` (backend) / `AssetSource` (plugin): all fields optional + an
  explicit `resolution_status` enum (`resolved | path_unresolved | untracked`),
  mirroring `locator_status`.
- "Single entry point, not single implementation": plugin keeps a local Zotero
  fallback used only when the backend command is unavailable.
- **Zotero fallback cache invalidation is mandatory** (per review): the plugin's
  optional `attachment_key → absPath` hot-path cache is tied to the workspace
  configuration epoch, cleared on plugin reload, in-memory only, and a cached
  path whose file is gone is treated as a miss. Specified in PLUGIN_SCHEMA §1.2.
- `external_uri` is authoritative for opening whenever present (already specified
  in SYSTEM_BEHAVIOR §29.2 this session); all consumers must honor it.
- `.curator/sessions.json` may sync between macOS/Linux, so session-stored
  `ContextRef` objects are NOT allowed to preserve device-local absolute paths as
  identity. They must either keep vault-relative paths, or keep portable
  identifiers and ask `AssetSource`/backend resolution to recover the current
  device's real path.
- Renderer extraction is last and incremental (registry first), preserving
  module-load timing for persisted-doc rehydration.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: cross-reference resolver and pdfCapture internals; any dedup-key
  change; new OCR/scanned-PDF handling.
- **Stop Conditions**:
  - STOP if dedup parity tests cannot be made green → identity model is wrong.
  - STOP if persisted-doc rehydration breaks during renderer extraction.
  - STOP and ask before deleting any backend public function still imported
    elsewhere.

## 6. Evidence Ledger

See `.agents/plans/G_pdf_roadmap_evidence.md` (rollback anchor, current schema
reality, dirty-worktree state, pre/post validation). Created before P0 coding.

## 7. Execution Phases (TDD + CI each phase)

- **P0 — Research & Baseline.** Characterization tests for: reference/copy/zotero
  ingest dedup (`sources` rows), persisted-doc rehydration, all-three-flow
  testbed snapshot. Record baseline LOC. Attempt an item-3 repro test.
  Verify: new tests pass and pin current behavior.
- **P1 — Contract Specification (docs-first; STOP for approval).** Define
  `AssetIdentity` / `AssetSource` + `resolution_status` in `docs/specs/` (+ EN/KR
  guides). Audit & list every relpath-first consumer (items 1/2 follow-up).
- **P2 — Backend resolver facade.** Add `asset_identity.resolve()` wrapping existing
  functions; route `import_source` + `_locator_from_span` through it. No dedup SQL
  change. Verify: `pytest`/`ruff`/`mypy` + dedup parity gate.
- **P3 — Plugin resolver + state machine.** Add `assetSource.ts`; route badge/source
  call sites; single `assetStatusKey`; remove `as any` Zotero detection (item 4);
  resolve/close item 3 (single key + regression test); clarify `isAddedState`
  states (item 5). Implement the mandatory Zotero-fallback **cache invalidation**
  (config-epoch tied + reload-cleared + missing-file = miss; PLUGIN_SCHEMA §1.2)
  with a regression test. Verify-or-implement the folded
  external-image-attachment-to-`.md` asset routing (§1a) through the unified
  resolver / `--asset-dir`. Verify: `vitest` + `tsc`.
- **P4 — Delete dead resolvers + slim renderer.** Remove now-unused private
  resolvers; extract `externalPdfRegistry.ts` (registry/persistence + Zotero
  traversal) from `externalPdfView.ts`, one move per commit. Also: when backend
  `AssetIdentity` resolution yields a NEW physical path, overwrite/invalidate the
  persisted `externalPdfDocs` localStorage entry for that docId (review finding —
  stale persisted path across restarts). **Device-portability:** persisted /
  synced absolute paths are device-specific (macOS vs Linux, `~` expansion) and
  MUST be re-resolved per device via the backend resolver / Reference Mode
  rebind, never trusted verbatim (PLUGIN_SCHEMA §1.2). Add the session-sync
  guard: sanitize persisted `ContextRef` / `backendStatus` path fields so
  `.curator/sessions.json` can sync safely between
  `/Users/shin/shinywings/second_brain` and `/home/shin/Workspace/second_brain`
  while Zotero paths re-resolve via the local `~/Zotero` database / ZotMoov
  roots. Verify: net-LOC gate + all tests.
- **P4b — Extract `PdfCaptureService` (review finding 5).** Move
  `externalPdfView.getActivePdfContext` data-extraction / RAG-composition /
  Canvas-image extraction out of the view into a decoupled service that receives
  the view's DOM/Canvas nodes, so capture is unit-testable without an Obsidian
  `ItemView`. Verify: new unit tests for the service + `vitest`/`tsc`.
- **P5 — Testbed E2E + docs sync.** Run reference/add-source/agent-PDF scenarios
  in the testbed; confirm behavior parity; finalize EN/KR docs; version bump +
  changelog per Universal Strict Workflow.
