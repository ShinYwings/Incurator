# RELAY — v0.41.1 hotfix ready for PR (arena paused)

## Goal

Ship v0.41.1: restored (deferred) PDF tabs crashed the shared context path and
took down the purple context pins, sidechat Send, and the Quick Query popover
together. Branch: `hotfix/v0.41.1-deferred-view-crash`.

## Plan Reference

- No Arena plan — HOTFIX EXCEPTION (CLAUDE.md). Report + evidence live in
  `.agents/USER_REPORT.md` (2026-08-04 HOTFIX entry).

## Analysis And Reasoning

Root cause (from user-supplied console errors, after two of my earlier
hypotheses were refuted):

1. **`TypeError: getRuntimePath is not a function` — one cause, three symptoms.**
   Obsidian 1.7.2+ restores tabs as *deferred* views: `leaf.view` answers the
   real `getViewType()` while carrying none of the concrete class's methods.
   `main.ts` narrowed external-PDF leaves on that string alone (6 sites) and
   called `getRuntimePath()`. The throw landed in `getLeafFile()`, which feeds
   BOTH `updateActiveContext()` (→ `refreshActiveContext`, used by sidechat
   `handleSend` and the popover) AND the open-tab inventory (→ purple pins).
   Restarting Obsidian *increased* reproduction because a restart is what
   creates deferred tabs — which is why my "reload Obsidian" advice was exactly
   backwards.
2. **PDF.js canvas collision.** Page canvases are reused across zoom/scroll/
   document swap while `page.render()` was fire-and-forget, so a re-render
   could start while the previous task still owned the canvas.

Refuted along the way (kept so nobody re-runs them): stale-runtime bundle gate
(user had already restarted; installed bundle hash was byte-identical to a fresh
build) and the `wiki` 0.4.3 finding (real and independently filed, but the
backend answered correctly and the update banner never blocks the composer).

## Progress Status

Implementation COMPLETE, gates green:

- New capability guard `plugin/src/ui/pdf/externalPdfLeaf.ts`
  (`asLoadedExternalPdfView`) + obsidian-free `externalPdfViewType.ts`; all 6
  unsafe casts in `plugin/main.ts` routed through it.
- Per-page PDF render tasks tracked/cancelled/awaited in `ExternalPdfView.ts`,
  with cancel-all on document swap, reload, and close.
- TDD: `deferredViewGuard.test.ts` (RED first) + `pdfCanvasRenderRace.test.ts`;
  updated the existing `externalPdfViewSource.test.ts` onClose contract.
- Plugin Vitest 851/851 across 77 files, `tsc --noEmit` clean, production build
  clean. Backend Ruff clean, mypy clean (127 files). Version bumped to 0.41.1
  across all four manifests; spec-sync 10/10 (patch bump → spec titles untouched).
- Docs: PLUGIN_SCHEMA §1.4.1 + §1.4.2; PLUGIN_GUIDE.md and PLUGIN_GUIDE_KR.md
  troubleshooting sections.

## Critical Context / Blockers

- Backend `pytest` was still running at handoff — confirm it is green before the
  release commit (no backend code changed; only `pyproject.toml` version).
- NOT yet done: commit, push, PR.
- Independent open item from the same session: `wiki` resolving to a stale
  editable install in Anaconda (reports 0.4.3 while running current code), the
  plugin comparing the metadata `version` instead of `build.backend_version`,
  and the user's request that `setup.sh` provision the `wiki` alias. All three
  are filed in USER_REPORT.md and are NOT in this hotfix.
- Arena diagnosis (`system_defect_audit_arena/`) is still paused; only
  `00_problem.md` exists. Two runs died on provider limits.

## Immediate Next Action

Confirm backend pytest is green, then commit implementation + `chore(release):
v0.41.1`, push `hotfix/v0.41.1-deferred-view-crash`, open the PR, and verify
latest-head CI.
