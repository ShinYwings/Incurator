# Defense & Synthesis

Date: 2026-06-19 | Agent Persona: system_synthesizer

The red-team critique is accepted in full; it converts a risky rewrite into a
safe strangler refactor. Consensus resolutions:

- **C1 → accepted.** Renderer extraction is the LAST phase, incremental, registry
  first, preserving module-load timing. A characterization test for persisted-doc
  rehydration is written in P0 before any move.
- **C2 → accepted.** "Single entry point, not single implementation." The plugin
  keeps a local Zotero fallback used only when `client.available === false`.
- **C3 → accepted.** All `AssetIdentity` / `AssetSource` fields optional; add
  `resolution_status` mirroring `locator_status`.
- **C4 → accepted, hard gate.** The resolver is a *facade* feeding the existing
  dedup branches. No dedup SQL is merged in this milestone. Dedup regression
  tests land in P0. schema_guardian sign-off required before P2 merges.
- **C5 → accepted.** `crossReferenceResolver.ts` and `pdfCapture.ts` are
  explicit non-goals; the new model is adapted at their boundary only.
- **C6 → accepted.** Item 3 gets a repro attempt first; close as wontfix if it
  cannot be reproduced. The unified status key lands as structure, not "a fix."

**Net-LOC gate** adopted as a release gate.

The resulting plan is therefore additive-then-subtractive: introduce the
resolver, route callers, prove parity, then delete dead private resolvers and
slim the renderer — with a measured net LOC decrease and zero test regressions.
