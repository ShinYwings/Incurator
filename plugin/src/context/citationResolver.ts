/**
 * Citation resolution, depth 1 (v0.56.0, PLUGIN_SCHEMA §13.7 / plan §4.8).
 *
 * Reading a paper means following its citations. Until now `[8]` was three
 * characters of noise to the assistant: the cross-reference resolver knew
 * sections, figures, equations, and pages, but not "the eighth paper in the
 * bibliography".
 *
 * The hard part is not finding `[8]`. It is knowing that a given `[8]` IS a
 * citation. Bare brackets collide with footnote markers (`[^8]`), markdown
 * reference links (`[text][8]`), and array indices (`arr[8]`) — and a reading
 * assistant that mistakes `buf[8]` for a citation puts noise in front of the
 * model on every code-bearing page.
 *
 * The disambiguator is the bibliography itself. §4.8: **a citation number that
 * does not resolve against a parsed References section is dropped, not rendered
 * as unresolved.** That is a deliberate asymmetry with the rest of the resolver,
 * which reports what it could not find. Here, "not found" is far more likely to
 * mean "not a citation" than "a citation we missed", so silence is the honest
 * output.
 *
 * Everything here is pure so the collision rules are unit-testable without a
 * PDF, a provider, or a UI surface. Fetching the References page lives in the
 * caller.
 */

/** A citation occurrence in the selection, before bibliography matching. */
export interface CitationMatch {
  num: number;
  /** The bracket group this came from, e.g. `[8, 9]` for both 8 and 9. */
  raw: string;
  index: number;
}

/** A citation that matched a bibliography entry. */
export interface ResolvedCitation {
  num: number;
  /** Display label, always the single-number form: `[8]`. */
  label: string;
  /** The bibliography entry text, continuation lines folded in. */
  entry: string;
}

