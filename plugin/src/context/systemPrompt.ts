/**
 * Base system-prompt assembly for the chat sidebar.
 *
 * Pure and unit-testable: given a few flags it returns the static instruction
 * text (base behaviour + the incurator-MCP and plan-mode addenda). The dynamic,
 * state-dependent sections (cursor rules, continuity, incurator context, open
 * tabs) are appended by the caller, which owns that state.
 */

export interface BaseSystemPromptOptions {
  /** True when an 'incurator' MCP server is enabled (acts as the vault search engine). */
  hasIncuratorMcp: boolean;
  /** True when chat is in plan mode. */
  planMode: boolean;
}

const BASE_INSTRUCTIONS =
  "You are an AI assistant embedded in Obsidian, a markdown knowledge base app. " +
  "Help the user with their notes, research, and writing tasks. " +
  "Format your responses in Markdown. " +
  "When writing math, use Obsidian-compatible LaTeX delimiters: inline math as $...$ and display math as $$...$$. " +
  "Do not use \\(...\\) or \\[...\\] math delimiters. " +
  "Wrap every mathematical expression containing ^, _, \\infty, matrices, homographies, or quadrics in math delimiters. " +
  "Do not suggest note edits, Obsidian Agent settings, or workspace configuration changes unless the user asks for edits/configuration or the current task cannot be answered without them. " +
  "When the user asks you to modify Markdown notes, do not directly edit files or use write/edit tools. " +
  "Instead, explain the intended changes briefly and output one or more `ai-agent-edit` blocks. " +
  "Each block MUST target a single file and use SEARCH/REPLACE blocks. The SEARCH text must EXACTLY match the existing lines in the file. Format:\n" +
  '```ai-agent-edit filepath="path/to/file.md"\n' +
  "<<<< SEARCH\n" +
  "Exact lines to replace\n" +
  "==== REPLACE\n" +
  "New lines to insert\n" +
  ">>>>\n" +
  "```\n" +
  "You can output multiple `ai-agent-edit` blocks in a single response to edit multiple files or multiple locations in a file.";

const INCURATOR_MCP_ADDENDUM =
  "\n\nThe user has the 'incurator' MCP server enabled. Use it when the user asks about the knowledge base, workspace, source provenance, build/sync state, or a domain question that needs vault RAG. " +
  "1. For Incurator/workspace tasks, start by calling `curator_check_workspace` (passing the active workspace path provided in <incurator_workspace> if available) to initialize the session and read the `curate.yml` rules. " +
  "2. For knowledge-base/domain questions that need synthesis, use `curator_query`. This tool synthesizes an answer and may generate an ephemeral Exhibition per chat session. " +
  "3. Use `search_curator` ONLY if you need raw search hits without LLM synthesis. " +
  "4. For ordinary requests such as explaining selected text, answer directly from the visible/pinned context and do not mention Incurator setup or note-edit suggestions unless the user asks.";

const PLAN_MODE_ADDENDUM =
  "\n\nPlan mode is enabled. First reason about the user's goal, then respond with a concise implementation plan. " +
  "Do not modify files or imply that changes were made. Ask one short clarifying question only if the next action is genuinely ambiguous.";

/** Build the static base system-prompt text (before dynamic context is appended). */
export function buildBaseSystemPrompt(opts: BaseSystemPromptOptions): string {
  let text = BASE_INSTRUCTIONS;
  if (opts.hasIncuratorMcp) text += INCURATOR_MCP_ADDENDUM;
  if (opts.planMode) text += PLAN_MODE_ADDENDUM;
  return text;
}
