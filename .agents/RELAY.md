# Relay State — ACTIVE (2026-06-11)

Branch: `fix/install-version-unification` (from master). Target: `v0.4.4`.

## Active Goal
Completing ROADMAP To-Do #1 (Installation & Version Management Unification).
The user already landed a workaround (commit 1066292: CI `working-directory`,
install-hint strings, deleted `plugin/.env.example`, `plugin/deploy.sh` fallback).
This branch finishes the gaps that commit missed:
- **resolveWikiBinary probe order** (root cause): now prefers repo-root `.venv`
  over the stale `backend/.venv` → fixes the plugin reporting an old backend
  version / broken self-update toast. (`plugin/src/utils/deviceRegistry.ts`)
- **Dashboard model display**: `populateModelSelect` no longer snaps custom
  models to Antigravity Gemini; surfaces the active model as a "(current)"
  option. (`plugin/src/utils/modelSelect.ts` + `incuratorDashboardModal.ts`)
- **Docs path scrub**: absolute link + `second_brain`/`/Users/<you>` examples.

## Status
Code + tests done. Local CI green: vitest 291 pass, tsc clean, ruff clean,
pytest 505 pass. (mypy has 84 PRE-EXISTING backend errors, not from this change;
not a CI gate.) Version bumped 0.4.3 → 0.4.4 across pyproject/package/manifest/
lock + CHANGELOG. Next: commit, push, PR.

## Last Completed Work

## Last Completed Work
- **v0.4.3**: `pointer-events: none` + `user-select: text` on `mjx-container` / svg inside `.ai-agent-chat-msg-content` and `.ai-agent-quick-query-answer`. Fixes Shift+click selection spanning MathJax formulas in chat sidebar and quick query popover.

## Pending
USER_REPORT inbox triaged on 2026-06-11 → 8 To-Do milestones in
`.agents/ROADMAP.md`. Recommended next pickup: **#1 Installation & Version
Management Unification** (partly hotfix-class — broken self-update toast).
USER_REPORT inbox is now empty.
