# RELAY - ACTIVE

## Goal
Ship v0.36.4 Antigravity headless PDF compatibility hotfix.

## Plan Reference
Implemented plan deleted per release workflow; preserved in Git history.

## Analysis & Reasoning
Antigravity CLI 1.1.3 introduced headless soft-denial, and 1.1.5 made persisted settings authoritative. The plugin now atomically merges `$read_file$()` into the live CLI settings, preserves all user keys, removes only the marked obsolete TOML, and forwards required `--effort` values for Gemini 3.6 Flash base slugs.

## Progress Status
- Implementation committed as `67d8bb9 fix(plugin): restore Antigravity PDF reads`.
- Backend: 1268 passed, 6 skipped, 5 xfailed; ruff and mypy passed.
- Plugin: 699 passed; production build passed.
- Testbed status completed and lint passed 100/100.
- Real `agy -p --model gemini-3.6-flash --effort medium` read the external iCloud Zotero PDF and returned its correct title without permission denial.
- Release commit `902ea80 chore(release): v0.36.4` pushed.
- Draft PR opened: https://github.com/ShinYwings/Incurator/pull/91

## Critical Context / Blockers
- Do not re-introduce `--dangerously-skip-permissions`.
- The user's live Antigravity CLI settings now contain `$read_file$()`; the stale Incurator TOML was removed and is not recoverable except by recreating it from Git history.

## Immediate Next Action
Human reviews and merges draft PR #91.
