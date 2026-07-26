# RELAY — v0.36.7 Obsidian Agent Hotfix

## Goal

Fix recurrent Antigravity headless `read_file` denial and incomplete open-tab
purple context chips without weakening sandbox or prompt privacy.

## Plan Reference

- `.agents/plans/07_agy_open_tab_context_hotfix.md`
- `.agents/plans/07_roadmap_evidence.md`
- Arena: `.agents/plans/agy_open_tab_context_hotfix_arena/`

## Analysis & Reasoning

- Installed v0.36.6 files are newer than the live Obsidian process. The v0.36.4
  permission helper is correct on disk but did not run in the failed live turn.
- `getOpenTabContexts()` drops hidden `0x0` tab-group leaves. This is an indirect
  trigger for native reads, not the direct permission cause.
- Consensus: block provider launch on disk/runtime bundle mismatch; make update
  perform a real reload; show all open-tab chips while hidden tabs default
  eye-off and remain absent from prompts until explicitly included.

## Progress Status

- Triage and v0.36.7 patch classification complete.
- Hotfix branch created from `master` at `45cd97f`.
- Live/runtime and targeted 98-test baselines complete.
- Arena plan and evidence ledger authored.
- User approved the plan.
- Docs/specs updated in English then Korean.
- TDD regressions added for bundle activation, prompt inclusion, open-tab
  identity/page dedupe, layout refresh, and complete-update reload.
- Implementation complete: provider launch hash/version gate, complete
  three-artifact update + reload action, all-leaf chip enumeration, hidden-tab
  eye-off policy, prompt filtering, and stale PDF-cache removal.
- `npx tsc --noEmit` and all 719 plugin tests pass.

## Critical Context / Blockers

- The currently running Obsidian instance still needs one reload after v0.36.7
  is deployed; the new guard prevents this state from recurring silently.
- Active testbed scenario: `complex_math_backprop`.
- `agy` self-updated from 1.1.5 to 1.1.7 during read-only diagnosis; its settings
  hash did not change.

## Immediate Next Action

Commit the implementation, bump v0.36.7/changelog, run full backend/plugin and
testbed validation, delete the completed hotfix plan, then push and open the PR.
