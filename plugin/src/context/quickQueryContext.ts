import {
  escapeAttribute,
  formatOutline,
  formatPdfWindow,
  truncateForProviderContext,
} from "./providerContextFormat";
import { contextPriorityInstruction } from "./chatContextPriority";
import { resolveSelectionReferencesBlock } from "./pdfReferenceContext";
import { selectNoteWindow } from "./noteWindow";
import { fitTurnBudget } from "./turnBudget";
import {
  boundaryConstraints,
  buildRecencyAnchor,
  POPOVER_PROFILE,
  surfaceToolReality,
} from "./promptRegistry";
import type { ActiveContext, ContextRef, LLMMessage } from "../types";

export interface QuickQueryTurn {
  question: string;
  answer: string;
}

export interface QuickQueryMessageArgs {
  selectedText: string;
  question: string;
  /**
   * The provider this turn will actually run on.
   *
   * Decides whether the prompt may promise the local page reader, because that
   * reader is only injected on the API path. Omitted means CLI — the restrictive
   * wording — so a caller that forgets cannot resurrect the promise of a tool
   * that is not actually there.
   */
  provider?: string;
  activeContext?: ActiveContext;
  previousTurns?: QuickQueryTurn[];
  maxBackgroundLength?: number;
  /** Pre-resolved cross-references block (from async resolution with page fetch).
   *  When provided, skips the synchronous inline resolution so the async result is used. */
  resolvedReferencesBlock?: string;
  /**
   * Notes the reader's own text links to, already followed and read.
   *
   * A note's `[[link]]` is a paper's `[12]`. Papers have had a citation resolver
   * since v0.56.0; notes had none, so a question about a linked note was answered
   * from its title. Resolved BEFORE the turn like every other pointer, because
   * the CLI path injects no tools and cannot go and get it mid-answer.
   */
  resolvedWikilinksBlock?: string;
  /** Pinned context refs from the sidechat (purple pins). Injected as read-only
   *  background so the popover can search/use them without changing tool policy. */
  pinnedContextRefs?: ContextRef[];
  /** Vault-wide evidence for the question, resolved BEFORE the turn (§4.2) and
   *  formatted by the same `formatCuratorContextPack` the sidechat uses.
   *
   *  Duty 2 — "remind me what I wrote" — needs the reader's OTHER notes, and the
   *  popover had no vault retrieval on its path at all: it assembled from the
   *  selection, the current file's outline, pinned refs and citation resolution,
   *  and `IncuratorClient.curatorQuery` had zero callers anywhere. Measured live:
   *  asking "이 제약이 무슨 뜻이야? 내가 쓴 다른 노트 중 관련된 게 있어?" surfaced
   *  only sections of the SAME note, while the vault held 21 published sources
   *  matching the topic. Pre-resolved here rather than fetched by the model:
   *  §2 forbids giving the popover tools, and §4.2 forbids making it chase. */
  vaultEvidenceBlock?: string;
}

const DEFAULT_BACKGROUND_LIMIT = 12000;
/**
 * Characters one popover turn may spend on everything the reader did not type.
 *
 * Generous on purpose — the point is not frugality, it is that a ceiling exists
 * at all. Without one the per-block caps were additive and the selection had no
 * share of the result.
 */
const DEFAULT_TURN_BUDGET = 36000;
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
  options: {
    selectedText?: string;
    question?: string;
    maxBackgroundLength?: number;
  } = {}
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
        // Windowed on the reader, not cut at the head. A note they have been
        // adding to for a year loses everything after its opening otherwise, and
        // a question about the middle is answered from the top or not at all.
        `${selectNoteWindow(activeCtx.fileContent, {
          budget: Math.floor(maxLength / 2),
          question: options.question,
          selection: options.selectedText,
        })}\n` +
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
        `<document_outline document="${escapeAttribute(doc)}">\n${formatOutline(pdf.outline, pdf.pageNum)}\n</document_outline>`
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

const PINNED_SOURCE_LIMIT = 6000;

/**
 * Format sidechat pinned context refs as a background block for the popover.
 * Each pinned source is wrapped with its label so the LLM can cite it.
 */
export function buildPinnedSourcesBlock(refs: ContextRef[] | undefined): string {
  const pinned = (refs ?? []).filter((r) => r.isPinned && r.content?.trim());
  if (pinned.length === 0) return "";
  const entries = pinned.map((ref) => {
    const label = escapeAttribute(ref.label || ref.filePath || "pinned source");
    const content = truncateForProviderContext(ref.content.trim(), Math.floor(PINNED_SOURCE_LIMIT / pinned.length));
    return `<pinned_source label="${label}">\n${content}\n</pinned_source>`;
  });
  return `<pinned_sources>\n${entries.join("\n")}\n</pinned_sources>`;
}

/** Retrieval query for the popover's pre-turn vault fetch.
 *
 * The question alone is not enough, and shipping it that way made the fix look
 * like it had failed. A popover question is usually deictic — "이 제약이 무슨
 * 뜻이야?", "what does this mean?" — so it carries no topical term at all, and
 * the topic lives in the SELECTION. Measured against the live vault: the question
 * alone returned **0 evidence items from 0 sources**; the selection prepended to
 * it returned **35 items across 9 sources**.
 *
 * The selection is capped because a drag can span a page: retrieval needs the
 * subject, not the whole passage. */
