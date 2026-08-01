# v0.39.2 Review Hardening Evidence Ledger

Date: 2026-08-01
Status: IMPLEMENTATION APPROVED

## Rollback Anchor

- Branch: `hotfix/v0.39.2-equation-reference-context`
- Head before review planning: `e02859b`
- Draft PR: #103
- Rollback method: additive `git revert` of follow-up commits; never rewrite the
  shared branch.

## Current Contract and Schema Reality

- The affected path is plugin-only prompt-context assembly.
- No SQLite tables, persisted session shapes, provider permissions, or public
  API contracts change.
- Existing contract: latest-user automatic resolution is PDF-focused, exact
  equation evidence is preferred, and unresolved pointers fail closed.

## Pre-Implementation Evidence

- GitHub CI at `e02859b`: backend tests, plugin tests, and version consistency
  are green.
- Full validation reported on the branch: plugin 740 passed; backend 1373
  passed, 6 skipped, 4 expected xfails; Ruff, MyPy, TypeScript, and build passed.
- False-positive diagnostic:
  - current page 5 contains generic `equation system` and number `10` prose;
  - pages 6, 4, 7, and 3 contain no exact equation 10 label;
  - actual fetch order was `[6, 4, 7, 3]`;
  - actual result was `bm25-object`, page 5, confidence `0.85`, and a serialized
    resolved-reference block instead of unresolved.
- Positive control: the real external PDF page-6 fixture resolved page 6 using
  `caption-index` and fetched only page 6.
- Focus inspection: `ChatSidebarView.ts` invokes the latest-user resolver for
  every prompt-included PDF tab without an active/explicit-document gate.

## Post-Implementation Evidence (Pending)

- Focused fail-first tests: 5 expected failures reproduced across the exact-scan
  regression, the new focus-policy cases, and the integration source contract.
- Focused post-implementation tests: 63 passed across
  `pdfReferenceContext.test.ts`, `providerContextPolicy.test.ts`, and
  `chatSidebarSource.test.ts`.
- Docs/spec synchronization: English/Korean plugin guides, system behavior, and
  plugin schema updated.
- Full local validation:
  - plugin Vitest: 744 passed across 68 files;
  - TypeScript `--noEmit`: passed;
  - production plugin build: passed;
  - backend pytest: 1373 passed, 6 skipped, 4 expected xfails;
  - backend Ruff and MyPy: passed.
- Testbed/live-provider handling: no active testbed or production vault was
  mutated. The affected behavior is plugin-local and covered by deterministic
  runtime/source-contract tests; the previously successful disposable PDF smoke
  remains the external-fixture control. The live provider replay was not
  repeated per the relay constraint.
- Follow-up commits: `186c2da` (contracts/plan) and `c12b6de` (TDD fix).
- PR follow-up push/checks: pending delivery.
