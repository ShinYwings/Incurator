# Domain Analysis B — Sidechat Link Rendering And Navigation

Date: 2026-07-30

## Design constraints from the codebase

- Final Sidechat answers use `MarkdownRenderer.render(this.app, source, ...,
  "", this)`.
- `attachAssistantAnswerLinkNavigation` is deliberately conservative: PDF page/
  section targets and explicit vault block locators only.
- `rewriteCuratorLinks` handles hidden `.curator/Collections` pages because
  Obsidian cannot index hidden folders.
- Visible vault notes should remain owned by Obsidian's native internal-link
  renderer and workspace navigation.

## Documentation/spec invariants

- Ordinary vault links keep native behavior.
- Hidden Curator links, PDF jumps, and edit-loop markers must not be reclassified
  as ordinary note links.
- Modifier-click, hover, aliases, heading links, and block links must remain
  compatible with Obsidian.

## Alternatives and trade-offs

1. Attach `openLinkText` to every internal anchor: deterministic but duplicates
   MarkdownRenderer and risks double events/modifier loss; rejected by default.
2. Convert wikilinks to custom HTML before render: unnecessary and bypasses
   Obsidian parsing; rejected.
3. Keep native renderer, characterize with real Obsidian smoke: selected.

## Final decision

Do not add a second ordinary-link navigation layer. Unit tests lock formatter
and prompt behavior. A real Obsidian test must prove that a generated page,
heading, and block link opens the intended target. Only if that baseline fails
may implementation add a narrowly scoped handler after documenting the native
failure.

## Implementation pseudocode

```ts
renderAssistantMarkdown(answer)
await native MarkdownRenderer
retain existing PDF/block/Curator special handlers
// no generic link rewrite
```
