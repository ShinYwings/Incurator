# Cross-Agent Relay State

## Goal
Plan G — PDF handling unification and simplification on
`feature/pdf-unified-handling`.

## Plan Reference
- Active plan: `.agents/plans/G_pdf_unified_handling.md`
- Evidence ledger: `.agents/plans/G_pdf_roadmap_evidence.md`
- Current phase: P4/P4b complete structurally; additional P4 slimming still
  required before Plan G can close because the net-LOC gate is not yet met.

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

## Progress Status
- Latest commits:
  - `01a13d5` — `feat(plan-g): P4 registry extraction and session path sync guard`
  - `e05db49` — `feat(plan-g): extract PdfCaptureService from external PDF view`
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
- `git diff --check` -> passed before both P4 commits.

## Critical Context / Blockers
- Net-LOC gate is still open. P0 baseline: 4601 PDF-module LOC. After P4/P4b:
  4704 LOC. `externalPdfView.ts` is down to 1889 lines, but new registry/service
  modules add enough lines that total LOC is +103. Plan G cannot close until
  additional deletion/slimming brings the total below 4601.
- Testbed E2E is still pending for P5. Active scenario remains unconfirmed.
- Popover review findings remain queued after Plan G in ROADMAP item 4.1; do not
  mix them into this branch unless explicitly reprioritized.

## Immediate Next Action
Continue P4 slimming:
1. Identify and delete or simplify dead/excess PDF-view logic after registry and
   capture extraction.
2. Re-measure PDF-module LOC and keep iterating until total < 4601.
3. Then run full plugin validation again and proceed to P5 testbed E2E/docs sync.
