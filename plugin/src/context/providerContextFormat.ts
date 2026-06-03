/**
 * Pure formatting helpers for the LLM provider-context block.
 *
 * Extracted from chatSidebar so they can be unit-tested and reused without a
 * sidebar instance. All functions here are stateless — they take their data
 * (and the few needed settings) explicitly and return strings.
 */
import type {
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

export function formatCuratorQueryResult(result: CuratorQueryResult, query: string): string {
  const trace = result.trace;
  const attrs = [
    `query="${escapeAttribute(query.slice(0, 120))}"`,
    result.input_language ? `input_language="${escapeAttribute(result.input_language)}"` : null,
    result.english_query ? `english_query="${escapeAttribute(result.english_query.slice(0, 120))}"` : null,
    result.cache_hit ? `cache="hit"` : null,
    result.exhibition_id ? `exhibition="${result.exhibition_id}"` : null,
  ].filter(Boolean).join(" ");
  let text = `<incurator_answer ${attrs}>\n`;
  text += truncateForProviderContext(result.answer ?? "", 4000);
  if (trace) {
    const concepts = trace.matched_concepts.slice(0, 5).join(", ") || "none";
    const sources = trace.source_paths.slice(0, 3).join(", ") || "none";
    text += `\n\n<!-- concepts: ${concepts} | sources: ${sources} | latency: ${trace.latency_ms}ms | l3_complete: ${trace.l3_complete} -->`;
  }
  text += `\n</incurator_answer>`;
  return text;
}
