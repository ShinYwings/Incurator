# Cross-Agent Relay State

## Status
Planning roadmap item 4, Purge Legacy QMD References, on
`fix/purge-legacy-qmd-references`.

## Plan Reference
`.agents/plans/04_purge_legacy_qmd_references.md`

## Analysis & Reasoning
- Baseline active match count is 202 case-insensitive `qmd` matches across active
  source/tests/plugin/scripts/docs/agent-rule files.
- The cleanup touches runtime/build/API/plugin surfaces, so this is a v0.16.0
  fix release, not a branch-exempt chore.
- Plan decision: remove active qmd runtime/build/status references and migrate
  plugin consumers to `search_*`; preserve useful legacy behavior only by
  generalizing it without qmd naming.

## Immediate Next Action
Wait for approval to implement
`.agents/plans/04_purge_legacy_qmd_references.md`.
