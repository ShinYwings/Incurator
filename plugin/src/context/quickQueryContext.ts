import {
  escapeAttribute,
  formatOutline,
  formatPdfWindow,
  truncateForProviderContext,
} from "./providerContextFormat";
import { contextPriorityInstruction } from "./chatContextPriority";
import { resolveSelectionReferencesBlock } from "./pdfReferenceContext";
import type { ActiveContext, LLMMessage } from "../types";

export interface QuickQueryTurn {
  question: string;
  answer: string;
}

export interface QuickQueryMessageArgs {
  selectedText: string;
  question: string;
  activeContext?: ActiveContext;
  previousTurns?: QuickQueryTurn[];
  maxBackgroundLength?: number;
}

const DEFAULT_BACKGROUND_LIMIT = 12000;
const FOLLOWUP_TURN_LIMIT = 3;
const FOLLOWUP_TEXT_LIMIT = 4000;

export function buildPrimarySelectionBlock(selectedText: string): string {
  return `<primary_focus_selection>\n${selectedText.trim()}\n</primary_focus_selection>`;
}

export function buildMarkdownOutline(markdown: string): string {
  return markdown
    .split(/\r?\n/)
    .map((line) => {
      const match = /^(#{1,6})\s+(.+?)\s*$/.exec(line);
      if (!match) return "";
      const level = match[1].length - 1;
      const title = match[2].replace(/\s+#*$/, "").trim();
      if (!title) return "";
      return `${"  ".repeat(level)}- ${title}`;
    })
    .filter(Boolean)
    .slice(0, 80)
    .join("\n");
}

export function buildActiveBackgroundContext(
  activeCtx: ActiveContext | undefined,
  options: { selectedText?: string; maxBackgroundLength?: number } = {}
): string {
  if (!activeCtx) return "";
  const maxLength = options.maxBackgroundLength ?? DEFAULT_BACKGROUND_LIMIT;
  const sections: string[] = [];
  const label = activeCtx.displayName || activeCtx.filePath || "active view";

  if (activeCtx.viewType === "markdown" && activeCtx.fileContent?.trim()) {
    const outline = buildMarkdownOutline(activeCtx.fileContent);
    if (outline) {
      sections.push(
        `<markdown_outline document="${escapeAttribute(label)}">\n${outline}\n</markdown_outline>`
      );
    }

    const path = activeCtx.filePath ? ` path="${escapeAttribute(activeCtx.filePath)}"` : "";
    sections.push(
      `<active_markdown document="${escapeAttribute(label)}"${path}>\n` +
        `<background_reference_only>\n` +
        `${truncateForProviderContext(activeCtx.fileContent, Math.floor(maxLength / 2))}\n` +
        `</background_reference_only>\n` +
        `</active_markdown>`
    );
  }

  const pdf = activeCtx.pdfPage;
  if (activeCtx.viewType === "pdf" && pdf) {
    const doc = pdf.documentName || activeCtx.displayName || activeCtx.filePath || "active PDF";
    if (pdf.windowPages?.length) {
      sections.push(
        `<pdf_window document="${escapeAttribute(doc)}" current_page="${pdf.pageNum}">\n` +
          `${formatPdfWindow(pdf.windowPages)}\n` +
          `</pdf_window>`
      );
    } else if (pdf.text?.trim()) {
      sections.push(
        `<pdf_page document="${escapeAttribute(doc)}" page="${pdf.pageNum}">\n` +
          `<background_reference_only>\n` +
          `${truncateForProviderContext(pdf.text, Math.floor(maxLength / 2))}\n` +
          `</background_reference_only>\n` +
          `</pdf_page>`
      );
    }
    if (pdf.outline?.length) {
      sections.push(
        `<document_outline document="${escapeAttribute(doc)}">\n${formatOutline(pdf.outline)}\n</document_outline>`
      );
    }
  }

  return truncateForProviderContext(sections.join("\n\n"), maxLength);
}

export function buildEphemeralFollowupContext(turns: QuickQueryTurn[] | undefined): string {
  const relevant = (turns ?? []).slice(-FOLLOWUP_TURN_LIMIT);
  if (relevant.length === 0) return "";
  const body = relevant
    .map((turn, index) => {
      const question = truncateForProviderContext(turn.question.trim(), 800);
      const answer = truncateForProviderContext(turn.answer.trim(), 1200);
      return `### Turn ${index + 1}\nUser: ${question}\nAssistant: ${answer}`;
    })
    .join("\n\n");
  return `<quick_query_followups>\n${truncateForProviderContext(body, FOLLOWUP_TEXT_LIMIT)}\n</quick_query_followups>`;
}

export function buildQuickQueryMessages(args: QuickQueryMessageArgs): LLMMessage[] {
  const background = buildActiveBackgroundContext(args.activeContext, {
    selectedText: args.selectedText,
    maxBackgroundLength: args.maxBackgroundLength,
  });
  const followups = buildEphemeralFollowupContext(args.previousTurns);

  const resolvedReferencesBlock = resolveSelectionReferencesBlock(
    args.selectedText,
    args.activeContext?.pdfPage
  );

  const systemText =
    "You are a reading assistant embedded in Obsidian. The user selected a " +
    "passage while reading and asks a quick question about it. Answer " +
    "concisely and directly, in the same language as the question. The " +
    "primary selected passage is the main focus. Use current page, document " +
    "outline/ToC, and prior quick-query turns from the same popover only as " +
    "background to resolve references, equations, and citations. When the " +
    "selection is itself a POINTER (e.g. \"see Section A4.2\", \"Figure 19.1\", " +
    "\"Eq. (3)\"), answer about the referenced TARGET shown in " +
    "<resolved_cross_references>, using the selection only to identify which " +
    "reference to follow — do not explain the visible page. " +
    "Positional or locational phrases in the question (e.g. \"위쪽\", \"아래쪽\", " +
    "\"앞부분\", \"뒷부분\", \"상단\", \"하단\", \"top\", \"above\", \"beginning\", " +
    "\"start\", \"end\", \"below\", \"later in the document\") refer to positions " +
    "WITHIN the current document's content and outline, NOT to the file system " +
    "or surrounding folders. You have no filesystem access: never list, browse, " +
    "or invent folder names, file names, or directory contents. Answer only from " +
    "the selection, the provided document content, and its outline; when asked " +
    "about a region of the document, summarize or quote that region's actual " +
    "content. Do not add " +
    "preamble, sign-off, or restate the question.\n\n<context_priority>\n" +
    contextPriorityInstruction(true) +
    "\n</context_priority>";

  const content = [
    buildPrimarySelectionBlock(args.selectedText),
    resolvedReferencesBlock,
    background ? `<quick_query_background>\n${background}\n</quick_query_background>` : "",
    followups,
    `Question: ${args.question}`,
  ]
    .filter(Boolean)
    .join("\n\n");

  return [
    { role: "system", content: systemText },
    { role: "user", content },
  ];
}
