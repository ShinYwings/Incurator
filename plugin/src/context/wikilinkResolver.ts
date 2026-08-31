/**
 * Following the links a note makes, the way a paper's citations are followed.
 *
 * A markdown note's `[[other note]]` is the exact analogue of a paper's `[12]`:
 * the reader points at something, and answering the question means going and
 * getting it. Papers had a resolver for this since v0.56.0. Notes had none — the
 * plugin only ever WROTE wikilinks, as output locators, and never read one as an
 * input. So "what did I conclude in [[Gaussian Splatting]]?" was answered from a
 * title, or not at all.
 *
 * Pure except for the injected reader, so this file needs no Obsidian API and is
 * testable without a vault. The same shape as `citationResolver` on purpose:
 * extract, then resolve against a source the caller supplies.
 */

/** A wikilink occurrence in the text the reader gave us. */
export interface WikilinkMatch {
  /** The link target as written, before any alias or heading is stripped. */
  raw: string;
  /** The note being pointed at: `[[A|B]]` and `[[A#H]]` both target `A`. */
  target: string;
  /** The heading after `#`, when the link points into a section. */
  heading?: string;
}

/** A wikilink whose note was found and read. */
export interface ResolvedWikilink {
  target: string;
  heading?: string;
  /** The note's path as the reader's vault reports it. */
  path: string;
  /** The text delivered: the named section when there is one, else the note. */
  text: string;
}

/** How much of one linked note to carry. A link is context, not the subject. */
const MAX_LINK_CHARS = 2400;
/** Links followed per turn. Notes routinely link a dozen ways; the prompt cannot. */
const MAX_LINKS = 4;

const WIKILINK = /\[\[([^\]\[|#]+)(?:#([^\]\[|]+))?(?:\|[^\]\[]*)?\]\]/g;

/**
 * Wikilinks in a piece of text, de-duplicated, in the order they appear.
 *
 * Embeds (`![[...]]`) count: Obsidian renders them inline, so the reader sees
 * that content as part of what they are reading and will ask about it as such.
 */
export function extractWikilinks(text: string): WikilinkMatch[] {
  if (!text) return [];
  const seen = new Set<string>();
  const out: WikilinkMatch[] = [];
  WIKILINK.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = WIKILINK.exec(text)) !== null) {
    const target = m[1].trim();
    if (!target) continue;
    const heading = m[2]?.trim() || undefined;
    const key = `${target}#${heading ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ raw: m[0], target, heading });
  }
  return out;
}

/**
 * The slice of a note under one heading, up to the next heading of the same or
 * higher level.
 *
 * A link to `[[Note#Method]]` is a link to that section, and delivering the whole
 * note instead buries the thing the reader pointed at in everything they did not.
 */
export function sectionUnderHeading(markdown: string, heading: string): string {
  const lines = markdown.split("\n");
  const wanted = heading.trim().toLowerCase();
  let start = -1;
  let level = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const m = /^(#{1,6})\s+(.*)$/.exec(lines[i]);
    if (!m) continue;
    if (m[2].trim().toLowerCase() === wanted) {
      start = i;
      level = m[1].length;
      break;
    }
  }
  if (start === -1) return "";
  const body: string[] = [lines[start]];
  for (let i = start + 1; i < lines.length; i += 1) {
    const m = /^(#{1,6})\s+/.exec(lines[i]);
    if (m && m[1].length <= level) break;
    body.push(lines[i]);
  }
  return body.join("\n").trim();
}

/** Reads a linked note. Returns undefined when the link does not resolve. */
export type WikilinkReader = (
  target: string
) => Promise<{ path: string; text: string } | undefined>;

/**
 * Follow the wikilinks in `text`, bounded.
 *
 * Never throws: a link into a note the reader deleted, or one the vault cannot
 * resolve, is simply not returned. A failed link must not cost the turn — that is
 * the failure this whole release is about.
 */
export async function resolveWikilinks(
  text: string,
  read: WikilinkReader
): Promise<ResolvedWikilink[]> {
  const links = extractWikilinks(text).slice(0, MAX_LINKS);
  const out: ResolvedWikilink[] = [];
  for (const link of links) {
    const found = await read(link.target).catch(() => undefined);
    if (!found?.text?.trim()) continue;
    const body = link.heading
      ? sectionUnderHeading(found.text, link.heading) || found.text
      : found.text;
    out.push({
      target: link.target,
      heading: link.heading,
      path: found.path,
      text:
        body.length > MAX_LINK_CHARS
          ? `${body.slice(0, MAX_LINK_CHARS)}\n[...truncated]`
          : body,
    });
  }
  return out;
}

/** Render followed links as a context block, shaped like `<resolved_citations>`. */
export function buildWikilinksBlock(links: ResolvedWikilink[]): string {
  if (links.length === 0) return "";
  const body = links
    .map((l) => {
      const at = l.heading ? `${l.target}#${l.heading}` : l.target;
      return `<linked_note target="${at.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;")}">\n${l.text}\n</linked_note>`;
    })
    .join("\n");
  return (
    `<resolved_wikilinks note="Notes the reader's own text links to. Answer ` +
    `about a linked note from its content here rather than from its title.">\n` +
    `${body}\n</resolved_wikilinks>`
  );
}
