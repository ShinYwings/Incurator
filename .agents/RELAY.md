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

Review round landed (PR #46 updated): re-added `agy --sandbox` (no-hang), allowed the
CLI agents' own state dirs (~/.gemini/.codex/.claude) so they don't crash, switched
macOS to inline `sandbox-exec -p` (no temp-file race), in-process bwrap PATH lookup,
gated --add-dir on !ephemeral. Relocated device-local plugin caches off ~/.incurator
to <incuratorRepoPath>/.cache/cli/ (OS-tmpdir fallback). Live-validated the real
profile: vault write allowed, out-of-vault denied, ~/.gemini allowed, nested children
contained.

CI: plugin tsc + vitest (527) green; spec_sync/ruff/mypy green. Backend unchanged.

Only remaining: in-Obsidian end-to-end smoke (real agy/claude popover + sidechat
write-outside-vault attempt) — needs the running app; user to verify.

Next roadmap priority: Prompt Architecture Overhaul & Refactoring.
