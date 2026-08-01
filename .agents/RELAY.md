# RELAY — ACTIVE

## Goal

Ship v0.39.2 so latest-user PDF references such as `수식 (10)` resolve the
target page before a headless provider is launched, without granting native
filesystem access to external Zotero/iCloud PDFs, and close two correctness
gaps found during review before PR #103 merges.

## Plan Reference

- Branch: `hotfix/v0.39.2-equation-reference-context`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/103`
- Review hardening plan: `.agents/plans/04_v0392_reference_review_hardening.md`
- Domain analysis: `.agents/plans/A_v0392_reference_review_hardening.md`
- Evidence: `.agents/plans/04_v0392_reference_review_evidence.md`

## Analysis & Reasoning

- The real page-6 PDF extraction omits the equation image but contains an exact
  `Eq. (10)` prose anchor and the surrounding explanation needed to correct the
  answer.
- The root fix recognizes latest-user `수식 (10)` / `Eq. (10)` pointers,
  refreshes a capped next-first adjacent page through the existing read-only
  PDF API, and injects `<resolved_cross_references>` before generic PDF context.
- External Zotero/iCloud paths remain outside provider filesystem roots; no
  command permission, trust flag, or broad `--add-dir` was added.
- Review reproduction proved that scan exhaustion currently returns a loose
  current-page BM25 hit even when no adjacent page has the exact equation label.
- Review inspection also proved that every prompt-included PDF tab can claim a
  latest-user pointer, including background PDFs in Markdown-focused turns.

## Progress Status

- Docs, TDD regression, implementation, and integration source contract are
  complete.
- Focused plugin tests: 71 passed. Full plugin tests: 740 passed. TypeScript and
  production build passed.
- Backend Ruff/MyPy passed; pytest: 1373 passed, 6 skipped, 4 expected xfails.
- Disposable PDF smoke passed without mutating production or active testbed.
- One isolated live Antigravity replay succeeded with no native-tool denial.
- Implementation commit: `b1dc17e`.
- Release commit: `c018a34` (`chore(release): v0.39.2`).
- v0.39.2 manifests, changelog, roadmap cleanup, and plan deletion are complete;
  version/spec consistency passed 10 tests.
- Branch is pushed and draft PR #103 is open against `master`.
- GitHub CI is green at `e02859b`, but code review found two merge-blocking
  correctness gaps. The user approved the review-hardening plan; docs-first
  contracts and TDD implementation are complete. Focused tests pass 63/63;
  full plugin tests pass 744/744; TypeScript, production build, backend pytest
  (1373 passed, 6 skipped, 4 expected xfails), Ruff, and MyPy pass.

## Critical Context / Blockers

- PR #103 must not merge until the two review findings are fixed and validated.
- Do not repeat the live-provider replay; the one permitted call is complete.
- Do not mutate production `second_brain` or an active testbed.
- v0.39.x stability work remains queued behind this hotfix merge.

## Immediate Next Action

1. Implement docs-first and TDD fixes, run full local validation, and push the
   follow-up commits to PR #103.
2. Human reviews and merges draft PR #103.
3. After merge, fast-forward local `master` and reset relay to the documented
   minimal IDLE stub.
4. Resume the v0.39.x stability audit at P6 on a fresh branch from `master`.
