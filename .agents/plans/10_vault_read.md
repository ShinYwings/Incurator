# v0.82.9 Master Implementation Plan

Date: 2026-09-21
Status: APPROVED — independent Arena proposals and cross-critique concluded.

## 1. Objective
Restore native Codex vault reads without permission prompts or nested Seatbelt
initialization failure. Preserve workspace-write and ephemeral read-only behavior.

## 2. Explicit Non-Goals
No DB/schema, retention, global config, original note edits, full-access retry,
Claude/AGY capability reversal, or unrelated timeout changes in this patch.
Provider read parity remains authorized follow-up, not a claimed patch outcome.

## 3. Strict Quality Conditions & Release Gates
Built-command tests; actual plugin-built Codex exec reads unindexed vault and
external reference markers, permits fixture vault write, denies external writes;
read-only denies vault write. Full backend/plugin checks, review, CI, merge.
No original vault data mutation. Documentation English first, Korean second.

## 4. Locked Design Decisions (Arena Consensus)
Native Codex only for every provider label in its switch branch. Native mode
remains workspace-write/ read-only by toolPolicy. Codex add-dir is writable:
use vault-only sandboxWriteRoots, never Zotero. Pin approval_policy=never,
sandbox_workspace_write.writable_roots=[], exclude_slash_tmp=true. Existing
CLI cwd and TMPDIR remain cache-local. Other providers retain OS wrappers.
Domain analysis and alternatives: vault_read_arena/01_launch_proposal.md and
01_access_adversary.md; genuine cross-critique in 02_*.

## 5. Scope Exclusions & Stop Conditions
Stop on evidence that native flags fail to preserve the write boundary; do not
ship a permission expansion. Escalate genuine product forks, not routine fixes.
Existing inherited named-profile behavior needs measured exec qualification.

## 6. Evidence Ledger
See 10_roadmap_evidence.md. Base f184c99d, schema14, v0.82.8. Dirty user report
was preserved verbatim in ROADMAP during triage. Separate lifetime WIP untouched.
Rollback is Git revert of this patch; no data migration needs rollback.

## 7. Execution Phases (Follow TDD and CI at each phase)
- P0 — reproduce nested sandbox EPERM; independent proposals/cross-critique.
- P1 — specify native-only launch in guides/specs; no public schema change.
- P2 — failing command-construction regressions, then minimal implementation.
- P3 — targeted Vitest, backend pytest/ruff, actual exec fixture smoke.
- P4 — all local gates, version/changelog, PR and code-review skill, CI/merge.
- P5 — deploy verified plugin bundle, communicate activation requirement,
  delete completed plans and prune merged branch. Continue authorized parity.
