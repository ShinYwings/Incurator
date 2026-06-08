## Why
<!-- What problem or user report item does this solve? Link to user_report.md item or describe the bug. -->

## What
<!-- High-level summary of what changed. -->

## How
<!-- Key implementation decisions, architecture changes, or tradeoffs worth noting. -->

## Checklist
- [ ] Tests pass: `uv run backend/pytest`
- [ ] Ruff clean: `ruff check backend/src/`
- [ ] Plugin tests pass: `npx vitest run -c ./plugin/vitest.config.ts`
- [ ] Docs updated (English guides first, then `_KR.md` counterparts)
- [ ] `CHANGELOG.md` updated
- [ ] Version bumped in `pyproject.toml` / `package.json` / `manifest.json` (if release)
- [ ] `.agents/relay.md` updated or reset to IDLE stub
- [ ] `user_report.md` items cleaned up
