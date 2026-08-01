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

- The real page-6 PDF extraction omits the equation image but contains an exact
  `Eq. (10)` prose anchor and the surrounding explanation needed to correct the
  answer.
- The root fix recognizes latest-user `수식 (10)` / `Eq. (10)` pointers,
  refreshes a capped next-first adjacent page through the existing read-only
  PDF API, and injects `<resolved_cross_references>` before generic PDF context.
- External Zotero/iCloud paths remain outside provider filesystem roots; no
  command permission, trust flag, or broad `--add-dir` was added.

## Progress Status

- Docs, TDD regression, implementation, and integration source contract are
  complete.
- Focused plugin tests: 71 passed. Full plugin tests: 740 passed. TypeScript and
  production build passed.
- Backend Ruff/MyPy passed; pytest: 1373 passed, 6 skipped, 4 expected xfails.
- Disposable PDF smoke passed without mutating production or active testbed.
- One isolated live Antigravity replay succeeded with no native-tool denial.

## Critical Context / Blockers

- No blocker remains.
- Do not repeat the live-provider replay; the one permitted call is complete.
- Do not mutate production `second_brain` or an active testbed.
- v0.39.x stability work remains queued behind this hotfix.

## Immediate Next Action

1. Commit the validated implementation and evidence.
2. Bump all manifests to v0.39.2 and update `CHANGELOG.md`.
3. Remove the completed roadmap item and transient v0.39.2 plan artifacts.
4. Run version/spec consistency and final diff checks.
5. Create `chore(release): v0.39.2`, push, and open the hotfix PR.
