# Defense and Consensus: Bounded v0.35.0 Model Contract
Date: 2026-07-19 | Agent Persona: System Synthesizer

## 1. Resolved Decisions

- The installed CLI contract wins over broader API availability.
- Codex uses exactly the four currently visible cache entries. Sol becomes the
  default; its native `low` effort becomes the new-install default.
- Claude Code adds Fable 5 and Opus 4.8, retains Sonnet 4.6 and Haiku 4.5, and
  removes the unverified Opus 4.7 entry. Sonnet 4.6 remains the default.
- One pure plugin effort normalizer owns reset, preservation, and no-effort
  behavior across every UI/load surface.
- Specs will describe the actual optional `efforts` fields, not
  `supportsThinking`.
- Context-window values remain provider/CLI token capacities. Existing plugin
  content clipping is documented as a conservative character guard and is not
  advertised as exact token accounting.
- v0.35.0 excludes PL-1 extraction and waits for the v0.34.1 hotfix to merge.

## 2. Required Evidence

- Exact catalogue tests and default-constant parity.
- Command argument tests for Codex `ultra`, Claude no-effort omission, and
  backend Claude image/text effort parity.
- Settings/sidebar/dashboard/load migration tests for default reset and
  no-effort clearing.
- EN docs first, faithful KR synchronization, four spec-title bumps, all local
  CI, production plugin build, and testbed smoke.
