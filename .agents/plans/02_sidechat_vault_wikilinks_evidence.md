# v0.38.0 Sidechat Vault-Page Wikilinks Evidence Ledger

Date: 2026-07-30
Status: IMPLEMENTING — baseline locked; plan approved.

## Rollback anchor

- Branch: `release/v0.38.0`
- Merge-base / clean master:
  `979bfe41c2c738f956e7e994a1f16ed9dc056777`
- Starting release manifests: `0.37.1`
- Starting DB schema: v13; no migration planned

## Current repository reality

| Boundary | Current behavior |
|---|---|
| Hidden Curator links | v0.17.0 rewrite opens `.curator/Collections` pages |
| Ordinary answer links | Left to native `MarkdownRenderer`; special handler ignores them |
| Shared Sidechat prompt | Requests Markdown but has no vault wikilink/non-invention contract |
| Open tabs | Exact vault-relative path is present in system context |
| Pinned context | `ContextRef.filePath` exists but prompt label omits it |
| ContextService | Returns structured locator path/heading/block/status |
| Provider formatter | Omits the ContextService locator |
| Failure Atlas F9 | Backend authored-topology compiler defect; unrelated to answer navigation |

## Measured baseline

- `rg` finds no ordinary-vault wikilink instruction in
  `plugin/src/context/systemPrompt.ts`.
- `formatCuratorContextPack` does not read `item.locator`.
- `contextPromptLabel` emits only `ref.label`.
- `parseAnswerLinkTarget("Auto Calibration")` intentionally returns `null`, so
  ordinary link ownership stays native.
- Existing baseline gates:
  - F9 characterization: `1 passed`.
  - Prompt/link plugin files: `4 files / 31 tests passed`.

## Prior art

- Obsidian's official Vault guide exposes `vault.getMarkdownFiles()` but warns
  that hidden folders are outside the normal Vault API. This supports retaining
  the dedicated hidden-Curator path while avoiding an unbounded visible-note
  inventory in prompts:
  <https://docs.obsidian.md/Plugins/Vault>
- Obsidian's official Bases-view guide opens a known vault path through
  `app.workspace.openLinkText(path, "", modEvent)` and emits a hover-link event.
  The project already uses that pattern for special links; ordinary rendered
  links should remain native so modifier/hover semantics are not reimplemented:
  <https://docs.obsidian.md/plugins/guides/bases-view>
- Obsidian Help documents vault-root paths with optional `.md` omission and
  `#Heading` / `#^Block` navigation:
  <https://help.obsidian.md/Extending+Obsidian/Obsidian+URI>

## Testbed reality

- Materialized `testbed/` is the ResNet Dynamics workspace.
- Checked-in scenarios are `complex_math_backprop` and `testbed_template`.
- Backend F9 remains reproducible and is explicitly out of this UI release.
- Plugin validation will use pure prompt/locator tests plus a real Obsidian smoke
  against existing visible Markdown notes; no production note content is edited.

## Planned regression matrix

| Scenario | Required assertion |
|---|---|
| Shared prompt | Every provider receives exact-path wikilink and non-invention rules |
| Pinned note | Exact `ContextRef.filePath` survives provider prompt construction |
| Valid Markdown locator | Emits `[[path#heading]]`, omitting `.md` |
| Valid block locator | Emits `[[path#^block]]` and prefers explicit block target |
| Valid PDF locator | Stays available as exact path without corrupt `.pdf` |
| Stale/unavailable/external locator | Emits no vault wikilink target |
| Ordinary answer link | Native renderer remains the owner |
| Curator/PDF/edit markers | Existing special behavior remains unchanged |
| Cross-model live smoke | At least one CLI and one local/other provider produce a grounded link |
| Click smoke | Page, heading, and block targets open exactly in Obsidian |

## Post-validation

- TDD red gate:
  `npx vitest run -c ./plugin/vitest.config.ts
  plugin/src/context/systemPrompt.test.ts
  plugin/src/context/chatContextPriority.test.ts
  plugin/src/context/providerContextFormat.test.ts`
  failed as intended: 13 new assertions exposed the missing shared prompt rule,
  omitted `ContextRef.filePath`, absent locator formatter, and omitted
  `vault_link_target`.
- TDD green gate: the same focused command now passes
  `3 files / 39 tests`.
- Full implementation and release validation remain pending.
