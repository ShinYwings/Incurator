/**
 * Parse the ordered list of math formulas from a block of markdown SOURCE.
 *
 * Reading-view MathJax (CHTML) keeps NO source in the rendered DOM — no
 * `annotation[x-tex]`, no assistive MathML, no data attribute (verified against a
 * live vault). So to recover `$...$` / `$$...$$` for a reading-view copy, a
 * markdown post-processor reads each block's source via `getSectionInfo`, parses
 * the formulas here in document order, and stamps them onto the rendered `.math`
 * elements as `data-tex`. The Nth formula maps to the Nth rendered math span.
 *
 * Correctness guard (enforced by the caller, not here): the caller only stamps
 * when `parseMathSources(src).length` EXACTLY equals the number of rendered math
 * elements in the block. So an over- or under-count (e.g. a `$5` price the parser
 * mistakes for math, or an exotic construct) can never produce a WRONG stamp — it
 * just disables the feature for that one block (falls back to today's behavior).
 * That lets this parser stay pragmatic rather than a full CommonMark implementation.
 */

export interface MathSource {
  /** LaTeX source, trimmed, without the `$`/`$$` delimiters. */
  tex: string;
  /** true for block `$$...$$`, false for inline `$...$`. */
  display: boolean;
}

function isLineStart(src: string, i: number): boolean {
  return i === 0 || src[i - 1] === "\n";
}

/** If a fenced code block (``` or ~~~, length ≥ 3) opens at `i` (line start),
 * return the index just past its closing fence (or end of string). Else -1. */
function skipFencedCode(src: string, i: number): number {
  if (!isLineStart(src, i)) return -1;
  const ch = src[i];
  if (ch !== "`" && ch !== "~") return -1;
  let run = 0;
  while (src[i + run] === ch) run++;
  if (run < 3) return -1;
  const fence = ch.repeat(run);
  // Find a closing fence (same char, ≥ run) at the start of a later line.
  let j = src.indexOf("\n", i);
  while (j !== -1) {
    const lineStart = j + 1;
    let k = lineStart;
    while (src[k] === " " || src[k] === "\t") k++;
    if (src.startsWith(fence, k)) {
      const lineEnd = src.indexOf("\n", k);
      return lineEnd === -1 ? src.length : lineEnd + 1;
    }
    j = src.indexOf("\n", lineStart);
  }
  return src.length; // unterminated fence → consume the rest
}

/** Skip an inline code span starting at `i` (one or more backticks). Returns the
 * index just past the matching closing run, or -1 if `i` is not a code span. */
function skipInlineCode(src: string, i: number): number {
  if (src[i] !== "`") return -1;
  let run = 0;
  while (src[i + run] === "`") run++;
  const close = src.indexOf("`".repeat(run), i + run);
  if (close === -1) return -1; // no closing run → not a code span
  return close + run;
}

function isSpace(c: string | undefined): boolean {
  return c === " " || c === "\t" || c === "\n" || c === undefined;
}

export function parseMathSources(src: string): MathSource[] {
  const out: MathSource[] = [];
  const n = src.length;
  let i = 0;
  while (i < n) {
    // Fenced code block (line-start ``` / ~~~) — skip its entire content.
    const fenceEnd = skipFencedCode(src, i);
    if (fenceEnd !== -1) {
      i = fenceEnd;
      continue;
    }
    // Inline code span — skip.
    if (src[i] === "`") {
      const codeEnd = skipInlineCode(src, i);
      if (codeEnd !== -1) {
        i = codeEnd;
        continue;
      }
    }
    // Escaped dollar — not a delimiter.
    if (src[i] === "\\" && src[i + 1] === "$") {
      i += 2;
      continue;
    }
    // Block math $$...$$
    if (src[i] === "$" && src[i + 1] === "$") {
      const end = src.indexOf("$$", i + 2);
      if (end === -1) {
        i += 2;
        continue;
      }
      out.push({ tex: src.slice(i + 2, end).trim(), display: true });
      i = end + 2;
      continue;
    }
    // Inline math $...$ — Obsidian requires no whitespace adjacent to either
    // delimiter (so `$5 and $10` currency is not treated as math), single line.
    if (src[i] === "$" && !isSpace(src[i + 1])) {
      let j = i + 1;
      let found = -1;
      while (j < n) {
        if (src[j] === "\\") {
          j += 2;
          continue;
        }
        if (src[j] === "\n") break; // inline math is single-line
        if (src[j] === "$") {
          found = j;
          break;
        }
        j++;
      }
      if (found !== -1 && !isSpace(src[found - 1])) {
        out.push({ tex: src.slice(i + 1, found).trim(), display: false });
        i = found + 1;
        continue;
      }
    }
    i++;
  }
  return out;
}