/** Headings that introduce a bibliography. */
const BIBLIOGRAPHY_HEADING = /^[\s#*]*(references|bibliography|works cited)[\s:]*$/im;

/** `[12]` at the start of a line (allowing leading whitespace) starts an entry. */
const ENTRY_START = /^\s*\[(\d{1,3})\]\s*/;

/**
 * A heading that ENDS the bibliography — appendices and named sections that
 * commonly follow it. Without this, "A. Implementation Details" and the
 * bracketed text under it get absorbed as further entries.
 */
const SECTION_AFTER = /^\s*(?:[A-Z]\.\s+[A-Z]|appendix\b|supplementary\b|\d+\.\s+[A-Z])/i;

/**
 * Parse a numbered References/Bibliography section out of page text.
 *
 * Returns an empty map when the text has no bibliography heading. That check is
 * load-bearing: body text is full of `[8]`-shaped citations, and a parser that
 * accepted any page would "find" a bibliography everywhere, destroying the
 * disambiguation this whole module rests on.
 */
export function parseBibliography(text: string): Map<number, string> {
  if (!text) return new Map();
  const lines = text.split(/\r?\n/);
  const headingAt = lines.findIndex((l) => BIBLIOGRAPHY_HEADING.test(l));
  if (headingAt === -1) return new Map();
  return scanEntries(lines.slice(headingAt + 1));
}

/**
 * Parse entries from a page that CONTINUES a bibliography, with no heading.
 *
 * A References section routinely spans pages and the heading appears once.
 * Measured on the motivating paper: p.24 carries the heading and entries 1–28,
 * then p.25 and p.26 carry 35 and 32 more entry-shaped lines with no heading at
 * all. Requiring the heading on every page would have found 28 of ~95.
 *
 * This drops the heading requirement, so it MUST only be applied to a page that
 * actually follows a heading page — {@link collectBibliography} enforces that,
 * and additionally requires the numbering to keep climbing, so an appendix full
 * of bracketed text cannot be absorbed.
 */
export function parseBibliographyContinuation(text: string): Map<number, string> {
  if (!text) return new Map();
  return scanEntries(text.split(/\r?\n/));
}

/**
 * Assemble a bibliography from consecutive page texts, starting at the page
 * that holds the heading.
 *
 * Continuation stops at the first page that adds nothing, and a page whose
 * numbers do not continue upward is rejected outright — that is what keeps an
 * appendix, a numbered figure list, or a changelog from being swallowed.
 */
export function collectBibliography(pageTexts: string[]): Map<number, string> {
  const out = new Map<number, string>();
  let started = false;
  for (const text of pageTexts) {
    const page = started ? parseBibliographyContinuation(text) : parseBibliography(text);
    if (page.size === 0) {
      if (started) break;
      continue;
    }
    if (started) {
      const highestSoFar = Math.max(...out.keys());
      const lowestHere = Math.min(...page.keys());
      // Entries must keep climbing. A page restarting at [1] is a different
      // list, not more of this one.
      if (lowestHere <= highestSoFar) break;
    }
    started = true;
    for (const [num, entry] of page) if (!out.has(num)) out.set(num, entry);
  }
  return out;
}

/** Shared entry scanner. Assumes the heading (if any) is already consumed. */
function scanEntries(lines: string[]): Map<number, string> {
  const out = new Map<number, string>();

  let currentNum: number | null = null;
  let buffer: string[] = [];

  const flush = (): void => {
    if (currentNum !== null && buffer.length) {
      const entry = buffer.join(" ").replace(/\s+/g, " ").trim();
      if (entry) out.set(currentNum, entry);
    }
    currentNum = null;
    buffer = [];
  };

  for (const line of lines) {
    const start = ENTRY_START.exec(line);
    if (start) {
      flush();
      currentNum = Number(start[1]);
      buffer = [line.slice(start[0].length)];
      continue;
    }
    // A section heading ends the bibliography. Only honoured once at least one
    // entry has been seen, so a heading-like line between "References" and the
    // first entry does not abort the parse.
    if (out.size > 0 && currentNum === null && SECTION_AFTER.test(line)) break;
    if (currentNum !== null) {
      if (!line.trim()) continue;
      if (SECTION_AFTER.test(line)) {
        flush();
        break;
      }
      buffer.push(line.trim());
    }
  }
  flush();
  return out;
}

/** Spans of the text that are code, and therefore not prose citations. */
function codeSpans(text: string): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  const patterns = [/```[\s\S]*?```/g, /`[^`\n]*`/g];
  for (const re of patterns) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) spans.push([m.index, m.index + m[0].length]);
  }
  return spans;
}

/** `[8]`, `[8, 9]`, `[1-3]`, `[8,9,11]` — numbers and separators only. */
const BRACKET_GROUP = /\[(\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\]/g;

/**
 * Citation numbers in the selection, with §4.8's collisions filtered out.
 *
 * Ranges expand: `[1-3]` yields 1, 2, 3. Expansion is capped so a typo like
 * `[1-999]` cannot flood the resolver.
 */
export function extractCitationNumbers(selectedText: string): CitationMatch[] {
  if (!selectedText) return [];
  const skip = codeSpans(selectedText);
  const inCode = (i: number): boolean => skip.some(([a, b]) => i >= a && i < b);

  const out: CitationMatch[] = [];
  BRACKET_GROUP.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = BRACKET_GROUP.exec(selectedText)) !== null) {
    const at = m.index;
    if (inCode(at)) continue;

    const before = selectedText[at - 1];
    // `[^8]` — footnote. The caret sits inside the bracket, so the group regex
    // never matches it; this guards the `[text][^8]` shape too.
    if (before === "^") continue;
    // `arr[8]`, `compute()[8]`, and `[text][8]` all bind the bracket to the
    // token before it. A citation follows prose, so the preceding character is
    // whitespace or punctuation. One rule covers the index and the markdown
    // reference-link cases — they are the same shape.
    if (before !== undefined && /[\w)\]]/.test(before)) continue;

    for (const num of expandGroup(m[1])) {
      out.push({ num, raw: m[0], index: at });
    }
  }
  return out;
}

/** Max numbers one bracket group may yield, so `[1-999]` cannot flood. */
const MAX_GROUP_EXPANSION = 24;

function expandGroup(body: string): number[] {
  const out: number[] = [];
  for (const part of body.split(",")) {
    const range = /^\s*(\d{1,3})\s*[–—-]\s*(\d{1,3})\s*$/.exec(part);
    if (range) {
      const from = Number(range[1]);
      const to = Number(range[2]);
      if (to >= from) {
        // Truncate an oversized range; do NOT reject it. Rejecting made
        // `[1-25]` resolve to nothing while the equivalent `[1,2,...,25]`
        // resolved to its first 24 — a survey citing a long range got no
        // citations at all, which is the opposite of the stated intent
        // ("capped so a typo cannot flood the resolver").
        const last = Math.min(to, from + MAX_GROUP_EXPANSION - 1);
        for (let n = from; n <= last; n += 1) out.push(n);
      }
      continue;
    }
    const single = /^\s*(\d{1,3})\s*$/.exec(part);
    if (single) out.push(Number(single[1]));
  }
  return out.slice(0, MAX_GROUP_EXPANSION);
}

/**
 * Citations in the selection that matched a bibliography entry.
 *
 * Unmatched numbers are DROPPED (§4.8). Order follows first appearance;
 * repeats collapse.
 */
export function resolveCitations(
  selectedText: string,
  bibliography: Map<number, string>
): ResolvedCitation[] {
  if (bibliography.size === 0) return [];
  const seen = new Set<number>();
  const out: ResolvedCitation[] = [];
  for (const match of extractCitationNumbers(selectedText)) {
    if (seen.has(match.num)) continue;
    const entry = bibliography.get(match.num);
    if (!entry) continue;
    seen.add(match.num);
    out.push({ num: match.num, label: `[${match.num}]`, entry });
  }
  return out;
}
