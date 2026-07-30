# Sidechat Proposal: Grounded Link Targets, Native Navigation

Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Keep the data flow linear:

```text
known ContextRef.filePath / ContextService locator / tool result
  → provider context preserves exact vault target
  → shared Sidechat prompt requires [[target|label]]
  → MarkdownRenderer
  → Obsidian native internal-link navigation
```

Implementation:

1. Extend the shared Sidechat base prompt with one compact contract:
   use `[[vault-relative/path|label]]` only for an existing target whose exact
   path is supplied by context/evidence/tools; omit `.md`; preserve
   `#heading`/`#^block`; use plain text when uncertain.
2. Make `contextPromptLabel(ref)` include `ref.filePath` when present, so both
   pinned and auto context call sites retain identity without duplicate logic.
3. Add a pure formatter for a ContextService `locator`. Emit a
   `vault_link_target: [[...]]` line only for usable vault locators; include it
   in `formatCuratorContextPack`.
4. Leave ordinary rendered internal links native. Add no second resolver unless
   live Obsidian characterization proves the current native click path broken.

Pseudocode:

```ts
function formatLocatorTarget(locator): string {
  if (!usableVaultLocator(locator)) return "";
  let target = stripMd(locator.relpath);
  if (locator.block_id) target += `#^${locator.block_id}`;
  else if (locator.heading) target += `#${locator.heading}`;
  return `[[${target}]]`;
}
```

## 2. Pros & Cons

Pros:

- Reuses already-authoritative paths; no new search subsystem or schema.
- Same prompt reaches every configured model/provider.
- No whole-vault path disclosure or token blow-up.
- Native Obsidian semantics retain aliases, hover, modifier-click, and page
  resolution.

Cons:

- The assistant can link only notes it actually knows through current context,
  evidence, or tools.
- Live Obsidian smoke is still required because Node tests cannot execute the
  real `MarkdownRenderer` click contract.
