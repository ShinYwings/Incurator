/**
 * Pure formatting helpers for the LLM provider-context block.
 *
 * Extracted from chatSidebar so they can be unit-tested and reused without a
 * sidebar instance. All functions here are stateless — they take their data
 * (and the few needed settings) explicitly and return strings.
 */
import type {
  CuratorContextPack,
  CuratorQueryResult,
  PdfOutlineItem,
  PdfRagHit,
  PdfWindowPage,
} from "../types";
import type { IncuratorHit } from "../agent/incuratorClient";

export function truncateForProviderContext(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n[...truncated]`;
}

export function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

export function formatPdfWindow(pages: PdfWindowPage[]): string {
  return pages
    .map((page) => {
      const text = truncateForProviderContext(page.text, 3000);
      return `### Page ${page.pageNum}\n${text}`;
    })
    .join("\n\n");
}

export function formatOutline(outline: PdfOutlineItem[]): string {
  return outline
    .slice(0, 80)
    .map((item) => {
      const indent = "  ".repeat(Math.max(0, item.level));
      const page = item.pageNum ? ` p.${item.pageNum}` : "";
      return `${indent}- ${item.title}${page}`;
    })
    .join("\n");
}

export function formatRagHits(hits: PdfRagHit[], topK: number): string {
  return hits
    .slice(0, topK)
    .map((hit) => {
      const section = hit.sectionTitle ? ` (${hit.sectionTitle})` : "";
      return `- p.${hit.pageNum}${section} score=${hit.score}: ${truncateForProviderContext(hit.snippet, 700)}`;
    })
    .join("\n");
}

export function formatIncuratorHits(hits: IncuratorHit[]): string {
  return hits
    .map((hit) => {
      const where = [hit.path, hit.pageNum ? `p.${hit.pageNum}` : ""]
        .filter(Boolean)
        .join(" ");
      const label = hit.title || where || "hit";
      const score = typeof hit.score === "number" ? ` score=${hit.score}` : "";
      return `- ${label}${where && label !== where ? ` (${where})` : ""}${score}: ${truncateForProviderContext(hit.snippet, 700)}`;
    })
    .join("\n");
}

const VAULT_LOCATOR_KINDS = new Set(["vault_markdown", "vault_pdf", "promoted_wiki"]);
const USABLE_LOCATOR_STATUSES = new Set(["exact", "fallback_file"]);

function locatorString(locator: Record<string, unknown>, key: string): string {
  return typeof locator[key] === "string" ? locator[key].trim() : "";
}

function safeVaultRelpath(value: string): string | null {
  if (
    !value ||
    value.startsWith("/") ||
    value.includes("\\") ||
    value.includes("\n") ||
    value.includes("\r") ||
    value.includes("[") ||
    value.includes("]") ||
    value.includes("|") ||
    value.includes("#") ||
    /^[a-z]:/i.test(value) ||
    /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ||
    value.split("/").some((part) => part === "..")
  ) {
    return null;
  }
  const wikilinkPath = value.replace(/\.md$/i, "");
  return wikilinkPath && !wikilinkPath.endsWith("/") ? wikilinkPath : null;
}

/**
 * Convert a confirmed ContextService vault locator into an exact Obsidian
 * wikilink target. Ambiguous, external, and unsafe locators fail closed.
 */
