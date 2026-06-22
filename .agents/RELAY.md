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

Security hardening round (PR #46): dropped the broad ~/.config / ~/.cache /
~/Library/Caches writes + /private/var/folders + /private/tmp roots from the sandbox
allow-list (autostart/other-app-config escalation). Scoped to the CLIs' OWN dirs only
(~/.gemini/.antigravity/.claude/.codex) + specific $TMPDIR + roots. bwrap no longer
re-binds /tmp over its tmpfs; roots use --bind-try. Live-validated: ~/.config/autostart
write DENIED, vault + ~/.gemini ALLOWED. Considered a full HOME/CODEX_HOME redirect
into <repo>/.cache (zero home exceptions) but BACKED IT OUT — cascades into config.toml
/ settings.json relocation + OAuth-secret mirroring for 3 CLIs, unverifiable headless,
high risk of breaking login. USER DECISION: keep the scoped version (safe). PLUGIN_SCHEMA
§13.6 updated (inline -p, scoped list, tmpfs /tmp, .cache/cli relocation).

Code-review round (PR #46): fixed (1) Zotero now READ-ONLY in the sandbox — split
allowedRoots() [read/--add-dir: vault+Zotero+storage] from sandboxWriteRoots()
[write: vault only] so a prompt-injected agent can't corrupt the user's Zotero
library; live-validated (vault write allowed, Zotero write denied, Zotero read ok).
(2) Reconciled spec/impl: sandbox-unavailable → agy refused, claude/codex degrade to
flag-based containment + console.warn; PLUGIN_SCHEMA §13.6 + PLUGIN_GUIDE EN/KR
rewritten to match. (3) Documented fail-open toolPolicy default. Cleanups: reuse
expandPath() (3 dup regexes gone), lazy --add-dir, cached getCliCwd mkdir.
Refuted (verified): claude tool-hang (claude never had skip-permissions), symlink
escape (seatbelt resolves realpath → denied), firmlink mismatch (empirically ok).

CI: plugin tsc + vitest (532) green; spec_sync/ruff/mypy green. Backend unchanged.

Review coverage caveat: 3/8 finder angles (line-by-line, cross-file, test-quality)
hit the session limit and returned empty — a re-run would complete the pass.
Remaining: in-Obsidian smoke (real agy/claude popover + sidechat write-outside-vault
attempt; also confirm codex read-only popover still returns its --output-last-message
answer) — needs the running app; user to verify.

Next roadmap priority: Prompt Architecture Overhaul & Refactoring.
