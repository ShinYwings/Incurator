# v0.82.9 Evidence Ledger

Rollback anchor: f184c99d (v0.82.8, PR209 merged). Schema14 unchanged.
Branch hotfix/v0.82.9-vault-read; runtime root and production DB untouched.
Existing user timeout report preserved verbatim under ROADMAP queued report.

P0: nested sandbox-exec under `(deny file-write*)` exits71, exact
`sandbox_apply: Operation not permitted`. Single layer reads successfully.
Installed Codex0.155.1. Diagnostic sandbox does not prove exec write behavior.
Actual installed plugin0.82.8, provider openai; no original failing trace captured.

Validation results follow below.

## Validation 2026-09-21

TDD: five new launch behavior cases failed with `nested sandbox reached`; after
minimal implementation targeted130 passed. Full plugin1313passed/3skip; TypeScript
passed; backend2045passed/6skip/4xfail/3subtests; Ruff/mypy134files passed. Build
passed, testbed status ok (runtime installed metadata remains0.82.8; no reinstall).
Manifest spec sync post-bump passed. Local root npx resolved Vitest5.0.1; bundled
version validation is recorded separately if rerun.

Actual plugin-built exec0.155.1 in private fixtures: auto read both random markers,
wrote vault file, attempted external-reference and sibling writes denied EPERM.
none read both markers, attempted all3writes denied. A third real exec with private
CODEX_HOME inheriting an extra sibling writable root still denied that write,
proving invocation writable_roots=[] override. All exit0, no approvals/retries,
no sandbox_apply failure. Auth was linked, not copied; production config unchanged.
Evidence logs under ignored .cache/vault-read-live. No original incident trace.

PR210 opened. Actual `/code-review:code-review210` invocation via Claude failed
OAuth expired/could not refresh. Per standing recorded user waiver, independent
five-lens substitute review requested; this is not successful skill execution.

## Final qualification 2026-09-22

Bundled Vitest4.1.11:1313passed/3skip; root npx5.0.1 also passed. Independent
implementation review and five-lens substitute review found no introduced
findings >=80. Both reviewers examined actual native tool result records.
PR210 a44962fb all6remote checks passed. Final change since that reviewed code
is only an explanatory wrapper comment removing an obsolete Codex mention.
Final release cleanup will remove implemented plans after preserving this record
in Git. No backend service reinstall or production data writes are needed.
