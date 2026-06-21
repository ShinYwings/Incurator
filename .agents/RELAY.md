# Active Relay State

**STATUS: IDLE (v0.23.0 implemented; PR pending)**

**Branch**: `feature/popover-tool-scope`

v0.23.0 — **CLI provider tool-scope sandbox** — implemented:
- `toolPolicy` threaded into the CLI command builder; popover runs CLI tool-free,
  sidechat scopes tools to allowed roots (vault + Zotero). Dropped
  `agy --dangerously-skip-permissions` / trust-workspace.
- Per-provider: claude `--tools ""`/`--disallowedTools`; codex `read-only`/
  `workspace-write`+`--add-dir`. agy ineffective at self-sandboxing → wrapped in an
  OS sandbox (macOS `sandbox-exec` validated; Linux `bwrap`, refuse+guide if missing;
  Windows out of scope). Reads allowed; writes/exec contained.
- `src/agent/sandboxWrapper.ts` (pure, unit-tested) + llmClient integration +
  source-contract tests. PLUGIN_SCHEMA §13.6 + PLUGIN_GUIDE EN/KR. v0.23.0 bump.

CI: spec_sync, ruff, mypy, plugin tsc, plugin vitest (524) all green. Backend
unchanged (plugin-only milestone).

Manual smoke for the user: trigger a popover query on PDF text + a sidechat agy
request that tries to write outside the vault → confirm no out-of-root file is
created.

Next roadmap priority: Prompt Architecture Overhaul & Refactoring.
