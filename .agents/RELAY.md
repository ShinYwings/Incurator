# Active Relay State

**STATUS: PLANNING (awaiting human review)**

**Active Branch**: `feature/popover-tool-scope`
**Milestone**: Popover Tool Scope & CLI Sandbox Violation → target `v0.23.0`
**Plan**: `.agents/plans/01_popover_tool_scope.md` (Arena: `.agents/plans/popover_tool_scope_arena/`)

## Analysis & Reasoning (key finding — corrects the draft)
The draft's concerns #1 (unconditional MCP injection) and #2 (prompt duplication)
were ALREADY fixed in v0.19.0 — but only on the HTTP path. The REAL open vector is
the **CLI providers**: `toolPolicy` never reaches `buildCliCommand` (`llmClient.ts:1826`),
so a CLI-backed popover/sidechat inherits the CLI agent's NATIVE tools. `agy` uses
`--dangerously-skip-permissions` (the `find_mvg_text.py` exploit). The Incurator MCP
server exposes no fs/exec tool — the escape is CLI-native.

## Locked decisions (user, 2026-06-21)
- Scope (a): BOTH (1) thread toolPolicy into the CLI path → popover tool-free, and
  (2) sidechat tools scoped to allowed roots (vault + Zotero) via each CLI's native
  sandbox/`--add-dir`, replacing `--dangerously-skip-permissions`.
- `agy --dangerously-skip-permissions` was a hang workaround; replace with
  `--sandbox` + `--add-dir` (deny-not-prompt). No interactive-approval UI this round.

## Progress
Arena debate + Master Plan authored. P0 is a HARD empirical gate (per-CLI
deny-not-hang validation).

## Immediate Next Action
AWAITING human review of the Master Plan before implementation (P0 → P5).