export const QUICK_QUERY_RETRIEVAL_SELECTION_CHARS = 600;

export function buildQuickQueryRetrievalQuery(
  selectedText: string,
  question: string
): string {
  const selection = (selectedText || "").trim().slice(0, QUICK_QUERY_RETRIEVAL_SELECTION_CHARS);
  return [selection, (question || "").trim()].filter(Boolean).join("\n\n");
}

export function buildQuickQueryMessages(args: QuickQueryMessageArgs): LLMMessage[] {
  // Fail closed: no provider named means the restrictive wording. Promising a
  // page reader that is not injected is what sent the model looking for a URL
  // tool it was not allowed to use.
  const reality = surfaceToolReality(args.provider ?? "");
  const background = buildActiveBackgroundContext(args.activeContext, {
    selectedText: args.selectedText,
    question: args.question,
    maxBackgroundLength: args.maxBackgroundLength,
  });
  const followups = buildEphemeralFollowupContext(args.previousTurns);

  const resolvedReferencesBlock =
    args.resolvedReferencesBlock ??
    resolveSelectionReferencesBlock(args.selectedText, args.activeContext?.pdfPage);

  const pinnedBlock = buildPinnedSourcesBlock(args.pinnedContextRefs);

  const systemText =
    "You are a reading assistant embedded in Obsidian. The user selected a " +
    "passage while reading and asks a quick question about it. Answer " +
    "concisely and directly, in the same language as the question. The " +
    "primary selected passage is the main focus. Use current page, document " +
    "outline/ToC, pinned sources from the sidebar, and prior quick-query " +
    "turns from the same popover as background to resolve references, " +
    "equations, and citations. If pinned sources (wrapped in " +
    "<pinned_sources>) are provided, actively use them to enrich your " +
    "answer. When <vault_evidence> is provided it holds passages from the " +
    "reader's OWN vault — their earlier notes and the sources they have " +
    "ingested. Surface what bears on the question and name the note it came " +
    "from, so they can return to what they already wrote. When the " +
    "selection is itself a POINTER (e.g. \"see Section A4.2\", \"Figure 19.1\", " +
    "\"Eq. (3)\"), answer about the referenced TARGET shown in " +
    "<resolved_cross_references>, using the selection only to identify which " +
    "reference to follow — do not explain the visible page. " +
    "Positional or locational phrases in the question (e.g. \"위쪽\", \"아래쪽\", " +
    "\"앞부분\", \"뒷부분\", \"상단\", \"하단\", \"top\", \"above\", \"beginning\", " +
    "\"start\", \"end\", \"below\", \"later in the document\") refer to positions " +
    "WITHIN the current document's content and outline, NOT to the file system " +
    "or surrounding folders. " +
    boundaryConstraints(POPOVER_PROFILE, reality) +
    " When asked about a region of the document, summarize or quote that " +
    "region's actual content. Do not add " +
    "preamble, sign-off, or restate the question.\n\n<context_priority>\n" +
    contextPriorityInstruction(
      true,
      args.activeContext?.pdfPage
        ? "pdf"
        : args.activeContext?.viewType === "markdown"
          ? "markdown"
          : "none"
    ) +
    "\n</context_priority>";

  // Fitted against ONE budget, in priority order. Every block used to carry its
  // own independent cap and know about no other, so stacking them near their
  // limits put a measured 102-character selection inside a 53,000-character turn
  // — 0.19%, outweighed by the vault evidence alone by about 206x. A popover
  // question is usually deictic, so the selection IS the subject and is short by
  // construction; nothing shrank the supporting material to match.
  //
  // Priority is by how directly the reader asked for the thing: what they
  // highlighted, then what they pointed at, then the document around it, then
  // what the vault volunteered without being asked.
  const content = fitTurnBudget(
    [
      {
        text: buildPrimarySelectionBlock(args.selectedText),
        priority: 0,
        pinned: true,
        label: "selection",
      },
      { text: resolvedReferencesBlock, priority: 1, label: "resolved references" },
      { text: args.resolvedWikilinksBlock ?? "", priority: 1, label: "linked notes" },
      {
        text: background
          ? `<quick_query_background>\n${background}\n</quick_query_background>`
          : "",
        priority: 2,
        label: "the open document",
      },
      { text: pinnedBlock, priority: 3, label: "pinned sources" },
      { text: args.vaultEvidenceBlock ?? "", priority: 4, label: "vault evidence" },
      { text: followups, priority: 5, label: "earlier turns" },
      {
        text: `Question: ${args.question}`,
        priority: 0,
        pinned: true,
        label: "question",
      },
      {
        // Emitted LAST so the read-only / selection-focus invariants sit at the
        // position of strongest attention, and pinned so a tight budget can never
        // be the thing that removes them.
        text: buildRecencyAnchor(POPOVER_PROFILE, {
          hasPrimarySelection: true,
          reality,
        }),
        priority: 0,
        pinned: true,
        label: "invariants",
      },
    ],
    DEFAULT_TURN_BUDGET
  ).join("\n\n");

  return [
    { role: "system", content: systemText },
    { role: "user", content },
  ];
}
