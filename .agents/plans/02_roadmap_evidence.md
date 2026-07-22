# v0.36.5 Evidence Ledger

Date: 2026-07-22

- Rollback anchor: `master` at creation of
  `hotfix/v0.36.5-zotero-refresh-collision`.
- Dirty worktree before implementation: planning-only changes in
  `.agents/RELAY.md`, `.agents/ROADMAP.md`, and `.agents/plans/`.
- Existing vault note: `03_Notes/Papers/EWA splatting.md`.
- Requested rendered path: `03_Notes/Papers/EWA Splatting.md`.
- Current selected Zotero identity: parent `RBKB7NXE`, attachment `6SFC2FXA`.
- Retired identity absent from current DB: parent `N553UVKA`, attachment
  `2JBAPFWN`.
- Schema impact: none. This is a plugin write-path correction and does not
  change backend storage identity or Zotero data.
- Pre-validation: current exact lookup falls through to `vault.create`, which
  produces the reported already-exists failure on macOS.
- Post-validation: targeted writer tests passed; plugin 704/704 tests and
  production build passed; backend 1268 tests passed with 6 skipped and 5
  expected failures; ruff and mypy passed; version/spec sync 10/10 passed;
  existing testbed status completed and lint scored 100/100.
