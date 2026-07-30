# RELAY — Plugin npm audit PostCSS Chore

## Goal

Make `npm audit` pass in `plugin/` by updating the vulnerable transitive PostCSS
lockfile resolution without adding a direct dependency or unrelated upgrades.

## Plan Reference

- Branch: `chore/npm-audit-postcss`
- Small isolated dependency-only chore; heavy Arena planning is not required.

## Analysis & Reasoning

- `npm audit` reports `postcss@8.5.15` under Vitest → Vite.
- Advisory `GHSA-r28c-9q8g-f849` affects PostCSS through 8.5.17.
- Vite declares `postcss@^8.5.15`, so a patched transitive resolution can satisfy
  the existing dependency graph without changing `package.json`.

## Progress Status

- [x] Reproduce the audit failure.
- [x] Identify the dependency chain and patched range.
- [ ] Apply a targeted lockfile update.
- [ ] Run audit, plugin tests, and production build.
- [ ] Push a dependency-only PR.

## Critical Context / Blockers

- No blocker.
- Rollback anchor: `ae61d65`.
- Worktree was clean before the report capture.

## Immediate Next Action

Update only the PostCSS lockfile resolution and inspect the exact diff.
