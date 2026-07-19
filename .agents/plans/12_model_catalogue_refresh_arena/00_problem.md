# v0.35.0 Model Catalogue Refresh Briefing

Date: 2026-07-19

## User Request

Refresh the Claude Code and Codex model choices after both CLIs changed, while
prioritizing code/document parity and finding system bugs exposed by the model
change.

## Current Reality

- Incurator invokes subscription CLIs, not the OpenAI or Anthropic APIs
  directly. The catalogue must therefore match models exposed by the installed
  CLI runtime.
- Installed Codex CLI `0.139.0` cache (fetched 2026-07-19) exposes
  `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, and `gpt-5.5` with an
  effective 272,000-token context window.
- Installed Claude Code `2.1.175` documents the current `fable`, `opus`,
  `sonnet`, and `haiku` aliases and accepts current full model IDs such as
  `claude-fable-5`; the verified safe full-ID set is Fable 5, Opus 4.8,
  Sonnet 4.6, and Haiku 4.5.
- `models.json`, backend defaults, plugin types, static specs, and EN/KR guides
  still describe older models and stop Codex effort at `xhigh`.

## Bugs Exposed During Triage

1. `PLUGIN_SCHEMA.md` requires a `supportsThinking` field that the plugin type
   and catalogue adapter do not implement.
2. Settings, sidebar, dashboard, and load-time migration do not share one model
   effort normalization rule; a model change may preserve an invalid or
   non-default effort.
3. Plugin Claude command construction always emits `--effort`, even for models
   such as Haiku that have no effort dimension.
4. The backend Claude image path must be checked for parity with the normal
   command path so selected effort is never silently lost.
5. Catalogue context windows are token capacities, while one plugin context
   truncation helper uses character counts. This release must document the
   conservative character cap explicitly; changing tokenization is a separate
   behavioral project.

## Release Boundary

- v0.34.1 Knowledge Sync hotfix PR #86 must merge first.
- v0.35.0 is a bounded model catalogue and effort-contract release.
- PL-1 plugin god-file decomposition moves to v0.36.0 because its approved-
  pending plan explicitly excludes provider/model behavior changes.
