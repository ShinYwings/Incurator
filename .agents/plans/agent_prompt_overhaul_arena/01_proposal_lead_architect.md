# Frontend/Architecture Proposal: Composable Prompt Registry + Surface Profiles

Date: 2026-06-20 | Agent Persona: lead_architect (The Proposer)

## 1. Core Logic & Implementation

### 1.1 New module: `plugin/src/context/promptRegistry.ts`
A single source of truth for every reusable prompt block. Each block is a pure
function returning a string. No state, fully unit-testable.

```ts
// promptRegistry.ts
export const PromptBlocks = {
  persona: () => "You are an AI assistant embedded in Obsidian...",
  mathRules: () => "When writing math, use Obsidian-compatible LaTeX...",
  languageRules: () => "Detect the latest user request's input language...",
  editFormatRules: () => "When the user asks you to modify Markdown notes...", // ai-agent-edit
  boundaryConstraints: (p: SurfaceProfile) =>
    p.toolPolicy === "none"
      ? "You have NO tools and NO filesystem access. Never list, browse, create, "
        + "or execute files or scripts. Answer only from the provided context."
      : "Tool/file access is limited to the vault, the configured Zotero folder, "
        + "and the Zotero library. Never traverse or create files outside them.",
  incuratorMcp: () => EXTERNAL_INCURATOR_MCP_ADDENDUM,
  planMode: () => PLAN_MODE_ADDENDUM,
  editLoopContract: () => getEditLoopContract(),     // re-exported, unchanged text
};
```

### 1.2 Surface profiles
```ts
export type ToolPolicy = "auto" | "none";
export interface SurfaceProfile {
  surface: "sidechat" | "popover";
  toolPolicy: ToolPolicy;
  allowEdits: boolean;        // popover = false
  hasExternalIncuratorMcp: boolean;
  planMode: boolean;
}
```

### 1.3 Behavior-preserving assembly
`buildBaseSystemPrompt` (sidechat) keeps its **exact current output text** but is
re-implemented as a composition of `PromptBlocks` so the literal lives once.
`buildQuickQueryMessages` (popover) keeps its concise reading-assistant persona
but sources its boundary line from `PromptBlocks.boundaryConstraints({toolPolicy:
"none"})` so the "no filesystem" rule can never again drift between surfaces.

Golden-master tests snapshot the current strings BEFORE refactor; the refactor
must reproduce them byte-for-byte (except the intentionally strengthened popover
boundary line).

### 1.4 Recency anchor (fixes F1)
New block appended LAST in the final payload (strongest attention position):

```ts
export function buildRecencyAnchor(p: SurfaceProfile, hasPrimarySelection: boolean): string {
  const lines = ["<critical_invariants>"];
  if (hasPrimarySelection)
    lines.push("Answer ONLY about <primary_focus_selection>. Do NOT explain or "
      + "edit the whole document unless the latest request explicitly asks.");
  if (!p.allowEdits)
    lines.push("Do NOT output ai-agent-edit blocks; this surface is read-only.");
  lines.push(p.toolPolicy === "none"
    ? "Do NOT call any tool or touch the filesystem."
    : "Stay within the vault / Zotero roots for any tool or file access.");
  lines.push("</critical_invariants>");
  return lines.join("\n");
}
```
In the sidechat, this anchor is appended to the latest user message wrapper
(after `wrapLatestUserMessageForLanguageBridge`), so it survives the
`CONTINUITY_MESSAGE_LIMIT` history slice (the latest turn is always included).

### 1.5 Tool-policy gate (fixes F2)
`streamChat` gains a third optional argument:
```ts
async streamChat(messages, onChunk, opts?: { toolPolicy?: ToolPolicy }): Promise<string>
```
When `opts.toolPolicy === "none"`, the method skips `getAllTools()` entirely and
runs the single-turn path. Default (`undefined`/`"auto"`) preserves today's
behavior, so the sidechat caller is untouched. The popover passes
`{ toolPolicy: "none" }`.

## 2. Pros & Cons

**Pros**
- One registry kills the duplication permanently; a boundary fix lands in both
  surfaces by construction.
- Tool isolation is a 1-line opt-in at the call site + a guard in `streamChat`;
  minimal blast radius.
- Recency anchor is additive — no existing text is removed, only appended — so
  edit-loop and language-bridge behavior is preserved.
- Golden-master tests make the refactor provably behavior-preserving.

**Cons / limits**
- `chatSidebar.ts` is a large, stateful caller (~1800 lines). Re-routing it
  through the registry risks accidental text drift → mitigated by golden-master.
- Hard path sandboxing of *external* MCP servers is NOT solvable here (see
  red_team critique); we constrain via prompt + popover tool-kill, not by
  intercepting an external server's syscalls.
