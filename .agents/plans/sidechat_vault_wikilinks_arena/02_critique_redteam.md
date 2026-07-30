# Critique on Grounded Link Targets

Date: 2026-07-30 | Agent Persona: Red Teamer

## 1. Vulnerabilities & Flaws

- A prompt-only change would still fail when the exact path is removed before
  the provider sees it. Pinned contexts and ContextService locators prove this
  risk today.
- Dumping `vault.getMarkdownFiles()` into the prompt would solve discovery only
  superficially while leaking unrelated filenames and consuming unbounded
  tokens.
- Formatting every locator is unsafe. `unavailable`, `stale`,
  `duplicate_anchor`, external URI, and source-only locators must not become
  clickable assertions.
- Markdown headings can contain link-sensitive characters. The formatter must
  preserve the stored heading without inventing an anchor and must prefer a
  block id when one is explicitly available.
- Adding a generic click listener to every internal anchor could double-fire
  alongside MarkdownRenderer, break modifier-click/new-pane behavior, or
  interfere with the existing PDF and Curator link handlers.
- The old roadmap mixed this UI contract with Failure Atlas F9. Implementing
  graph topology would be a large schema/compiler change and still would not
  force the Sidechat model to emit a link.

## 2. Suggested Alternatives

- Pair the prompt rule with lossless preservation of paths already in scope.
- Use a strict locator allowlist based on `source_kind`, `relpath`, and
  `locator_status`; return no target for ambiguous or unavailable evidence.
- Characterize native link rendering in a real Obsidian runtime before adding
  navigation code.
- Keep Failure Atlas F9 queued as a separate backend compiler milestone.
- Add cross-model live smoke with at least one weak/local model and one CLI
  provider so prompt compliance is measured rather than assumed.
