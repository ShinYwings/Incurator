# Obsidian Provider UX + DeepSeek Plan

Date: 2026-06-01
Agent: Codex

## Goal

Resolve the seven active user-reported issues:

1. Markdown note Zotero links on macOS should either open the built-in viewer
   when resolvable or fall through to the Zotero app when not resolvable.
2. Settings should find an installed Codex CLI in common GUI/macOS paths.
3. Backend provider login/account behavior should be explicit: CLI-backed
   providers use each provider CLI's own account store; API-key providers use
   environment/config keys.
4. Quota/capacity failures should appear clearly in sidechat.
5. Ordinary chat/explain requests should not automatically steer the answer
   toward Obsidian Agent settings or note-edit suggestions unless requested.
6. Purple pin ingest, dashboard build, jobs, and source list should use backend
   MCP tools and refresh live state instead of relying on brittle direct CLI
   calls or stale tool names.
7. Add DeepSeek API support across backend, frontend, config, docs, and model
   catalogue.

## Source Of Truth

- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md`
- `docs/guides/PLUGIN_GUIDE.md` / `_KR.md`
- `docs/guides/USER_GUIDE.md` / `_KR.md`
- `docs/guides/WORKFLOW_GUIDE.md` / `_KR.md`
- Official DeepSeek API docs checked on 2026-06-01:
  - OpenAI-compatible base URL: `https://api.deepseek.com`
  - API key environment variable: `DEEPSEEK_API_KEY`
  - Current model IDs: `deepseek-v4-flash`, `deepseek-v4-pro`
  - Legacy aliases `deepseek-chat` and `deepseek-reasoner` are scheduled for
    deprecation on 2026-07-24.

## Implementation Plan

1. Frontend provider plumbing
   - Extend `LLMProvider` with `deepseek`.
   - Add DeepSeek usage defaults and model selector labels.
   - Add API-key auth handling distinct from OAuth/CLI providers.
   - Add a DeepSeek OpenAI-compatible adapter.

2. Backend provider plumbing
   - Add `deepseek-api` constants, model catalogue entries, and config support.
   - Implement a synchronous DeepSeek HTTP client for build/query flows.
   - Wire provider selection through `build_client`, `make_client_by_key`,
     `wiki config provider`, dashboard config, and MCP provider config.

3. UX fixes
   - Zotero link interception should call Zotero externally when the built-in
     resolver cannot open a PDF.
   - Codex CLI discovery should include nvm, volta, bun, npm-global, and common
     Homebrew paths in GUI-launched Obsidian.
   - Sidechat should classify quota/capacity errors and replace noisy provider
     failures with a clear quota message.
   - The base chat prompt should only suggest note edits or Incurator agent
     workflows when the user asks for them.
   - Dashboard actions should call MCP tools via `IncuratorClient` and refresh
     Overview/Jobs/Sources state after actions.

4. Docs and tests
   - Update plugin/system specs and guides for DeepSeek and provider account
     scenarios.
   - Add TypeScript tests for provider typing, prompt behavior, CLI path
     discovery, and quota classification where practical.
   - Add backend tests for DeepSeek client construction, request payloads, and
     model catalogue exposure.

## Verification Gates

- `git diff --check`
- Plugin tests covering updated prompt/provider/path helpers.
- Backend pytest covering DeepSeek provider config/client behavior.
- TypeScript build or test command available in `plugin/package.json`.
- Manual code audit for Zotero fallback and dashboard MCP tool names.
