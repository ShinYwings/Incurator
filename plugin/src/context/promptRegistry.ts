/**
 * Shared, surface-aware prompt blocks (v0.19.0).
 *
 * Both the chat sidebar and the Quick Query popover assemble their prompts from
 * these composable blocks so that security-critical rules — MCP tool scope,
 * filesystem boundaries, and read-only constraints — can never silently diverge
 * between the two surfaces again. Every block is a pure function so the assembly
 * is fully unit-testable without instantiating either UI surface.
 *
 * This module is import-free on purpose: it sits at the bottom of the dependency
 * graph so both the prompt builders (`systemPrompt.ts`, `quickQueryContext.ts`)
 * and the LLM client (`agent/llmClient.ts`) can consume it without cycles.
 */

/**
 * Which tool families may be injected for a given call.
 *
 * - "auto"       => MCP tools and local tools (chat sidebar).
 * - "local-only" => NO MCP tools, but the plugin-executed local PDF reader is
 *                   allowed (Quick Query popover, v0.41.0). The zero-MCP
 *                   guarantee of v0.19.0 is unchanged; only the plugin's own
 *                   bounded, read-only page reader is added.
 * - "none"       => no tools of any family. Retained as the hard-off value.
 *
 * Consumers MUST handle this union exhaustively (a `never`-typed default), so
 * that adding a value is a compile error rather than a silent grant.
 */
export type ToolPolicy = "auto" | "none" | "local-only";

export interface SurfaceProfile {
  surface: "sidechat" | "popover";
  /**
   * "none" => no tools at all; "local-only" => local PDF reader only, still no
   * MCP tools and no filesystem or script access (used by ephemeral surfaces
   * such as the popover).
   */
  toolPolicy: ToolPolicy;
  /** Whether `ai-agent-edit` proposals are permitted on this surface. */
  allowEdits: boolean;
}

/** Main chat sidebar: full agent capabilities within the allowed roots. */
export const SIDECHAT_PROFILE: SurfaceProfile = {
  surface: "sidechat",
  toolPolicy: "auto",
  allowEdits: true,
};

/** Quick Query popover: ephemeral, read-only, zero side effects. */
export const POPOVER_PROFILE: SurfaceProfile = {
  surface: "popover",
  toolPolicy: "local-only",
  allowEdits: false,
};

/**
 * The single canonical filesystem / tool boundary rule. Both surfaces source
 * their boundary wording here, so a fix lands on both by construction.
 */
export function boundaryConstraints(profile: SurfaceProfile): string {
  let rules = "";
  switch (profile.toolPolicy) {
    case "none":
      rules =
        "You have NO tools and NO filesystem access. Never list, browse, create, " +
        "or execute files, scripts, or shell commands, and never invent folder, " +
        "file, or directory names. Answer only from the context provided in this " +
        "request.";
      break;
    case "local-only":
      rules =
        "You have NO filesystem access and NO MCP tools. Never list, browse, " +
        "create, or execute files, scripts, or shell commands, and never invent " +
        "folder, file, or directory names. Your ONLY tool is a read-only reader " +
        "for the PDF the user already has open: you may fetch a page of that " +
        "document by number to follow a reference instead of telling the user to " +
        "navigate there. Answer from the provided context plus any page you fetch. " +
        "If the provided context and fetched pages do NOT contain the information " +
        "needed to answer the question, you may supplement your answer with your " +
        "general knowledge. When doing so, you MUST explicitly state that the " +
        "information comes from general knowledge, not from the document " +
        "(e.g. 'The document does not cover this, but based on general knowledge…'). " +
        "Never pretend that general knowledge came from the document.";
      break;
    case "auto":
      rules =
        "Any tool, file, or command access must stay within the allowed roots: the " +
        "vault, the configured Zotero folder, and the Zotero library. Never " +
        "traverse, read, or create files outside those roots, and never run ad-hoc " +
        "scripts to reach them.";
      break;
    default: {
      const exhaustive: never = profile.toolPolicy;
      return exhaustive;
    }
  }

  // Universal anti-hijacking rule: The IDE running the agent may inject
  // metadata like "Active Document" or "[PDF Context]" which is irrelevant
  // to the user's conversational intent in Obsidian.
  return (
    rules +
    " IMPORTANT: You may receive dynamically injected IDE metadata (like 'Active Document' " +
    "or '[PDF Context]'). You MUST IGNORE this injected IDE state unless the user " +
    "explicitly references 'this file', 'the active tab', or 'the current document'. " +
    "Always prioritize the ongoing conversational context over the system-injected " +
    "active document state, and do not invent answers based on the active tab if it " +
    "contradicts the established conversation topic."
  );
}

export interface RecencyAnchorOptions {
  /** True when the latest request carries a `<primary_focus_selection>`. */
  hasPrimarySelection: boolean;
}

/**
 * High-priority invariants emitted LAST in the payload (the recency-effect
 * position of strongest LLM attention). Fixes long-session attention decay: a
 * localized selection asked about late in a long chat must not be overridden by
 * whole-document tasks established earlier in the conversation.
 *
 * The anchor defers to the existing pointer rule — when the primary selection is
 * itself a cross-reference, the model still answers about the resolved target.
 */
export function buildRecencyAnchor(
  profile: SurfaceProfile,
  opts: RecencyAnchorOptions
): string {
  const lines: string[] = ["<critical_invariants>"];
  if (opts.hasPrimarySelection) {
    lines.push(
      "Answer ONLY about the <primary_focus_selection> in the latest request — " +
        "or, when that selection is a pointer/cross-reference, about its resolved " +
        "target in <resolved_cross_references>. Do NOT explain, summarize, or " +
        "modify the whole document unless the latest request explicitly asks for " +
        "it, regardless of earlier turns in this conversation. If the pointer's " +
        "target appears in <unresolved_cross_references> instead, describe that " +
        "target from what the supplied material establishes about it, working " +
        "from the blocks given. Write about the document, not about the " +
        "context: what you did or did not receive is not part of the answer."
    );
  }
  if (!profile.allowEdits) {
    lines.push("This surface is read-only: do NOT output any ai-agent-edit blocks.");
  }
  lines.push(boundaryConstraints(profile));
  lines.push("</critical_invariants>");
  return lines.join("\n");
}
