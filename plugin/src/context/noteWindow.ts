/**
 * Choosing which part of a long note to carry into a turn.
 *
 * The active markdown note was cut at its first N characters. On a short note
 * that is the whole file and nothing is lost — which is why the truncation
 * looked correct. On a research note the reader has been adding to for a year it
 * means everything after the opening is absent, and a question about the middle
 * is answered from the top or not at all.
 *
 * The same defect shape as the book outline that showed page 1 to a reader on
 * page 400: truncating from the head is wrong whenever the reader is not at the
 * head. The reader's actions — select a passage, ask a question — say where they
 * are, so the window follows them instead.
 *
 * Pure. No Obsidian API, no vault, no retrieval service: a note is small enough
 * that a term overlap over its own sections beats a round-trip.
 */

export interface NoteWindowOptions {
  /** Characters of note text this turn can carry. */
  budget: number;
  /** What the reader typed, when there is one. */
  question?: string;
  /** What the reader highlighted, when there is one. */
  selection?: string;
}

interface Section {
  index: number;
  heading: string;
  text: string;
}

/** Split on ATX headings; text before the first heading is section zero. */
function sections(markdown: string): Section[] {
  const lines = markdown.split("\n");
  const out: Section[] = [];
  let heading = "";
  let buf: string[] = [];
  const flush = () => {
    const text = buf.join("\n");
    if (text.trim() || heading) {
      out.push({ index: out.length, heading, text });
    }
  };
  for (const line of lines) {
    if (/^#{1,6}\s+/.test(line)) {
      flush();
      heading = line;
      buf = [line];
    } else {
      buf.push(line);
    }
  }
  flush();
  return out;
}

/** Content words, lowercased. Short tokens carry no signal and cost matches. */
function terms(text: string): Set<string> {
  return new Set(
    (text.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? []).filter(
      (w) => !STOP.has(w)
    )
  );
}

const STOP = new Set([
  "the", "and", "for", "was", "with", "that", "this", "what", "did", "how",
  "why", "about", "have", "has", "are", "were", "from", "into", "not", "but",
  "you", "your", "its", "it's", "write", "wrote", "said", "say",
]);

/**
 * The slice of `markdown` most likely to answer the reader, within `budget`.
 *
 * Sections are scored by term overlap with the selection and the question, the
 * selection weighted higher because it is what the reader is literally pointing
 * at. Chosen sections are emitted in DOCUMENT ORDER with an explicit marker where
 * text was dropped — a gap the model reads as the end of the note is worse than a
 * gap it can see.
 */
export function selectNoteWindow(
  markdown: string,
  opts: NoteWindowOptions
): string {
  if (!markdown) return "";
  if (markdown.length <= opts.budget) return markdown;

  const secs = sections(markdown);
  if (secs.length <= 1) {
    return `${markdown.slice(0, opts.budget)}\n[...truncated]`;
  }

  const qTerms = terms(opts.question ?? "");
  const sTerms = terms(opts.selection ?? "");
  const scored = secs.map((s) => {
    const t = terms(`${s.heading}\n${s.text}`);
    let score = 0;
    for (const w of qTerms) if (t.has(w)) score += 1;
    for (const w of sTerms) if (t.has(w)) score += 2;
    // The literal selection beating a term match: the reader is inside this one.
    if (opts.selection && s.text.includes(opts.selection.slice(0, 80))) {
      score += 50;
    }
    return { s, score };
  });

  const ranked = [...scored].sort((a, b) => b.score - a.score);
  const keep = new Set<number>();
  const windowed = new Map<number, string>();
  let used = 0;
  for (const { s, score } of ranked) {
    if (score === 0) continue;
    if (used + s.text.length <= opts.budget) {
      keep.add(s.index);
      used += s.text.length;
      continue;
    }
    // The section is bigger than the budget. That is the COMMON case, not an
    // edge one: a note with few headings has enormous sections, and dropping it
    // whole would send us back to the head — the exact failure being fixed. Take
    // a window inside it, around the best match.
    const room = opts.budget - used;
    if (room < 200 || windowed.size > 0) continue;
    const inner = windowAround(s.text, qTerms, sTerms, opts.selection, room);
    if (!inner) continue;
    keep.add(s.index);
    windowed.set(s.index, inner);
    used += inner.length;
  }
  // Nothing matched, or nothing fit: fall back to the head, which is at least
  // where a note states what it is about.
  if (keep.size === 0) {
    return `${markdown.slice(0, opts.budget)}\n[...truncated]`;
  }

  const parts: string[] = [];
  let gap = false;
  for (const s of secs) {
    if (keep.has(s.index)) {
      if (gap) parts.push("[... unrelated sections omitted ...]");
      parts.push(windowed.get(s.index) ?? s.text);
      gap = false;
    } else {
      gap = true;
    }
  }
  if (gap) parts.push("[... later sections omitted ...]");
  return parts.join("\n").trim();
}

/**
 * A slice of one oversized section, centred on where the reader's words land.
 *
 * Returns "" when nothing in the section matches, so the caller can move on
 * rather than emit an arbitrary slab of the middle.
 */
function windowAround(
  text: string,
  qTerms: Set<string>,
  sTerms: Set<string>,
  selection: string | undefined,
  room: number
): string {
  const lower = text.toLowerCase();
  let at = -1;
  if (selection) at = text.indexOf(selection.slice(0, 80));
  if (at === -1) {
    for (const w of [...sTerms, ...qTerms]) {
      const i = lower.indexOf(w);
      if (i !== -1) {
        at = i;
        break;
      }
    }
  }
  if (at === -1) return "";
  const half = Math.floor(room / 2);
  const start = Math.max(0, at - half);
  const end = Math.min(text.length, at + half);
  const head = start > 0 ? "[... earlier in this section omitted ...]\n" : "";
  const tail = end < text.length ? "\n[... rest of this section omitted ...]" : "";
  return `${head}${text.slice(start, end).trim()}${tail}`;
}
