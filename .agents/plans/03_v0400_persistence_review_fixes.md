# v0.40.0 Master Implementation Plan

Date: 2026-08-01
Status: APPROVED — user approved the exact review-fix scope; Arena debate concluded; docs-first TDD is pending.

## 1. Objective

Close every actionable persistence finding on draft PR #104 without losing
peer state, corrupt bytes, tombstones, or intended file permissions. Done means
the stale config and peer-arrival reproductions retain all unrelated current
data, interrupted writes preserve canonical bytes and modes, paired docs match
runtime behavior, the required Obsidian version is explicit, and all local and
GitHub gates pass at the new release head.

## 2. Explicit Non-Goals

- No config revision vectors, three-way same-key conflict resolution, or
  deletion-by-omission semantics.
- No portable simultaneous create-if-absent/CAS promise for a missing plugin
  JSON file.
- No database/schema migration or persisted JSON shape change.
- No ownership, ACL, xattr, hard-link, or power-loss directory-fsync contract.
- No production `second_brain` or active testbed mutation.

## 3. Strict Quality Conditions & Release Gates

- A nested peer-only config key inserted after a stale load survives save;
  requested values commit and all machine-local blocks are absent.
- A peer live record or tombstone delivered at the plugin commit boundary is
  included in the committed session/profile result with current deletion and
  recreation semantics intact.
- Corrupt commit-boundary JSON and interrupted process/temp writes preserve
  exact canonical bytes; generic I/O rejection does not misclassify valid data.
- Existing ordinary POSIX mode survives; new ordinary mode matches normal
  umask creation; secret key/store files are `0600` from creation.
- Backend focused tests, full pytest, Ruff, mypy, spec sync, plugin Vitest,
  plugin build, manifest consistency, and GitHub CI are all green.
- All build manifests, static spec titles, changelog, branch, and PR identify
  v0.40.0. `minAppVersion` is 1.1.0 and `versions.json` preserves the v0.39.2
  fallback for Obsidian 1.0.x.

## 4. Locked Design Decisions (Arena Consensus)

- Merge requested vault config into the freshly locked mapping after removing
  `llm`, `search`, and `external`; omission does not delete unrelated keys.
- Existing plugin JSON commits parse and merge the callback bytes inside
  required `DataAdapter.process()`; no legacy race-prone fallback.
- Snapshot queued local state and install only the parsed string returned by
  `process()`. Typed structural failures block; generic failures reject only
  that save.
- Keep the sanitized sibling-temp path only for missing initial creation and
  clean it after both partial write and rename failures.
- Create backend temp siblings with `os.open(O_EXCL)` and the selected safe
  creation mode. Preserve existing `stat.S_IMODE`, use kernel umask for new
  ordinary files, and use explicit `0600` for secrets.
- Raise Obsidian minimum support to 1.1.0. Because this changes a compatibility
  contract, promote the unreleased patch branch to minor v0.40.0.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: first-create CAS, same-key distributed config conflict
  resolution, filesystem metadata beyond mode bits, and unrelated P7–P10 audit
  work remain deferred.
- **Stop Conditions**: stop if `DataAdapter.process()` cannot be proven in the
  declared minimum API, if a required persisted schema change emerges, if
  unrelated user changes overlap target files, or if isolated tests require
  production/testbed state.

## 6. Evidence Ledger

- **Current Repository & Schema Reality**: branch head `268d6c3`; no DB or JSON
  schema change; current session/profile merge functions already encode the
  required tombstones. Official API history adds `DataAdapter.process()` in
  v1.1.0. Existing docs incorrectly promise temp rename for all session writes
  and contain contradictory profile-merge language.
- **Current Dirty Worktree**: only roadmap, relay, and new review planning
  artifacts are modified before implementation; no pre-existing user code edit
  overlaps the scope.
- **Rollback Requirements**: `268d6c3` is the non-destructive rollback anchor.
  No production vault/testbed or external durable state will be changed.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Measured Baseline**: preserve the three isolated
  reproductions and official API/version evidence. Verify: current focused
  tests are green and each new regression fails against the old implementation.
- **P1 — Contract Specification**: update system behavior, plugin schema,
  English guides, then faithful Korean pairs; specify process-based existing
  commits, first-create limitation, config merge policy, mode rules, and
  Obsidian 1.1.0 minimum. Verify: doc/spec sync checks plus focused pytest/Ruff.
- **P2 — Backend TDD and Fix**: add failing stale nested-merge and permission
  tests; implement locked-current config merge and secure mode-aware temp
  replacement. Verify: `scripts/backend-check pytest backend/tests/test_durable_state.py`,
  `scripts/backend-check ruff`, then no phase advance on failure.
- **P3 — Plugin TDD and Fix**: add adversarial process-boundary session/profile
  and partial-temp tests; implement atomic process helpers and integrate both
  callers. Verify: focused Vitest, full Vitest, and plugin build.
- **P4 — Release and Full Validation**: bump every manifest and static spec title
  to v0.40, add `versions.json`, replace the unreleased changelog entry, remove
  implemented plan artifacts, close roadmap/relay state, run full backend
  pytest/Ruff/mypy/spec-sync plus plugin build/Vitest, rename and push branch,
  update PR #104, and wait for green latest-head GitHub CI.
