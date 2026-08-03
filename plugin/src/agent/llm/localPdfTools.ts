/**
 * Local PDF reader tools (v0.41.0) — see PLUGIN_SCHEMA §13.7.
 *
 * The reading assistant already receives the document outline WITH page numbers
 * (`formatOutline`), so it can reason "that result is in Appendix 4, around
 * p.617" — but before v0.41.0 it had no way to obtain that page and could only
 * tell the user to navigate there. These tools are the missing actuator.
 *
 * They are NOT MCP tools: they are executed by the plugin against the PDF the
 * user already has open, never reach the filesystem, the vault, the Zotero
 * library, or a shell, and are never registered with an MCP server. The
 * popover's zero-MCP guarantee (§13.5) is therefore unchanged.
 *
 * Everything here is pure so the security-relevant gating and bounds are unit
 * testable without a provider, a PDF, or a UI surface. Execution lives behind
 * the {@link LocalPdfToolRunner} interface implemented in `main.ts`.
 */
import type { PdfRagHit } from "../../types";

export const LOCAL_PDF_TOOL_NAMES = ["fetch_pdf_page", "search_pdf_anchor"] as const;
export type LocalPdfToolName = (typeof LOCAL_PDF_TOOL_NAMES)[number];

/** Default number of anchor-search hits returned to the model. */
export const LOCAL_PDF_SEARCH_TOP_K = 5;

/**
 * Total pages a single user request may fetch across all tool rounds. Distinct
 * from the tool loop's recursion limit: one round may request several pages.
 */
export const LOCAL_PDF_FETCH_BUDGET = 6;

/**
 * Whether the document's outline is known to exist. "unknown" (not yet parsed)
 * is treated as "present" so `search_pdf_anchor` is withheld rather than
 * wrongly exposed on a document that does have a map.
 */
export type OutlineState = "present" | "absent" | "unknown";

export interface LocalPdfToolContext {
  hasActivePdf: boolean;
  /** Physical page count. Absent => no fetch tool may be exposed at all. */
  pageCount?: number;
  currentPage?: number;
  /** Stable identity of the document the tools are scoped to. */
  documentId?: string;
  outlineState: OutlineState;
}

export interface ExposedLocalTool {
  type: "function";
  function: {
    name: LocalPdfToolName;
    description: string;
    parameters: Record<string, unknown>;
  };
}

export type LocalPdfToolErrorCode =
  | "unknown_tool"
  | "invalid_arguments"
  | "out_of_range"
  | "unavailable"
  | "budget_exhausted"
  | "document_changed"
  | "not_found";

export type LocalPdfToolRequest =
  | { kind: "fetch_page"; pageNum: number }
  | { kind: "search_anchor"; query: string };

export interface LocalPdfToolError {
  kind: "error";
  code: LocalPdfToolErrorCode;
  message: string;
}

export type LocalPdfToolParse = LocalPdfToolRequest | LocalPdfToolError;

/** Execution surface. The only implementation wraps the existing page fetch. */
export interface LocalPdfToolRunner {
  describeContext(): LocalPdfToolContext;
  fetchPage(pageNum: number): Promise<string | undefined>;
  searchAnchor(query: string, topK: number): Promise<PdfRagHit[]>;
}

function error(code: LocalPdfToolErrorCode, message: string): LocalPdfToolError {
  return { kind: "error", code, message };
}

export function isLocalPdfToolName(name: string): name is LocalPdfToolName {
  return (LOCAL_PDF_TOOL_NAMES as readonly string[]).includes(name);
}

/**
 * Whether the context can safely bound a page fetch. Fail closed: without an
 * active document, a positive page count, and a stable identity, an unbounded
 * or unscoped fetch tool is strictly worse than no tool at all.
 */
function canFetch(ctx: LocalPdfToolContext): boolean {
  return (
    ctx.hasActivePdf &&
    typeof ctx.pageCount === "number" &&
    ctx.pageCount > 0 &&
    typeof ctx.documentId === "string" &&
    ctx.documentId.length > 0
  );
}

/** Anchor search exists only as the no-map fallback for outline-less documents. */
function canSearch(ctx: LocalPdfToolContext): boolean {
  return canFetch(ctx) && ctx.outlineState === "absent";
}

export function buildLocalPdfTools(ctx: LocalPdfToolContext): ExposedLocalTool[] {
  if (!canFetch(ctx)) return [];
  const pageCount = ctx.pageCount as number;
  const tools: ExposedLocalTool[] = [
    {
      type: "function",
      function: {
        name: "fetch_pdf_page",
        description:
          `Read one page of the PDF the user currently has open (1-${pageCount}). ` +
          "Use this to follow a cross-reference — a theorem, proof, equation, " +
          "figure, or section the visible text points to — instead of telling the " +
          "user to navigate there. Page numbers are physical PDF pages; the " +
          "document outline in the context lists them.",
        parameters: {
          type: "object",
          properties: {
            page_number: {
              type: "integer",
              minimum: 1,
              maximum: pageCount,
              description: "Physical PDF page to read.",
            },
          },
          required: ["page_number"],
        },
      },
    },
  ];

  if (canSearch(ctx)) {
    tools.push({
      type: "function",
      function: {
        name: "search_pdf_anchor",
        description:
          "Search the pages of this PDF that have already been read. This " +
          "document has no embedded outline, so use this to locate a named " +
          "target before fetching its page.",
        parameters: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Text to look for, e.g. a theorem name or heading.",
            },
          },
          required: ["query"],
        },
      },
    });
  }

  return tools;
}

export function parseLocalPdfToolCall(
  name: string,
  rawArgs: string,
  ctx: LocalPdfToolContext
): LocalPdfToolParse {
  if (!isLocalPdfToolName(name)) {
    return error("unknown_tool", `Unknown local tool: ${name}`);
  }

  let args: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(rawArgs || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return error("invalid_arguments", "Arguments must be a JSON object.");
    }
    args = parsed as Record<string, unknown>;
  } catch {
    return error("invalid_arguments", `Arguments were not valid JSON: ${rawArgs}`);
  }

  if (name === "fetch_pdf_page") {
    if (!canFetch(ctx)) {
      return error(
        "unavailable",
        "No PDF page reader is available for this request (no open document, " +
          "unknown page count, or unstable document identity)."
      );
    }
    const raw = args.page_number;
    if (typeof raw !== "number" || !Number.isFinite(raw)) {
      return error("invalid_arguments", "page_number must be a number.");
    }
    if (!Number.isInteger(raw)) {
      return error("invalid_arguments", "page_number must be an integer.");
    }
    const pageCount = ctx.pageCount as number;
    if (raw < 1 || raw > pageCount) {
      return error(
        "out_of_range",
        `page_number must be between 1 and ${pageCount}; got ${raw}.`
      );
    }
    return { kind: "fetch_page", pageNum: raw };
  }

  if (!canSearch(ctx)) {
    return error(
      "unavailable",
      "Anchor search is not available for this document; use the document " +
        "outline in the context to pick a page and fetch it."
    );
  }
  const query = args.query;
  if (typeof query !== "string" || query.trim().length === 0) {
    return error("invalid_arguments", "query must be a non-empty string.");
  }
  return { kind: "search_anchor", query: query.trim() };
}

/** Render an anchor-search result set as compact tool output. */
export function formatAnchorHits(hits: PdfRagHit[]): string {
  if (hits.length === 0) return "No matching pages among the pages read so far.";
  return hits
    .map((hit) => `p.${hit.pageNum} (score ${hit.score}): ${hit.snippet}`)
    .join("\n");
}
