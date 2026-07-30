# Defense: Bounded Targets And One Navigation Owner

Date: 2026-07-30 | Agent Persona: System Synthesizer

## 1. Consensus Revisions

- The change is not prompt-only: it closes the two observed identity-loss points
  (`ContextRef.filePath` and `CuratorContextItem.locator`) first.
- Locator formatting is fail-closed. Only vault-backed locators with a non-empty
  `relpath` and usable status produce a link target. External/unavailable/stale
  locators stay descriptive evidence.
- No global vault inventory is injected. Tools remain the discovery mechanism
  for pages outside the current evidence/context boundary.
- Obsidian remains the single navigation owner for ordinary visible-vault
  links. The existing targeted handlers remain responsible only for hidden DAG,
  PDF, and explicit block-locator special cases.
- Failure Atlas F9 is explicitly separated from this release.

## 2. Final Contract

For a known note target:

```text
Markdown note: 03_Notes/Residual Learning.md
Answer syntax: [[03_Notes/Residual Learning|Residual Learning]]

Heading: 03_Notes/Residual Learning.md + Dynamics
Answer syntax: [[03_Notes/Residual Learning#Dynamics|Dynamics]]

Block: 03_Notes/Residual Learning.md + ^proof-1
Answer syntax: [[03_Notes/Residual Learning#^proof-1|proof]]
```

If the exact target is not present in current context, evidence, or a tool
result, the assistant writes ordinary text instead of guessing.
