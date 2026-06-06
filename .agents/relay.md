# Relay State — fix/v0.3.3-cleanup (2026-06-06, Claude Code)

## Status: Wrapping up

Branch: `fix/v0.3.3-cleanup`  
PR target: `master`

## What was done this session

Fixed 8 structural workflow issues identified during v0.3.3 PR audit:

1. **relay.md bloat** — added IDLE Cleanup rule to AGENTS.md + CLAUDE.md
2. **No CI** — created `.github/workflows/ci.yml` (backend pytest + ruff; plugin tsc + vitest)
3. **master vs main** — documented in AGENTS.md + CLAUDE.md branch naming section (no rename)
4. **Branch naming inconsistency** — added convention table to AGENTS.md + CLAUDE.md
5. **System Invariants stale** — updated EXH→Synthesis, qmd retired in AGENTS.md + CLAUDE.md
6. **schema_guardian "v0.2.0" hardcoded** — removed version in AGENTS.md + CLAUDE.md
7. **No PR template** — created `.github/pull_request_template.md`
8. **No rollback procedure** — documented `git revert -m 1` in AGENTS.md + CLAUDE.md

Also fixed: `backend/pyproject.toml` readme path (root README deleted → points to `docs/README.md`).  
Also added: **Shared Architecture Memory** section to both agent files.  
Also synced: all prior AGENTS.md changes (relay IDLE cleanup, branch naming, Antigravity Fallback bullet) into CLAUDE.md.

Tests: 445 passed (full backend suite).

## Immediate Next Action

Commit all staged changes and push → open PR against `master`.

After PR merges: reset this file to a minimal IDLE stub.
