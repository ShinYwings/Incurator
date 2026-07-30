# RELAY — Plugin npm audit PostCSS Chore

## Goal

Make `npm audit` pass in `plugin/` by updating the vulnerable transitive PostCSS
lockfile resolution without adding a direct dependency or unrelated upgrades.

## Plan Reference

- Branch: `chore/npm-audit-postcss`
- Draft PR: `https://github.com/ShinYwings/Incurator/pull/97`
- Small isolated dependency-only chore; heavy Arena planning is not required.

## Analysis & Reasoning

- `npm audit` reports `postcss@8.5.15` under Vitest → Vite.
- Advisory `GHSA-r28c-9q8g-f849` affects PostCSS through 8.5.17.
- Vite declares `postcss@^8.5.15`, so a patched transitive resolution can satisfy
  the existing dependency graph without changing `package.json`.

## Progress Status

- [x] Reproduce the audit failure.
- [x] Identify the dependency chain and patched range.
- [x] Apply a targeted lockfile update.
- [x] Run audit, plugin tests, and production build.
- [x] Push a dependency-only PR.

## Critical Context / Blockers

- No blocker.
- Rollback anchor: `ae61d65`.
- Worktree was clean before the report capture.
- Clean `npm ci`: succeeded.
- `npm audit --audit-level=high`: zero vulnerabilities.
- Plugin: 721 tests passed; production build passed.

## Immediate Next Action

Confirm PR #97 CI, then hand off for human review and merge.
