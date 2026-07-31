# RELAY — ACTIVE

## Goal

Ship v0.39.2 so latest-user PDF references such as `수식 (10)` resolve the
target page before a headless provider is launched, without granting native
filesystem access to external Zotero/iCloud PDFs.

## Plan Reference

- Branch: `hotfix/v0.39.2-equation-reference-context`
- Master plan: `.agents/plans/03_v0392_equation_reference_context.md`
- Evidence ledger: `.agents/plans/03_v0392_equation_reference_evidence.md`
- Domain analysis: `.agents/plans/A_v0392_equation_reference_analysis.md`

## Analysis & Reasoning

- The running Obsidian plugin is v0.39.1 and its bundle matches disk.
- The v0.36.4 permission merge works: `$read_file$()` is inserted before
  launch and removed by `agy` 1.1.9 on exit.
- The failing prompt contains page 5 through equation (9), only header-level
  page 6 evidence, and an external PDF path. `agy` receives only the vault via
  `--add-dir`, so its attempt to find equation (10) with native `read_file` is
  correctly denied.
- The root fix is to resolve references in the latest user message, fetch a
  bounded missing page through the existing read-only PDF context API, and
  inject it as `<resolved_cross_references>` before generic PDF context.
- Do not widen `--add-dir`, add command permissions, or use
  `--dangerously-skip-permissions`.

## Progress Status

- Branch created from merged v0.39.1 anchor `bc61fab`.
- Planning commit: `85c8f1a`.
- Diagnosis, plan, and rollback evidence are complete and approved.
- No application code has been written for v0.39.2.
- Provider quota is intentionally preserved until local tests pass.

## Critical Context / Blockers

- No design or approval blocker remains.
- Do not repeat the live-provider diagnosis.
- Do not mutate production `second_brain` or an active testbed.
- v0.39.x stability work remains queued behind this hotfix.

## Immediate Next Action

1. Update the plugin/system specs and English guide, then the Korean guide.
2. Add a failing current-page-(9)/next-page-(10) regression test.
3. Integrate latest-user reference resolution into Sidechat PDF context using
   `getPdfContext(pageNum, radius=0)` for bounded missing-page fetches.
4. Run focused Vitest, full plugin tests, TypeScript, and production build.
5. Only then replay the external PDF once, bump all manifests to v0.39.2,
   update `CHANGELOG.md`, commit, push, and open the hotfix PR.