export function formatVaultLocatorWikilink(
  locator: Record<string, unknown> | null | undefined
): string | null {
  if (!locator) return null;
  const sourceKind = locatorString(locator, "source_kind");
  const locatorStatus = locatorString(locator, "locator_status");
  if (!VAULT_LOCATOR_KINDS.has(sourceKind) || !USABLE_LOCATOR_STATUSES.has(locatorStatus)) {
    return null;
  }
  if (locatorString(locator, "external_uri")) return null;

  const rawRelpath = locatorString(locator, "relpath");
  if (
    (sourceKind === "vault_pdf" && !/\.pdf$/i.test(rawRelpath)) ||
    (sourceKind !== "vault_pdf" && !/\.md$/i.test(rawRelpath))
  ) {
    return null;
  }
  const relpath = safeVaultRelpath(rawRelpath);
  if (!relpath) return null;
  if (locatorStatus === "fallback_file") return `[[${relpath}]]`;

  if (sourceKind === "vault_pdf") {
    const page = locator.page_number;
    const anchor = typeof page === "number" && Number.isInteger(page) && page > 0
      ? `#page=${page}`
      : "";
    return `[[${relpath}${anchor}]]`;
  }

  const blockId = locatorString(locator, "block_id").replace(/^\^/, "");
  if (blockId && /^[A-Za-z0-9-]+$/.test(blockId)) {
    return `[[${relpath}#^${blockId}]]`;
  }
  const heading = locatorString(locator, "heading").replace(/^#/, "");
  const safeHeading = heading && !/[\r\n[\]|]/.test(heading) ? heading : "";
  return `[[${relpath}${safeHeading ? `#${safeHeading}` : ""}]]`;
}

export function formatCuratorQueryResult(result: CuratorQueryResult, query: string): string {
  const trace = result.trace;
  const attrs = [
    `query="${escapeAttribute(query.slice(0, 120))}"`,
    result.input_language ? `input_language="${escapeAttribute(result.input_language)}"` : null,
    result.english_query ? `english_query="${escapeAttribute(result.english_query.slice(0, 120))}"` : null,
    result.route ? `route="${escapeAttribute(result.route)}"` : null,
    result.trace_id ? `trace="${escapeAttribute(result.trace_id)}"` : null,
  ].filter(Boolean).join(" ");
  let text = `<incurator_query_trace ${attrs}>\n`;
  if (trace) {
    const concepts = trace.matched_concepts.slice(0, 5).join(", ") || "none";
    const sources = trace.source_paths.slice(0, 3).join(", ") || "none";
    text += `concepts=${concepts}; sources=${sources}; latency_ms=${trace.latency_ms}; l3_complete=${trace.l3_complete}`;
  } else {
    text += "No backend evidence pack was returned.";
  }
  text += `\n</incurator_query_trace>`;
  return text;
}

export function formatCuratorContextPack(pack: CuratorContextPack, query: string): string {
  const snapshotId = typeof pack.snapshot?.snapshot_id === "string" ? pack.snapshot.snapshot_id : "";
  const budgetUsed = typeof pack.budget?.used_tokens === "number" ? pack.budget.used_tokens : undefined;
  const budgetLimit = typeof pack.budget?.limit_tokens === "number" ? pack.budget.limit_tokens : undefined;
  const attrs = [
    `query="${escapeAttribute(query.slice(0, 120))}"`,
    pack.route ? `route="${escapeAttribute(pack.route)}"` : null,
    pack.trace_id ? `trace="${escapeAttribute(pack.trace_id)}"` : null,
    pack.pack_id ? `pack="${escapeAttribute(pack.pack_id)}"` : null,
    snapshotId ? `snapshot="${escapeAttribute(snapshotId)}"` : null,
    budgetUsed !== undefined && budgetLimit !== undefined
      ? `budget="${budgetUsed}/${budgetLimit}"`
      : null,
  ].filter(Boolean).join(" ");

  const lines: string[] = [`<incurator_evidence_pack ${attrs}>`];
  const items = pack.items ?? [];
  for (const item of items.slice(0, 12)) {
    const label = [item.kind, item.record_id].filter(Boolean).join(" ");
    const summary = item.summary || item.title || item.claim || label;
    const detail = item.detail || "";
    lines.push(`### ${summary}`);
    if (label) lines.push(`id: ${label}`);
    if (item.truth_state || item.freshness_state) {
      lines.push(
        `state: truth=${item.truth_state || "unknown"} freshness=${item.freshness_state || "unknown"}`
      );
    }
    if (item.source_span_ids?.length) {
      lines.push(`source_spans: ${item.source_span_ids.slice(0, 8).join(", ")}`);
    }
    const vaultLinkTarget = formatVaultLocatorWikilink(item.locator);
    if (vaultLinkTarget) {
      lines.push(`vault_link_target: ${vaultLinkTarget}`);
    }
    if (item.expansion_handle || item.verification_handle) {
      lines.push(
        `handles: expansion=${item.expansion_handle || "none"} verification=${item.verification_handle || "none"}`
      );
    }
    if (detail) lines.push(truncateForProviderContext(detail, 1600));
  }
  if (pack.next?.length) {
    lines.push(`omitted_expansion_handles: ${pack.next.length}`);
  }
  if (pack.warnings?.length) {
    lines.push(`warnings: ${pack.warnings.join("; ")}`);
  }
  lines.push("</incurator_evidence_pack>");
  return lines.join("\n");
}
