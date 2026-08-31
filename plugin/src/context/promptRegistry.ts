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
/**
 * What the surface can actually reach, for the provider in hand.
 *
 * `ToolPolicy` says what the plugin INTENDS to hand out. That is not the same as
 * what the model ends up holding, and until v0.77.0 the popover's prompt stated
 * the intent as though it were the fact — with two errors pointing the same way:
 *
 *  - It promised "you may fetch a page of that document by number". But
 *    `shouldInjectLocalTools` returns false whenever `useCli` is true, for every
 *    policy, and every provider except ollama/deepseek routes through a CLI. On
 *    the surface the bug was reported from, that tool was never there.
 *  - It claimed "NO MCP tools". True for API providers, where the plugin decides
 *    injection. False for `agy`, which reads its own registry — `syncAgyMcpConfig`
 *    runs unconditionally and the ephemeral flag only empties `--add-dir`.
 *
 * A model promised a page reader that is absent reaches for the nearest
 * substitute, and the nearest substitute is a URL tool that is not in the
 * allow-list. The request was auto-denied and the turn produced nothing, while
 * the answer sat in the paper's own last pages. Reported 2026-08-31.
 *
 * Required, not defaulted: a missed call site should be a compile error rather
 * than a prompt that quietly lies again.
 */
/**
 * The one place that decides which reality a provider is in.
 *
 * Mirrors `LLMClient.shouldUseCli`: everything except ollama and deepseek routes
 * through a CLI subprocess, and a CLI subprocess gets no injected tools and
 * loads its own MCP registry. Kept here, beside the wording it governs, so the
 * prompt and the routing cannot drift apart silently — which is exactly what
 * happened before v0.77.0.
 */
export function surfaceToolReality(provider: string): SurfaceToolReality {
  return provider === "ollama" || provider === "deepseek"
    ? "plugin-injected"
    : "cli-registry";
}

export type SurfaceToolReality =
  /** API providers: the plugin injects its own readers, and no MCP tools exist. */
  | "plugin-injected"
  /** CLI providers: nothing is injected; the CLI's own MCP registry is what it has. */
  | "cli-registry";

export function boundaryConstraints(
  profile: SurfaceProfile,
  reality: SurfaceToolReality
): string {
  let rules = "";
  switch (profile.toolPolicy) {
    case "none":
      rules =
        "You have NO tools and NO filesystem access. Never list, browse, create, " +
        "or execute files, scripts, or shell commands, and never invent folder, " +
        "file, or directory names. Answer only from the context provided in this " +
        "request.";
      break;
      case "local-only": {
        // The two variants differ in ONE clause — whether a page reader exists —
        // so only that clause is written twice. Duplicating the shared prose
        // would grow the prompt budget for text the model never sees twice.
        const reach =
          reality === "plugin-injected"
            ? "Your only tools read the PDF the user already has open, and nothing " +
              "else: you may fetch a page of that document by number to follow a " +
              "reference instead of telling the user to navigate there, and — where " +
              "`read_pdf_page_image` is among the tools you were given — you may read " +
              "a page as an image when what you were asked about is not in that " +
              "page's text; a typeset paper draws many of its equations and figures " +
              "as pictures, so the text can read as complete prose while the formula " +
              "itself is simply absent."
            : "You cannot open this document yourself; its pages, cited entries and " +
              "referenced targets are already in the context above. A tool outside " +
              "your permitted set is refused silently and the turn then returns " +
              "nothing, so reaching for one costs the reader their answer.";
        rules =
          "You have NO filesystem access. Never list, browse, create, or execute " +
          "files, scripts, or shell commands, and never invent folder, file, or " +
          "directory names. " +
          reach +
          " Answer from the provided context first; where it does not cover the " +
          "question, answer from your general knowledge of the field rather than " +
          "stopping. Explain the subject — the reader wants the answer, not an " +
          "account of which sentence came from where.";
        break;
      }
    case "auto":
      // The sidechat is the only surface that states the active file and page
      // (ChatSidebarView emits "Currently active file: ..." and "The user is
      // viewing a PDF. Current page: N" on every turn). The universal rule
      // removed in v0.54.1 was the only instruction saying that signal does not
      // override the conversation, so a scoped, positive replacement lives here
      // — on the one profile whose prompt actually carries the line.
      rules =
        "Any tool, file, or command access must stay within the allowed roots: the " +
        "vault, the configured Zotero folder, and the Zotero library. Never " +
        "traverse, read, or create files outside those roots, and never run ad-hoc " +
        "scripts to reach them. The active file and page tell you where the user " +
        "is sitting, not what they asked about; when the conversation has settled " +
        "on a subject, stay with it and treat whatever is open as one more source " +
        "you may draw on.";
      break;
    default: {
      const exhaustive: never = profile.toolPolicy;
      return exhaustive;
    }
  }

  // v0.53.2 appended a universal rule here telling the model to IGNORE injected
  // IDE metadata ("Active Document", "[PDF Context]"). That treated a symptom:
  // the metadata arrived because a spawned `agy` inherited the host IDE's
  // ANTIGRAVITY_* variables and reconnected to its daemon. Both spawn sites now
  // scrub those variables — LLMClient.getAugmentedEnv since v0.53.2, and
  // curator/llm.py `_repo_temp_env` as of v0.54.1 — so the metadata never
  // reaches the model and the instruction has nothing to suppress.
  //
  // It is removed rather than left as belt-and-braces: it rode on EVERY surface,
  // including ones that never spawn a CLI, and it was phrased as a prohibition.
  // Negative instructions prime the behaviour they forbid, so a rule naming
  // "Active Document" and "[PDF Context]" on a surface with neither was pure
  // dilution of the instructions that do apply.
  return rules;
}

export interface RecencyAnchorOptions {
  /** True when the latest request carries a `<primary_focus_selection>`. */
  hasPrimarySelection: boolean;
  /**
   * What the surface can actually reach, for the provider in hand.
   *
   * This anchor re-emits `boundaryConstraints` at the END of the payload, the
   * position of strongest attention. Fixing the direct call site and not this one
   * would leave the stale claim as the last thing the model reads, which is worse
   * than not fixing it at all.
   */
  reality: SurfaceToolReality;
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
        "it, regardless of earlier turns in this conversation. " +
        "A <resolved_citations> block, when present, holds the papers the " +
        "selection cites; answer about the cited work from its entry there. " +
        "A <workspace_notes> block holds notes the reader wrote themselves in " +
        "this project; when they bear on the question, say what the reader " +
        "already concluded and attribute it to them. " +
        "If the pointer's " +
        "target appears in <unresolved_cross_references> instead, call " +
        "`read_pdf_page_image` on the page it names where you were given that " +
        "tool — a rasterized equation has no text to find — and otherwise " +
        "describe the target from " +
        "what the supplied material establishes about it. Write about the " +
        "document, not about the context: what you did or did not receive is " +
        "not part of the answer."
    );
  }
  if (!profile.allowEdits) {
    lines.push("This surface is read-only: do NOT output any ai-agent-edit blocks.");
  }
  lines.push(boundaryConstraints(profile, opts.reality));
  lines.push("</critical_invariants>");
  return lines.join("\n");
}
