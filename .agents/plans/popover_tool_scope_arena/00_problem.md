# Arena Briefing: Popover Tool Scope & CLI Sandbox Violation

Date: 2026-06-21 | Branch: `feature/popover-tool-scope`
Source draft: `.agents/drafts/popover_tool_scope.md`

## Problem (corrected from the draft after code analysis)

The user reported the inline **Quick Query popover** agent running scripts
(`find_mvg_text.py`), searching the whole filesystem, and creating files — far
outside the intended scope (vault + Zotero folder + Zotero library).

The draft attributes this to (1) unconditional MCP tool injection and (2) prompt
duplication between sidechat and popover. **Code analysis shows both were already
fixed in v0.19.0 — but only on the HTTP path:**

- `streamChat(messages, onChunk, { toolPolicy })` gates MCP injection via
  `shouldInjectMcpTools`; the popover calls it with `toolPolicy: "none"` →
  **zero MCP tools** (`quickQueryPopover.ts:468`, `llmClient.ts:678`).
- `quickQueryContext.ts` consumes the shared `promptRegistry.ts`
  (`boundaryConstraints`, `buildRecencyAnchor`, `POPOVER_PROFILE`) — no duplication.

**The REAL, still-open vector is the CLI providers.** `toolPolicy` never reaches
the CLI path: `streamChatViaCli` → `buildCliCommand` (`llmClient.ts:1826`) ignores
it, so a CLI-backed popover/sidechat inherits the CLI agent's NATIVE tools:

| Provider | Current CLI flags | Native tool exposure |
|---|---|---|
| antigravity (`agy`) | `--dangerously-skip-permissions` + `*_TRUST_WORKSPACE=true` | **Unrestricted** — Bash, create/search anywhere (the exploit) |
| claude | `-p` default perms, no `--disallowedTools`/`--add-dir` | Default agent tools (Bash/Write possible) |
| codex | `--sandbox read-only` | No writes, but **filesystem-wide read/search** |

So `find_mvg_text.py` is the CLI agent (most likely `agy` with
`--dangerously-skip-permissions`) using its OWN tools — which `toolPolicy: "none"`
does not govern. v0.19.0 closed the MCP-injection half; the CLI-native-tool half is
the gap.

## Why `--dangerously-skip-permissions` was added (user context)

In non-interactive `-p`/`exec` mode a CLI permission prompt has no one to answer,
so the sidechat **hangs / appears stuck**. `--dangerously-skip-permissions` was a
workaround to avoid the hang — at the cost of unrestricted tool access.

## Locked decisions (user, 2026-06-21)

- Scope **(a)** — BOTH:
  1. **Thread `toolPolicy` into the CLI path.** Popover/ephemeral (`toolPolicy:
     "none"`) builds the CLI command with tools DISABLED → zero side effects on
     every provider.
  2. **Strict path sandboxing for the sidechat** (`toolPolicy: "auto"`): replace
     `--dangerously-skip-permissions`/trust-workspace with access scoped to the
     **allowed roots** (vault + Zotero folder + Zotero library) so even tool-enabled
     surfaces cannot traverse the whole filesystem or run arbitrary shell.
- **Resolve the hang WITHOUT skip-all**: prefer each CLI's *sandbox/deny* mode
  (which enforces/denies rather than prompting) over a blanket skip or a heavy
  interactive-approval bridge. The sandbox denies out-of-bounds ops cleanly, so
  there is no prompt to hang on. A real interactive permission UI is an explicit
  non-goal for this milestone (possible future enhancement).

## Constraints / success criteria

- **Popover = zero side effects** on every provider (HTTP and CLI): a PDF-text
  query answers from the injected context only — no tool calls, no script
  execution, no file creation.
- **Sidechat tools stay useful WITHIN the allowed roots** (curator MCP, reads/edits
  inside vault/Zotero) but cannot escape them or run arbitrary shell.
- **No hang**: restricted ops are denied by the sandbox, not blocked on a prompt.
- Per-provider native flags only (no new external deps): claude
  `--add-dir`/`--allowedTools`/`--disallowedTools`/`--permission-mode`; agy
  `--sandbox`/`--add-dir`; codex `-s read-only|workspace-write` + `-c sandbox_*`.
- Allowed roots derive from `LLMClient.vaultRoot` + `settings.zoteroBasePath` +
  the Zotero library/storage path.
- Plugin-only (TypeScript) change to the CLI command builder + a `.test.ts`.
- Security-sensitive → P0 must EMPIRICALLY validate each CLI's restricted mode
  denies-not-hangs and that legit in-vault tool use still works.
