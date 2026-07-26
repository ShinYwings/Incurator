# v0.36.7 Evidence Ledger

Date: 2026-07-26

## Rollback Anchor And Worktree

- Base branch/commit: `master` at `45cd97f`.
- Work branch: `hotfix/v0.36.7-agy-open-tab-context`.
- Initial worktree was clean.
- No DB, vault note, external PDF, or user security-setting writes were made by
  repository changes during planning.

## Live Runtime Evidence

- Obsidian main process start: 2026-07-20 09:49 KST.
- Active renderer start: 2026-07-21 00:17 KST.
- Installed `main.js`/`manifest.json` mtime: 2026-07-23 12:40 KST.
- Installed plugin manifest: v0.36.6.
- Installed `main.js` SHA-256 equals the repository build:
  `d730649016cb5769331a5b0e47c2c3964a11fa4cefff0029c807e1049f004a97`.
- Live chat history contains the reported `jetski` headless `read_file` denial.
- Plugin `data.json` was updated after the failed turn, but
  `~/.gemini/antigravity-cli/settings.json` still had no `permissions` object.
  Therefore the live query path did not execute the v0.36.4 pre-spawn sync.

## Permission Helper Evidence

- Source helper: `plugin/src/agent/llm/LLMClient.ts:52-125`.
- Invocation wiring: `LLMClient.ts:1889-1907`, `2222-2250`.
- Targeted baseline:
  `src/agent/llmClient.test.ts` plus `src/ui/chatSidebarSource.test.ts` =
  98/98 passing.
- `agy` updated locally from 1.1.5 to 1.1.7 during read-only diagnosis without
  changing the Antigravity settings-file hash.
- On 1.1.7, direct reads from an untrusted cache cwd through an external
  `--add-dir`, including a PDF, succeeded even though `permissions` was absent.
  This does not invalidate compatibility support for older 1.1.x releases, but
  it rejects the hypothesis that the observed settings loss was caused by the
  updater rewriting the file during the measured invocation.

## Tab/Chip Evidence

- Persisted workspace content leaves:
  - one `ai-agent-external-pdf`;
  - three Markdown leaves.
- Observed live chip row at the failed turn:
  - active external PDF page;
  - one Markdown file.
- `plugin/main.ts:1818-1824` removes zero-size hidden tab-group leaves.
- `ChatSidebarView.ts:1954-2029`, `4175-4232`, and `4307-4345` reuse the narrowed
  list for prompt refs, chips, and the add-context menu.
- Prompt expansion risk is real: open-tab content is consumed by system prompt,
  user refs, outlines, and edit-target blocks.

## Testbed

- Active scenario identified from the existing testbed fixtures:
  `tests/scenarios/complex_math_backprop`.
- Workspace: `testbed/01_Workspaces/ResNet_Dynamics_Lab`.
- No testbed configuration path was changed during planning.

## Pre-Implementation Result

- Root causes isolated.
- No application code written.
- Plan requires user approval before P1/P2.

## Post-Implementation Result

- User approved the plan on 2026-07-26.
- The running bundle is fingerprinted at plugin load. Every provider call now
  compares that fingerprint/version with the active vault's installed bundle
  before authentication or CLI startup.
- Plugin updates preflight and copy `main.js`, `manifest.json`, and `styles.css`
  as a complete set; the update UI then requires an actual Obsidian renderer
  reload.
- `iterateAllLeaves()` remains the materialized-content source. The public
  `workspace.getLayout()` supplements it with identity-only entries for
  deferred inactive tabs in pop-out tab groups.
- Exact `(view type, portable source identity, page)` keys deduplicate only true
  duplicates. Visible/materialized tabs default eye-on; deferred hidden tabs
  default eye-off and cannot contribute placeholder content to prompts.
- Live Obsidian validation after deployment showed all four expected chips:
  the external PDF page and active Markdown tab eye-on, and the two inactive
  pop-out Markdown tabs eye-off.
- Two live Antigravity PDF-context questions completed normally without
  `jetski`, `read_file`, or auto-denial errors.
- A 50 ms poll during the second live request observed `$read_file$()` in
  `~/.gemini/antigravity-cli/settings.json` immediately before launch.
  Antigravity 1.1.7 subsequently normalized the file and removed that field;
  this is post-launch CLI behavior, not a missing pre-spawn sync.
- Repository and deployed `main.js` SHA-256 matched:
  `0f5b580498feb979ad2e30f5dec5bc18cae1da11a7f7c482c2a06bfa182746bf`.

## Validation Ledger

- Targeted hotfix tests: 45/45 passed after the deferred-layout fix.
- Full plugin suite: 68 files, 721 tests passed.
- `npx tsc --noEmit`: passed.
- Plugin production build: passed.
- Backend suite: 1270 passed, 6 skipped, 5 xfailed.
- Ruff: passed.
- Mypy: passed for 125 source files.
- Version/spec synchronization: 10 passed.
- `complex_math_backprop` testbed status and lint ran without changing its
  configuration; lint scored 100/100. Status retained the pre-existing testbed
  schema-v0/backend-schema-v1 warning, which is unrelated to this plugin-only
  hotfix.
