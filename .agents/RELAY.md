# RELAY — ACTIVE

## Goal

Ship v0.40.0 as the reviewed durable-state release: preserve freshly locked
project-config state, merge synced plugin JSON at the atomic commit boundary,
and preserve intended config/secret permissions.

## Plan Reference

- Branch: `release/v0.40.0`
- Parent audit plan: `.agents/plans/02_v032_regression_audit.md` (P7 remains next)
- Review plan/domain analyses were implemented and deleted; history begins at
  `b08ec84`.
- Closed predecessor draft: `https://github.com/ShinYwings/Incurator/pull/104`
- Successor v0.40.0 draft: pending publication.

## Analysis & Reasoning

- Project config now recursively merges requested vault values into the mapping
  read under the lock, while stripping machine-local blocks.
- Existing session/profile JSON now parses and merges the text supplied inside
  `DataAdapter.process()`; no race-prone compatibility fallback exists.
- Obsidian 1.1.0 introduced that official API. Raising `minAppVersion` is a
  compatibility contract change, so the unreleased patch became minor v0.40.0;
  `versions.json` retains v0.39.2 for Obsidian 1.0.x.
- Backend temp siblings use exclusive creation with a safe initial mode:
  existing ordinary mode is restored, new ordinary files use kernel umask, and
  secrets are private from creation onward.

## Progress Status

- Captured, planned, documented, tested, and implemented all three review
  findings; removed the completed follow-up from the roadmap.
- Focused green proofs: backend durable-state 12/12; plugin session/profile
  32/32.
- Full local gates: backend 1,386 passed / 6 skipped / 4 xfailed; Ruff clean;
  mypy clean; spec/version sync 10/10; plugin 757/757; plugin build clean.
- Build manifests, all static spec titles, changelog, plugin minimum support,
  and compatibility fallback agree on v0.40.0.
- Production `second_brain` and active testbed state were not touched.

## Critical Context / Blockers

- The portable Obsidian adapter has no simultaneous create-if-absent/CAS
  contract. Existing files are protected at commit time; first simultaneous
  creation remains an explicit documented limitation.
- GitHub closed PR #104 when its remote head branch was renamed. The correctly
  named v0.40.0 branch requires a successor draft PR; no code/review data was
  lost.
- No implementation blocker remains. Latest-head GitHub CI is still pending.

## Immediate Next Action

1. Create `chore(release): v0.40.0`, push `release/v0.40.0`, and open the
   successor draft PR against `master`.
2. Wait for latest-head GitHub CI and record the result here.
3. Human reviews and merges the successor PR; then reset relay through the
   documented IDLE cleanup procedure.
