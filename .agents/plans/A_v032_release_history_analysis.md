# Domain Analysis A — v0.32.0+ Release-History Regression Audit

Date: 2026-07-30
Scope: PR #80 / v0.32.0 through PR #100 / v0.38.0 and current PR #101 /
v0.39.0.

## 1. Design Constraints From The Repository

- The audit baseline is the merged v0.31.0 parent of PR #80. Current review
  target is `release/v0.39.0` at `b567427`.
- The range contains 19 merged release/chore PRs, 167 non-merge commits, and
  216 changed paths in the aggregate diff. Large facade moves in v0.34.0 and
  v0.36.0 make raw line-count review misleading.
- Completed release plans were deleted from the active workspace by design.
  Their intended contracts must be read with `git show`, then compared with the
  merge diff and current implementation.
- The consumed D2 holdout must not be rerun. Any tracked-file changes must
  update only the permitted drift evidence and hashes.
- Production `second_brain` and the active ResNet testbed are read-only. Fault
  injection uses temporary SQLite databases and disposable vault copies.

## 2. Release Inventory And Primary Risk

| Range | Original focus | Primary regression lens |
| --- | --- | --- |
| v0.32.0 / PR #80 | remove portable-path compatibility | current-only path resolution, destructive normalization assumptions |
| v0.32.1 / PR #82 | schema-v12 identity, storage boundary, session serialization | replica identity, source remap, corrupt shared state, concurrent saves |
| v0.32.2 / PR #83 | legacy peer autosync parsing | malformed/partial files, false success |
| v0.33.0 / PR #84 | strict schema, incremental embedding reuse | migration boundary, stale/partial vector reuse |
| v0.34.0 / PR #85 | CLI/MCP/plugin API decomposition | facade parity, duplicated state, exception boundaries |
| v0.34.1 / PR #86 | autosync loop prevention | high-water state, self-snapshot races, quiescence |
| v0.35.0 / PR #87 | model/effort catalogue | provider parity, unsupported flags, per-call overrides |
| v0.36.0 / PR #88 | plugin god-file decomposition | lifecycle ownership, cancellation, persistence, facade drift |
| v0.36.1 / PR #89 | silent exception hardening | fail-open fallback, false success, missing diagnostics |
| v0.36.2 / PR #90 | fail-closed sync/KRS | corrupt state preservation, transaction closure |
| v0.36.4–v0.36.8 / PRs #91–#96 | PDF/Zotero/provider hotfixes | prompt transport, temp cleanup, model/effort dispatch, timeout |
| dependency PR #97 | npm audit | lockfile-only parity |
| v0.37.0 / PR #98 | schema-v13 composite tombstones | portable keys, LWW, delete/reinsert convergence |
| v0.37.1 / PR #99 | query provider failure UX | trace finalization, fallback attribution, malformed wire output |
| v0.38.0 / PR #100 | grounded Sidechat wikilinks | exact locator preservation, non-invention, native navigation |
| v0.39.0 / PR #101 | authored topology | parser boundaries, generation ownership, sync clocks, serving freshness |

## 3. Alternatives And Trade-Offs

### Alternative A — Re-read only current large files

Fast, but loses the intent and stop conditions that motivated each change.
Facade moves also make new files appear unrelated to the old behavior.

### Alternative B — Re-run every historical release test suite at its commit

Provides historical reproducibility but spends most time rebuilding obsolete
environments and still misses absent failure tests.

### Alternative C — Contract/diff/current-state triangulation

For each release, read the historical master plan and evidence, inspect only
its first-parent merge diff, map changed behavior to current specs/tests, then
exercise the same fault matrix on current code. This preserves historical
intent while reviewing the code users actually run.

## 4. Final Decision

Use Alternative C. Audit in integrity-boundary order for context coherence, but
record results against every release row:

1. identity/storage/sync: v0.32.0–v0.34.1 and v0.37.0;
2. model/provider/plugin lifecycle: v0.35.0–v0.36.8;
3. query/link/topology: v0.37.1–v0.39.0.

A release closes only after two consecutive passes find no new P0/P1 finding
and every changed behavior has one of: passing failure oracle, explicit
contract proof, or a queued finding with owner and patch release.

## 5. Audit Pseudocode

```text
for release in release_matrix:
    plan = git_show(release.plan_commit, release.plan_path)
    diff = git_diff(release.merge_parent, release.merge_commit)
    contracts = map_changed_symbols_to_specs_and_guides(diff)
    tests = map_changed_symbols_to_tests(diff)

    for transition in [
        delete, rename, corrupt_input, partial_success, post_commit_failure,
        concurrent_request, cancellation, timeout, clock_skew, stale_replay,
        empty_provider_output, short_provider_output
    ]:
        inspect_and_fault_inject(release, transition)

    record(finding_or_proof, exact_path, test_gap, release_owner)
    repeat_until_two_dry_passes()
```

