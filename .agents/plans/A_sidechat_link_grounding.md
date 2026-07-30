# Domain Analysis A — Sidechat Link Grounding

Date: 2026-07-30

## Design constraints from the codebase

- `buildBaseSystemPrompt` is the provider-independent Sidechat instruction
  source and already owns Markdown, language, math, and edit contracts.
- `buildLLMMessages` sends exact open-tab paths but loses `filePath` from pinned
  context labels.
- `ContextService` already resolves structured locators; adding another path
  lookup in the plugin would duplicate authority.
- `formatCuratorContextPack` currently emits evidence text and ids but not the
  locator included in `CuratorContextItem`.

## Documentation/spec invariants

- Plugin answers render Markdown and must preserve ordinary vault-link behavior.
- Hidden Curator links remain navigation-only and use the v0.17.0 rewrite.
- ContextService locators are clickable only when their status supports it.
- The model must not invent a wikilink target.

## Alternatives and trade-offs

1. Prompt wording only: smallest diff, rejected because exact paths are already
   dropped at two boundaries.
2. Whole-vault path inventory: broad discovery, rejected for token/privacy cost
   and weak relevance.
3. Post-hoc prose auto-linking: model-independent, rejected because it can link
   ambiguous names and hides the real prompt/context defect.
4. Preserve current grounded paths plus one prompt rule: selected.

## Final decision

Expose only current grounded targets. Extend `contextPromptLabel` to preserve
`filePath`, and format usable ContextService locators inside the existing
provider evidence block. Add a single shared Sidechat instruction for exact
wikilink output and non-invention.

## Implementation pseudocode

```ts
contextPromptLabel(ref):
  base = existing priority label
  return ref.filePath ? `${base} (vault path: ${ref.filePath})` : base

formatCuratorContextPack(pack):
  for item:
    render existing evidence
    target = formatVaultLocatorWikilink(item.locator)
    if target: render `vault_link_target: ${target}`
```
