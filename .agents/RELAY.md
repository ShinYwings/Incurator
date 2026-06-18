# Cross-Agent Relay State

## Goal
Plan G — PDF handling unification and simplification on
`feature/pdf-unified-handling`.

## Plan Reference
- Active plan: `.agents/plans/G_pdf_unified_handling.md`
- Evidence ledger: `.agents/plans/G_pdf_roadmap_evidence.md`
- Current phase: P4/P4b complete and net-LOC gate closed. Next phase is P5
  testbed E2E/docs finalization/version bump.

## Analysis & Reasoning
- User explicitly asked to re-check macOS/Linux device sync before continuing.
  Audit found the original Plan G resolver/cache design was mostly device-safe:
  plugin `data.json`, backend `state.sqlite`, runtime state, and Obsidian
  workspace state are ignored by the active vault `.stignore`; Zotero paths are
  device-local and resolved from each machine's local `~/Zotero` database and
  ZotMoov roots.
- Gap found and fixed: `.curator/sessions.json` is sync-supported and can store
  `ChatMessage.contextRefs`. Those refs could carry absolute external PDF paths
  and `backendStatus.*Path` from macOS or Linux. P4 now sanitizes synced session
  data: absolute `ContextRef.filePath` values are stripped, volatile
  `backendStatus` is removed, and portable identity (`zoteroAttachmentKey`,
  `fileHash`, vault-relative path, page) is preserved for local re-resolution.
- P4 registry extraction is done: `externalPdfView.ts` no longer owns
  persistence/register/Zotero local traversal helpers. New boundary:
  `plugin/src/ui/externalPdfRegistry.ts`.
- Stale persisted path handling is done: Zotero URL open reuses existing external
  PDF leaves by `zoteroAttachmentKey` as well as path and updates the persisted
  doc path when the backend resolves the same attachment to a new physical path.
- P4b capture extraction is done: `getActivePdfContext` delegates to
  `PdfCaptureService`, which is unit-testable without an Obsidian `ItemView`.
- P4 net-LOC gate is now green after deleting unused text-extraction promise
  code, collapsing toolbar button duplication, and compacting registry glue.

## Progress Status
- Latest commits:
  - `01a13d5` — `feat(plan-g): P4 registry extraction and session path sync guard`
  - `e05db49` — `feat(plan-g): extract PdfCaptureService from external PDF view`
  - `HEAD` — `refactor(plan-g): close P4 PDF module LOC gate`
- Docs/specs updated for device-safe session sync:
  `PLUGIN_SCHEMA.md`, `PLUGIN_GUIDE.md`, `PLUGIN_GUIDE_KR.md`,
  `SYNC_IGNORE_GUIDE.md`, `SYNC_IGNORE_GUIDE_KR.md`, Plan G, and evidence ledger.
- Tests added/updated:
  - `plugin/src/utils/sessionData.test.ts` for synced-session path sanitization.
  - `plugin/src/ui/externalPdfPersistence.test.ts` for registry persistence,
    stale path replacement, and Zotero attachment-key reuse.
  - `plugin/src/ui/pdfCaptureService.test.ts` for capture service behavior.

## Validation
- `npx tsc --noEmit` from `plugin/` -> passed.
- Full plugin suite: `npx vitest run -c ./vitest.config.ts` ->
  `48` files / `413` tests passed.
- `git diff --check` -> passed.
- PDF module LOC: P0 baseline 4601, current 4598.

## Critical Context / Blockers
- Testbed E2E is still pending for P5. Active scenario remains unconfirmed.
- Popover review findings remain queued after Plan G in ROADMAP item 4.1; do not
  mix them into this branch unless explicitly reprioritized.

## Immediate Next Action
Proceed to P5:
1. Confirm or select the active `tests/scenarios/` testbed scenario.
2. Run reference/add-source/agent-PDF E2E smoke validation in `testbed/`.
3. Finalize changelog/version bump and release commit after validation.
