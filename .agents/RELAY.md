# Cross-Agent Relay State

## Status
Milestone 2 (Diff Viewer Tier A) is published on
`feature/diff-viewer-plugin-overhaul` as PR #36:
https://github.com/ShinYwings/Incurator/pull/36

Branch version: v0.14.1. Release commit remains the branch tip.

## Done This Milestone
- P0 triage of 11 reported Diff Viewer defects: 2 fixed, 2 live, 7 partial.
- Tier A fixes shipped: Accept-All caret restore (#3), toolbar scroll-anchor
  (#11), review-in-flight serialization (#2), case-insensitive full-path
  fallback without basename retargeting (#7), derived pill status
  reviewable/applied/not_found with ambiguity-safe applied detection (#9), and
  "edits proposed not applied" wording (#4).
- Review follow-up applied: deletion proposals with empty/whitespace REPLACE now
  show applied once SEARCH is gone, and applied/not-found pills suppress click
  propagation so they do not re-run doomed SEARCH matches.
- Proposal status remains derived from live file state; no ChatMessage schema
  change.
- Docs synchronized: PLUGIN_SCHEMA §6 plus EN/KR PLUGIN_GUIDE.
- Version and changelog updated for v0.14.1.
- Plan, arena, and draft files deleted from the active workspace; Git history is
  the archive.

## Validation
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 52 files, 456 tests
  passed.
- `npx tsc -p tsconfig.json --noEmit` from `plugin/`: passed.
- `npm run build` from `plugin/`: passed.
- Version consistency checked locally: backend pyproject, plugin package, and
  plugin manifest are all 0.14.1.

## Deferred
Folded into roadmap item 6: unified-view CSS gutter polish (#5),
cross-model output determinism (#8), token-truncation hard guard (#10; existing
`warnIfLargeReplacement` warning remains).

## Immediate Next Action
User reviews/merges PR #36 on GitHub. After merge, next roadmap item is 3
(Persistent Quick Query Popover).
