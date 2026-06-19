# Cross-Agent Relay State

## Status
Roadmap item 4 is implemented and validated on
`fix/purge-legacy-qmd-references` as v0.16.0. Draft PR #38 is open:
https://github.com/ShinYwings/Incurator/pull/38

## Plan Reference
Implemented plan artifacts were deleted after ship cleanup. Use Git history for
`.agents/plans/04_purge_legacy_qmd_references.md`.

## Analysis & Reasoning
- Active runtime/build/API/plugin surfaces were migrated to DB-native
  `search_*` status naming.
- The retired external search-binary installer/build path and obsolete search
  parity benchmark artifacts were removed.
- Guard coverage now scans active source, plugin, scripts/build, guides, specs,
  and agent-rule files for the retired dependency name.
- Version is synchronized at 0.16.0 across backend, plugin package/lockfile, and
  manifest; CHANGELOG documents the release.

## Validation
- `scripts/backend-check pytest` -> 961 passed, 6 skipped, 5 xfailed.
- `scripts/backend-check ruff` -> passed.
- `scripts/backend-check mypy` -> passed.
- `npx vitest run -c ./vitest.config.ts` -> 463 passed.
- `npx tsc -p tsconfig.json --noEmit` -> passed.
- `npm run build` -> passed.
- `VAULT_ROOT=testbed .venv-dev/bin/wiki status` -> native-0.16.0.
- `VAULT_ROOT=testbed .venv-dev/bin/wiki reindex` -> 409 documents/chunks.
- `VAULT_ROOT=testbed .venv-dev/bin/wiki lint` -> clean.
- `VAULT_ROOT=testbed .venv-dev/bin/wiki plugin zotero resolve-pdf --attachment-key TESTKEY1 --custom-paths tests/scenarios/testbed_template/mock_zotero_env` -> mock PDF resolved.

## Immediate Next Action
Monitor PR #38 CI/review. Next roadmap implementation item is item 5,
`[[wikilink]]` Architecture Validation.
