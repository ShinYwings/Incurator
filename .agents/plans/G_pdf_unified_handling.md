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
1. Backend: one `pdf_identity.resolve()` facade; `_resolve_reference_source`,
   `_default_logical_source_id`, and Zotero resolution reachable only through it.
2. Plugin: one `PdfSource` model + `resolvePdfSource()` + `pdfStatusKey()`; badge
   status map keyed by exactly one canonical key; `as any` Zotero detection gone.
3. `externalPdfView.ts` reduced to render + view-state (registry/persistence
   extracted), target < ~1200 LOC.
4. Audit items 3 (repro-or-close), 4 (fixed), 5 (clarified) resolved with tests.
5. Measured **net LOC decrease** across PDF modules, zero test regressions, all
   three flows verified in the testbed.

## 2. Explicit Non-Goals

- NOT refactoring `crossReferenceResolver.ts` or `pdfCapture.ts` internals
  (boundary-adapt only).
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
- `PdfIdentity` (backend) / `PdfSource` (plugin): all fields optional + an
  explicit `resolution_status` enum (`resolved | path_unresolved | untracked`),
  mirroring `locator_status`.
- "Single entry point, not single implementation": plugin keeps a local Zotero
  fallback used only when the backend command is unavailable.
- `external_uri` is authoritative for opening whenever present (already specified
  in SYSTEM_BEHAVIOR §29.2 this session); all consumers must honor it.
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
  `PdfIdentity` / `PdfSource` + `resolution_status` in `docs/specs/` (+ EN/KR
  guides). Audit & list every relpath-first consumer (items 1/2 follow-up).
- **P2 — Backend resolver facade.** Add `pdf_identity.resolve()` wrapping existing
  functions; route `import_source` + `_locator_from_span` through it. No dedup SQL
  change. Verify: `pytest`/`ruff`/`mypy` + dedup parity gate.
- **P3 — Plugin resolver + state machine.** Add `pdfSource.ts`; route badge/source
  call sites; single `pdfStatusKey`; remove `as any` Zotero detection (item 4);
  resolve/close item 3; clarify `isAddedState` states (item 5). Verify: `vitest`
  + `tsc`.
- **P4 — Delete dead resolvers + slim renderer.** Remove now-unused private
  resolvers; extract `externalPdfRegistry.ts` (registry/persistence) from
  `externalPdfView.ts`, one move per commit. Verify: net-LOC gate + all tests.
- **P5 — Testbed E2E + docs sync.** Run reference/add-source/agent-PDF scenarios
  in the testbed; confirm behavior parity; finalize EN/KR docs; version bump +
  changelog per Universal Strict Workflow.
