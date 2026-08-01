# RELAY — ACTIVE

## Goal

Close all three actionable review findings on draft PR #104: merge project
configuration from the freshly locked mapping, preserve peer arrivals in
synced plugin JSON at the atomic commit boundary, and preserve normal config
permissions while keeping secret files private from creation onward.

## Plan Reference

- Branch: `release/v0.39.3` (will be renamed to `release/v0.40.0` before release)
- Review-fix plan: `.agents/plans/03_v0400_persistence_review_fixes.md`
- Review-fix evidence: `.agents/plans/03_v0400_persistence_review_evidence.md`
- Parent audit plan: `.agents/plans/02_v032_regression_audit.md` (P7 remains next)
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/104`

## Analysis & Reasoning

- The original project-config callback discarded the mapping read under the
  lock, so an unrelated peer key could be lost despite serialization.
- The plugin's promise queue serialized only this JavaScript process; it did
  not protect a canonical file replaced by a sync peer between read and rename.
- `mkstemp()` forced replacement files to `0600`, unintentionally tightening
  ordinary config files instead of preserving their mode or normal umask.
- Obsidian's `DataAdapter.process()` entered the official API in 1.1.0. Using
  it closes the existing-file commit race, but raises the declared minimum from
  1.0.0 to 1.1.0. Under the repository's 0.x SemVer rule this contract change
  promotes the unreleased patch to minor v0.40.0; `versions.json` must retain
  v0.39.2 as the compatible fallback for Obsidian 1.0.x.

## Progress Status

- Captured and triaged all three review findings into the active roadmap.
- Completed the required Arena proposal, independent domain validation, and
  red-team critique; the master plan and evidence ledger are being finalized.
- No application code has changed during planning.
- Prior PR-head gates at `268d6c3` were green: backend 1,382 passed / 6 skipped /
  4 xfailed, Ruff and mypy clean, plugin build clean, Vitest 749 passed.

## Critical Context / Blockers

- Existing session/profile files must merge the exact bytes supplied to the
  synchronous `DataAdapter.process()` callback. No racy fallback is allowed.
- The portable adapter has no create-if-absent/CAS contract; first simultaneous
  creation remains an explicitly documented limitation, not a falsely claimed
  guarantee.
- Generic process/write failures must reject the save without permanently
  classifying valid canonical bytes as corrupt.
- Explicit secret temps must be `0600` from byte zero. Existing ordinary files
  preserve POSIX mode; new ordinary files receive kernel umask semantics.
- Do not mutate production `second_brain` or an active testbed.

## Immediate Next Action

1. Finalize the Arena consensus, domain analyses, master plan, and evidence.
2. Update authoritative docs, then add failing regression tests.
3. Implement, run focused and full gates, rename/push the release branch, update
   PR #104, and wait for the latest GitHub CI result.
