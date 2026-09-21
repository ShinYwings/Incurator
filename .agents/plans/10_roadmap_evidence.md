# v0.82.9 Evidence Ledger

Rollback anchor: f184c99d (v0.82.8, PR209 merged). Schema14 unchanged.
Branch hotfix/v0.82.9-vault-read; runtime root and production DB untouched.
Existing user timeout report preserved verbatim under ROADMAP queued report.

P0: nested sandbox-exec under `(deny file-write*)` exits71, exact
`sandbox_apply: Operation not permitted`. Single layer reads successfully.
Installed Codex0.155.1. Diagnostic sandbox does not prove exec write behavior.
Actual installed plugin0.82.8, provider openai; no original failing trace captured.

Validation results follow below.
