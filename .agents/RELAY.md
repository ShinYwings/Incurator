# Cross-Agent Relay State

## Goal
Plan G — PDF handling unification and simplification on
`feature/pdf-unified-handling`.

## Plan Reference
- Plan G implementation/evidence artifacts were completed and removed from the
  active workspace during v0.12.0 finalization; historical copies remain in Git.
- Current phase: release metadata pass complete. Remaining work: release commit
  and PR handoff.

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
- P5 testbed confirmed the device-portability contract: a fresh reference PDF
  resolved on the current macOS path without rebind, while older smoke sources
  pointing at missing `/private/tmp/*.pdf` paths downgraded to `state: missing`
  / `requires_rebind: true` instead of treating stale absolute paths as truth.

## Progress Status
- Latest commits:
  - `01a13d5` — `feat(plan-g): P4 registry extraction and session path sync guard`
  - `e05db49` — `feat(plan-g): extract PdfCaptureService from external PDF view`
  - `669176f` — `refactor(plan-g): close P4 PDF module LOC gate`
  - `300c861` — `chore(plan-g): record P5 testbed validation`
- Docs/specs updated for device-safe session sync:
  `PLUGIN_SCHEMA.md`, `PLUGIN_GUIDE.md`, `PLUGIN_GUIDE_KR.md`,
  `SYNC_IGNORE_GUIDE.md`, `SYNC_IGNORE_GUIDE_KR.md`, Plan G, and evidence ledger.
- Tests added/updated:
  - `plugin/src/utils/sessionData.test.ts` for synced-session path sanitization.
  - `plugin/src/ui/externalPdfPersistence.test.ts` for registry persistence,
    stale path replacement, and Zotero attachment-key reuse.
  - `plugin/src/ui/pdfCaptureService.test.ts` for capture service behavior.

## Validation
- `scripts/backend-check pytest` -> `938 passed, 6 skipped, 5 xfailed`.
- `scripts/backend-check ruff` -> passed.
- `scripts/backend-check mypy` -> passed, no issues in 96 files.
- `npx tsc --noEmit` from `plugin/` -> passed.
- Full plugin suite from `plugin/`: `npx vitest run -c ./vitest.config.ts` ->
  `48` files / `413` tests passed.
- `git diff --check` -> passed.
- PDF module LOC: P0 baseline 4601, current 4598.
- Testbed: ResNet Reference Mode import/register generated L1
  `CTX-d617d779`; `wiki plugin pdf context --source-id 3` returned durable L1
  page text; `wiki lint` health `100/100`.
- Release metadata: backend/plugin versions set to `0.12.0`; changelog updated.

## Critical Context / Blockers
- Active scenario was not explicitly confirmed; P5 therefore reused the existing
  Plan G smoke `testbed/` instead of force reinitializing it. This preserved
  useful stale-path evidence for `/private/tmp` reference rows.
- Popover review findings remain queued after Plan G in ROADMAP item 4.1; do not
  mix them into this branch unless explicitly reprioritized.

## Immediate Next Action
Proceed to finalization:
1. Run the final lightweight metadata checks.
2. Commit `chore(release): v0.12.0`.
3. Push/open PR when ready; note Plan F base dependency in the PR.
