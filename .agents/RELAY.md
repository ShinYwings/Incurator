# Relay State — ACTIVE (2026-06-11)

## Goal
Agent Edit & Diff Viewer Reliability — **implemented, v0.5.0**, branch
`feature/agent-edit-diff-reliability`.

## Status — AWAITING REVIEW/MERGE
All 5 phases done. Local CI green: vitest 297 pass (40 files), tsc clean,
production esbuild OK, version-consistency 0.5.0 across pyproject/package/
manifest/lock. Backend Python unchanged (only version string) → its ruff/pytest
unaffected; CI re-verifies on the PR. Plan + Arena + draft deleted (Step 11);
ROADMAP/RELAY updated. PR pending push.

## What shipped (edge-hardening, no DiffViewer rewrite)
- `utils/editMatch.findSearchBlock` — unified, ambiguity-safe SEARCH matcher
  (exact → line-trim → anchored; refuses on >1 candidate or >3× span). Wired
  into `applyInlineMultiEdit` + `reviewAssistantEdit` so preview == apply.
- Tolerant edit-block parser + `stripDanglingEditMarkers` (fence-aware,
  render-only; stored content untouched) + stronger `collapseStreamingEditBlocks`.
- Safe-gated `maybeAutoOpenDiff` (active note / no focus only; once per message;
  never on history re-render). Always-visible hunk counter. Scope prompt rule +
  non-blocking large-replacement warning.
- **Removed** the `00_System/Agent Diffs/` artifact feature entirely (writer,
  pill, setting, `editArtifact.ts` + test, `editArtifactPath`). Existing user
  files left on disk.

## User decisions captured (2026-06-11)
Minor v0.5.0 · safe-gated auto-open · artifact removed entirely.

## Immediate Next Action
Push branch + open PR. After merge, next milestone candidate = To-Do #1
(Sidechat Selection & LaTeX Robustness) — needs its own Arena plan + approval.
