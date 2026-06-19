# Cross-Agent Relay State

## Status
Roadmap item 1 (Curator Wikilink Native Resolution) IMPLEMENTED on
`feature/wikilink-architecture-validation` (v0.17.0). Local CI green. PR pending.

## What shipped
Root cause: L1–L4 DAG lives in hidden `.curator/Collections/`; Obsidian never
indexes dot-folders → all `[[LAYER/ID]]` links were dead. Fix (Option A, plugin
owns navigation): one `registerMarkdownPostProcessor` in `plugin/main.ts` calls
`rewriteCuratorLinks` (`plugin/src/utils/curatorWikilinks.ts`) to convert
curator-layer anchors into clickable `openLinkText('.curator/…')` links across
sidechat, quick-query popover, and opened DAG pages; missing targets get
`is-missing`. No backend logic change; native Graph/Backlinks still excluded by
design. Docs: PLUGIN_GUIDE(+KR), PLUGIN_SCHEMA. Version bumped 0.16.1 → 0.17.0
across all three manifests. CHANGELOG updated.

## Validation
- `curatorWikilinks.test.ts` (12) + `curatorWikilinkWiring.test.ts` (3) pass;
  full plugin suite 478/478; tsc clean; production build OK; backend ruff clean.
- Testbed is L1-only (no L2–L4 cross-links to click through); parser verified to
  ignore real `04_Resources/`/`05_Assets/` links. Full DAG click-through needs
  Obsidian runtime — covered by unit tests.

## Immediate Next Action
Push `feature/wikilink-architecture-validation` and open the PR (Universal Strict
Workflow Step 13). Backend pytest not re-run (no backend logic changed; only the
pyproject version string).
