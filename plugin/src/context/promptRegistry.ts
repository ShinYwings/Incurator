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

/** Whether MCP tools may be injected for a given call. */
export type ToolPolicy = "auto" | "none";

export interface SurfaceProfile {
  surface: "sidechat" | "popover";
  /**
   * "none" => no MCP tools are injected and the prompt forbids any filesystem
   * or script access (used by ephemeral surfaces such as the popover).
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
  toolPolicy: "none",
  allowEdits: false,
};

/**
 * The single canonical filesystem / tool boundary rule. Both surfaces source
 * their boundary wording here, so a fix lands on both by construction.
 */
export function boundaryConstraints(profile: SurfaceProfile): string {
  if (profile.toolPolicy === "none") {
    return (
      "You have NO tools and NO filesystem access. Never list, browse, create, " +
      "or execute files, scripts, or shell commands, and never invent folder, " +
      "file, or directory names. Answer only from the context provided in this " +
      "request."
    );
  }
  return (
    "Any tool, file, or command access must stay within the allowed roots: the " +
    "vault, the configured Zotero folder, and the Zotero library. Never " +
    "traverse, read, or create files outside those roots, and never run ad-hoc " +
    "scripts to reach them."
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
        "it, regardless of earlier turns in this conversation."
    );
  }
  if (!profile.allowEdits) {
    lines.push("This surface is read-only: do NOT output any ai-agent-edit blocks.");
  }
  lines.push(boundaryConstraints(profile));
  lines.push("</critical_invariants>");
  return lines.join("\n");
}
