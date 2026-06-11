# Relay State — ACTIVE (2026-06-11)

## Goal
Drop the `gh` dependency / local-only Git sidechat — **implemented, v0.5.3**,
branch `fix/drop-gh-dependency`.

## Status — AWAITING REVIEW/MERGE
Done. Local CI green: plugin tsc clean + vitest 302, backend ruff clean +
pytest 507. Versions 0.5.3 consistent. ROADMAP/RELAY updated, draft deleted.
PR pending push.

## What shipped (user decisions: remove auth feature entirely; verify-only history; patch)
Investigation finding: NO core feature needed `gh`. The local Git sidechat
(status/log/file history/commit/push) already used the local `git` binary; only
an OPTIONAL GitHub-account display used `gh`, and `setup.sh` force-installed it.
Removed:
- `setup.sh` gh install block; `auth/githubAuth.ts` (+test); the GitHub
  Sign-in/out settings section; `github_authenticated`/`github_account` fields
  (types.ts, git_manager.py `_github_status`, chatSidebar status line).
- Docs: PLUGIN_GUIDE/USER_GUIDE (EN+KR) + SYSTEM_BEHAVIOR/PLUGIN_SCHEMA specs
  now say "local git only, no gh".
Local history feature was verified working gh-free (unchanged).

## Recurring note
Used `uv run --directory backend` + `UV_PROJECT_ENVIRONMENT=$(git rev-parse
--show-toplevel)/.venv` per the new policy — no backend/.venv created.

## Immediate Next Action
Push branch + open PR. After merge, next milestone = To-Do #1 **RAG & Knowledge
Quality Stabilization** (Major → full Arena plan + approval before coding).
