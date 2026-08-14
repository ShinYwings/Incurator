/**
 * Provenance, assembled from what was resolved (v0.56.0, PLUGIN_SCHEMA §13.9).
 *
 * The reader needs to know which part of an answer came from their document and
 * which from the model's background knowledge. There are two ways to produce
 * that signal and only one of them works.
 *
 * The rejected design scanned the model's rendered answer for `[[wikilink]]`
 * citations and warned when none appeared. Measured: `quickQueryContext.ts`
 * contains **zero** occurrences of `[[` — the popover model is never told
 * wikilinks exist, so the check would have reported "no citation" on every
 * popover answer ever produced. A signal that is wrong by construction is worse
 * than no signal, because the reader learns to ignore it.
 *
 * So provenance is built from the resolution record the plugin already holds:
 * which rung answered, which page it read, which bibliography entry a citation
 * matched. That record is ground truth. Model output is a claim about it.
 *
 * This module is pure. It produces a value; rendering is the surface's job, and
 * nothing here reaches the prompt — provenance is UI state, so it stays outside
 * §13.8's prompt budget and cannot be argued away by a model mid-turn.
 */
import type { ResolvedReference } from "./crossReferenceResolver";
import type { ResolvedCitation } from "./citationResolver";

export type ProvenanceOrigin =
  | "page"
  | "outline"
  | "caption"
  | "search"
  | "bibliography"
  | "unresolved";

export interface ProvenanceItem {
  /** What the reader asked about: "Eq. (29)", "[8]", "Section A4.2". */
  label: string;
  origin: ProvenanceOrigin;
  /** Short human phrase: "p.11", "bibliography", "not retrieved". */
  detail: string;
}

export interface ProvenanceRecord {
  items: ProvenanceItem[];
  /** True when at least one pointer could not be retrieved. */
  hasUnresolved: boolean;
}

/**
 * How each resolver rung is described to the reader.
 *
 * `bm25-*` becomes "found by search" rather than naming the algorithm: the
 * reader is being told how much to trust the answer, and "BM25" answers a
 * question they did not ask.
 */
const ORIGIN_BY_METHOD: Record<string, ProvenanceOrigin> = {
  "explicit-page": "page",
  "outline-section": "outline",
  "caption-index": "caption",
  "bm25-object": "search",
  "bm25-section": "search",
  unresolved: "unresolved",
};

function detailFor(ref: ResolvedReference): string {
  if (ref.method === "unresolved") return "not retrieved";
  const page = typeof ref.targetPage === "number" ? `p.${ref.targetPage}` : "";
  const section = ref.sectionTitle ? `“${ref.sectionTitle}”` : "";
  const how =
    ref.method === "bm25-object" || ref.method === "bm25-section"
      ? "found by search"
      : "";
  return [page, section, how].filter(Boolean).join(" · ") || "resolved";
}

/**
 * Build the provenance record for one turn.
 *
 * References consumed by a sibling are omitted: they were folded into another
 * entry's text and listing them again would show the reader two sources for one
 * lookup.
 */
export function buildProvenance(
  resolved: ResolvedReference[],
  citations: ResolvedCitation[] = []
): ProvenanceRecord {
  const items: ProvenanceItem[] = [];

  for (const ref of resolved) {
    if (ref.consumedBySibling) continue;
    items.push({
      label: ref.label,
      origin: ORIGIN_BY_METHOD[ref.method] ?? "search",
      detail: detailFor(ref),
    });
  }

  for (const cite of citations) {
    items.push({
      label: cite.label,
      origin: "bibliography",
      detail: firstAuthorAndYear(cite.entry) || "bibliography",
    });
  }

  return { items, hasUnresolved: items.some((i) => i.origin === "unresolved") };
}

/**
 * Condense a bibliography line to something a chip can hold.
 *
 * "S. Liu, Y. Yu, R. Pautrat, M. Pollefeys, and V. Larsson. 3D line mapping
 * revisited. In CVPR, 2023." → "Liu et al., 2023".
 */
function firstAuthorAndYear(entry: string): string {
  const year = /\b(19|20)\d{2}\b/.exec(entry)?.[0];

  // The author list ends at the first period that is NOT an initial's — an
  // initial's period follows a single capital. Splitting on any period instead
  // truncates "S. Liu" to "S", and splitting on any comma truncates the list
  // before the "and V. Larsson" that makes it multi-author.
  const authorEnd = /(?<![A-Z])\.\s/.exec(entry);
  const authors = authorEnd ? entry.slice(0, authorEnd.index) : entry;

  // The surname is the LAST word of the FIRST author, not the first word of
  // the list. Real bibliographies mix both conventions — this paper writes
  // "Hichem Abdellali, Robert Frohlich, ..." in full while others write
  // "S. Liu, Y. Yu, ...". Taking the first word yields the given name
  // ("Hichem") on the first convention and the initial ("S") on the second;
  // taking the last word of the first author yields the surname on both.
  const firstAuthor = authors.split(/,|\sand\s/)[0] ?? "";
  const words = firstAuthor.match(/[A-Za-z][A-Za-z'\u2019.-]*/g) ?? [];
  const surname = words
    .filter((w) => !/^[A-Za-z][.-]*$/.test(w) && !/^[A-Za-z]\.[A-Za-z]?\.?$/.test(w))
    .pop()
    ?.replace(/\.+$/, "");
  if (!surname) return year ?? "";

  const many = /,|\band\b/.test(authors);
  return [`${surname}${many ? " et al." : ""}`, year].filter(Boolean).join(", ");
}

/**
 * One-line summary for a compact surface.
 *
 * Returns "" when nothing was resolved — the reader gets no chip rather than an
 * empty one, and an ordinary question that needed no lookup shows no chrome.
 */
export function summarizeProvenance(record: ProvenanceRecord): string {
  if (record.items.length === 0) return "";
  return record.items.map((i) => `${i.label} — ${i.detail}`).join(" · ");
}
