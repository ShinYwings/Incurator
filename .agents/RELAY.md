# Active Relay State

**STATUS: PR OPEN - Hotfix for large PDF/Markdown L2 extraction failures.**

**Branch**: `hotfix/v0.27.1-l2-extraction-failure`
**PR**: https://github.com/ShinYwings/Incurator/pull/59

---

## Goal

Fix the production failure where large/equation-heavy sources, specifically
`/Users/shin/shinywings/second_brain/03_Notes/Vision/MultipleViewGeometry.md`
and its Zotero PDF reference, take hours in `wiki build` and then fail L2 with
`knowledge unit extraction failed`.

## Plan Reference

- Roadmap: `.agents/ROADMAP.md`
- Repro source note: `03_Notes/Vision/MultipleViewGeometry.md`
- Failing source row in the user's production DB: PDF reference source id `27`
- Branch: `hotfix/v0.27.1-l2-extraction-failure`

## Analysis & Reasoning

- The Markdown note itself had already completed L2/L3 in the user's DB.
- The referenced PDF source was failing:
  `04_Resources/References/Multiple_View_Geometry_in_Computer_Vision-EN.md`,
  `file_type=pdf`, external Zotero PDF path
  `/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/[Project] COLMAP_free_Reconstruction/Multiple_View_Geometry_in_Computer_Vision-EN.pdf`.
- Source id `27` had `l1_status=done`, `l2_status=error`, and layer error
  `knowledge unit extraction failed`.
- Runtime history showed multi-hour jobs where most L2 prompt batches succeeded,
  but a minority failed validation because output did not parse into the declared
  model.
- Before this hotfix, `extract_knowledge_units()` persisted successful batch
  rows immediately, while `compile_source_l2()` only published a compiler
  generation if every batch succeeded. A late failed batch therefore left
  generation-less orphan units and still marked the whole source failed.

## Progress Status

- Implemented recursive failed-batch narrowing for L2 knowledge-unit extraction:
  multi-span batches split by approximate character weight; a single large span
  can split into overlapping same-span retry slices.
- Changed extraction persistence to collect validated units in memory and write
  them only after every batch/retry slice succeeds.
- Added one transaction for final unit + claim-support persistence by extending
  `db.upsert_knowledge_unit(..., conn=...)`.
- Added cleanup of generation-less source-local knowledge units at fresh L2
  extraction start, so retrying the failed PDF discards stale failed-run rows
  before prompting.
- PR review follow-ups added an empty-batch retry-split guard, fail-fast retry
  behavior when the left half of a split already fails, and active-only cleanup
  so retired generation-less rows remain audit history.
- Updated docs/specs/guides, changelog, and version metadata to `v0.27.1`.

## Validation

- `scripts/backend-check pytest backend/tests/test_knowledge_unit_extraction.py`:
  11 passed.
- `scripts/backend-check pytest backend/tests/test_failure_atlas_d2.py::test_d2_holdout_result_is_single_run_frozen_and_fine_grained`:
  passed after re-arming the DB helper hash.
- `scripts/backend-check ruff`: passed.
- `scripts/backend-check mypy`: passed, 97 source files.
- `scripts/backend-check pytest`: 1076 passed, 6 skipped, 5 xfailed, 7 warnings.
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 60 files / 598 tests
  passed.
- `VAULT_ROOT=testbed wiki status`: passed.

## Critical Context / Blockers

- The user's production source files were not edited.
- The production PDF build was not rerun because prior runs took 80 minutes to
  3+ hours; deterministic tests cover the failed-batch and partial-publish paths.
- After this hotfix is installed, retry the failed source with
  `VAULT_ROOT=/Users/shin/shinywings/second_brain wiki source retry 27`.
- A separate quick-win stash exists for G13 CLI PATH parity:
  `wip-v0.27.1-g13-cli-path-parity`. It must be rebased/renumbered after this
  hotfix because this branch uses `v0.27.1`.

## Immediate Next Action

Human review/merge PR #59. After merge, retry the failed production PDF source
with `VAULT_ROOT=/Users/shin/shinywings/second_brain wiki source retry 27`, then
resume System Stability Phase A and adjust the shelved G13 quick-win to
`v0.27.2` or later.
