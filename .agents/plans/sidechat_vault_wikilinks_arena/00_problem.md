# Sidechat Vault-Page Wikilinks — Problem Briefing

Date: 2026-07-30

## User outcome

The essential behavior is not backend DAG topology. In an Obsidian Agent
Sidechat answer, a reference to another existing page in the user's vault must
appear as an Obsidian `[[wikilink]]`; clicking it must open that exact page,
heading, or block.

## Measured current state

- v0.17.0 already rewrites hidden Curator DAG links under
  `.curator/Collections/`; this shipped behavior is not the missing feature.
- Sidechat renders final answers through `MarkdownRenderer.render(...)`.
  `attachAssistantAnswerLinkNavigation` handles PDF and explicit block
  locators, while ordinary internal links are intentionally left to Obsidian.
- `buildBaseSystemPrompt` requests Markdown but says nothing about ordinary
  vault-note wikilinks or non-invention.
- Open-tab context carries exact vault-relative paths. Pinned `ContextRef`
  objects also carry `filePath`, but the prompt label currently emits only the
  display label.
- ContextService already returns `locator.relpath`, `heading`, `block_id`, and
  `locator_status`; `formatCuratorContextPack` discards the locator when
  formatting evidence for the Sidechat provider.
- Failure Atlas F9 is a real but different backend defect: authored note links
  are not compiled into graph topology. It is not needed to navigate a link in
  an assistant answer.

## Constraints

- Use only a target known from open/pinned context, a valid ContextService
  locator, or a provider tool result.
- Do not send a whole-vault filename inventory to the provider.
- Do not post-process plain prose into links.
- Do not rewrite native visible-vault links with a second click system unless a
  live Obsidian baseline proves native navigation broken.
- Preserve provider parity and existing Curator/PDF/edit-loop behavior.
- This is a new user-facing Sidechat behavior, so it targets v0.38.0 Minor.

## Success criteria

1. All Sidechat providers receive one shared grounded-wikilink instruction.
2. Exact known note paths survive prompt construction.
3. ContextService evidence exposes valid vault locators as ready-to-copy
   wikilink targets.
4. An answer containing a known page, heading, or block link opens the exact
   target in Obsidian.
5. Unknown/stale/unavailable targets remain plain evidence; the model is told
   not to invent links.
