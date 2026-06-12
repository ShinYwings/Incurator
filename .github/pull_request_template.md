## 📋 References
- **Related User Report:** <!-- Link to the original bug/issue in user_report.md -->
- **Implementation Plan:** <!-- MANDATORY: Link to the approved .agents/plans/[Plan_Name].md -->

## 💡 Why
<!-- What problem does this solve? -->

## 🛠️ What
<!-- High-level summary of what changed. -->

## 🏗️ How
<!-- Key implementation decisions, architecture changes, or tradeoffs worth noting. -->

## 🧐 Antigravity Code Review Feedback Applied
<!-- MANDATORY: If Antigravity provided a code review or plan audit, list the feedback here and explain how you fixed it. If no review was given, write "N/A". -->

## ✅ Checklist
### CI & Local Tests
- [ ] Tests pass: `uv run --directory backend pytest -q`
- [ ] Ruff clean: `uv run --directory backend ruff check src/`
- [ ] Plugin tests pass: `npx vitest run -c ./plugin/vitest.config.ts`

### Testbed Validation (MANDATORY)
- [ ] Validated changes using the active testbed scenario (`VAULT_ROOT=testbed wiki update` or equivalent CLI commands).
- [ ] Ensured NO unverified production changes were pushed.

### Documentation & Agents
- [ ] Docs updated (English guides first, then `_KR.md` counterparts)
- [ ] `CHANGELOG.md` updated and version alignment verified
- [ ] Version bumped identically in `pyproject.toml`, `package.json`, and `manifest.json`
- [ ] `.agents/RELAY.md` updated or reset to IDLE stub
- [ ] `.agents/USER_REPORT.md` items cleaned up
