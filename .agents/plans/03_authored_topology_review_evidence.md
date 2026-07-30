# v0.39.0 Authored-Topology Deep-Review Evidence Ledger

Date: 2026-07-30
Status: IMPLEMENTED — final latest-head CI pending
Branch: `release/v0.39.0`
Rollback anchor: `d4420eac439e7395b3d6f081686c296094363763`
PR: #101 (draft)

## 1. Repository Reality

- Worktree was clean before review-plan files.
- PR #101 is open, draft, mergeable, with no review threads.
- Head CI run for `d4420ea` passed backend and plugin jobs.
- Build manifests agree on 0.39.0; DB schema remains v13.

## 2. Confirmed Pre-Fix Reproductions

| Case | Current result |
|---|---|
| `[[Tar<!-- -->get]]` | invents `Target.md` relation |
| `#to%%...%%pic` | invents `#topic` |
| `\[[Escaped]]` | emits relation |
| `#123` | emits tag |
| tilde fence closed by longer fence | fenced link leaks |
| unclosed fence | fenced link leaks |
| `[x](Target_(v2).md)` | valid target missed |
| source-relative `../Target.md` | valid target missed |
| duplicate filename + unique same-name alias | ambiguous filename falls through to alias |
| `.markdown` source/target | compile succeeds with zero authored rows |
| DB-only prompt-contract republish | relation remains on discarded generation |
| Markdown→text source transition | old relation remains active |
| replica generation/row clock skew | shared deterministic relation becomes retired |
| pure authored-edge addition | old community report remains served |
| source deletion | retired relation's search document remains |
| link removal | orphan authored entity documents remain searchable |

## 3. Read-Only User-Vault Check

- `/Users/shin/shinywings/second_brain/03_Notes` still contains 17 Markdown
  notes.
- No `.markdown`, escaped wikilink, comment-stitch, longer-tilde, or unclosed
  fence instance was observed.
- The balanced-parenthesis pattern appears in Zotero URI links; those are
  external and must remain rejected.
- One numeric-looking match was a heading fragment inside a wikilink and is
  already removed from tag scanning. Synthetic numeric-only tags still prove
  the parser boundary is wrong.
- Current full extraction over the 17-note directory took about 3.6 seconds.
  Broad inventory caching remains outside this corrective slice.

## 4. Deferred Finding

The pre-existing full `remove_source` closure for extracted knowledge units and
relation supports needs a separate stability plan. This PR will not widen its
F9 review patch into that architecture; the follow-up must be queued explicitly.

## 5. Post-Fix Gates

- Parser/resolver regressions: 25 focused authored-topology tests pass,
  including length-preserving masking, escape/numeric filtering, CommonMark
  fence boundaries, balanced destinations, safe parent resolution, tri-state
  ambiguity, and `.markdown`.
- DB-only republish and non-Markdown transition: unchanged-fingerprint
  membership transfers atomically; changed/unknown membership and type changes
  fail closed and retire prior ownership.
- Adversarial replica convergence: shared edges survive independent
  relation/generation clocks, including a future row clock. Three-way
  reconciliation compares the winner with every loser for report invalidation.
- Report/search freshness: pure local and imported topology additions retire
  endpoint reports; link removal and explicit source deletion remove retired
  relations and orphan authored entities from materialized search.
- Focused/related pytest: 25 authored tests pass; the broader related group
  passed 144 tests with 4 expected failures before the final three-way case was
  added. Ruff and Mypy pass.
- Full backend: 1,351 tests passed, 6 skipped, and 4 expected failures in the
  final latest-worktree run.
- Plugin: 68 files / 737 tests pass; production build passes; `npm audit`
  reports zero vulnerabilities.
- Isolated testbed: a disposable copy of `complex_math_backprop` successfully
  discovered and built a `.markdown` note through authenticated Antigravity.
  The authoritative generation recorded two exact authored relation ids.
  Removing both link and tag published an empty membership, retired both rows,
  and removed their relation/entity search documents. Both lint runs exited 0
  with 99/100, 0 errors, and 0 warnings.
- The active `testbed/` and production vault were not modified. The disposable
  vault and its exact cache were moved to Trash after validation. `wiki init`
  had updated the Gemini MCP vault root; it was restored to
  `/Users/shin/shinywings/second_brain`, matching `.cache/config/last_root`.
- D2 holdout: not rerun because the holdout is consumed. The changed
  `_entities.py` paths are outside Q06, and the drift ledger is re-armed at
  SHA-256 `cb27e8f5cffa6aaf5298209c22cee37b526ef6ecd5f14b2e5be7145d7b05f9f4`.
- Latest-head GitHub CI: pending push.
