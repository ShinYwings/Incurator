/**
 * Unified, ambiguity-safe locator for `ai-agent-edit` SEARCH blocks.
 *
 * The agent's SEARCH text frequently drifts from the file by leading/trailing
 * whitespace or indentation level (the LLM re-indents, or normalizes). The old
 * apply paths used exact `indexOf`/`includes`/`split`, so any drift failed with
 * "could not find the exact SEARCH block" and no diff ever rendered.
 *
 * This matcher tries progressively looser strategies, but **never guesses**:
 * when two or more spans are plausible it returns `null` (the caller then shows
 * the honest "couldn't find" message) — silence is safer than a wrong edit.
 *
 * It always returns the REAL character span in `haystack`, so callers splice the
 * file's own text and preserve its exact whitespace; the normalized forms are
 * used only for comparison.
 */
export interface MatchResult {
  /** Inclusive start offset into `haystack`. */
  start: number;
  /** Exclusive end offset into `haystack`. */
  end: number;
  /** `haystack.slice(start, end)` — the original text to be replaced. */
  matchedText: string;
  strategy: "exact" | "line-trim" | "anchored";
}

export function findSearchBlock(haystack: string, search: string): MatchResult | null {
  if (search.length === 0) return null;

  // ── Tier 0 — exact (first occurrence; preserves legacy behavior) ──────────
  const exactIdx = haystack.indexOf(search);
  if (exactIdx !== -1) {
    return {
      start: exactIdx,
      end: exactIdx + search.length,
      matchedText: search,
      strategy: "exact",
    };
  }

  const fileLines = haystack.split("\n");
  const searchLines = search.split("\n");

  // Character offset where each file line begins (+1 per stripped "\n").
  const lineStart: number[] = [];
  let off = 0;
  for (const line of fileLines) {
    lineStart.push(off);
    off += line.length + 1;
  }
  const spanFor = (firstLine: number, lastLine: number): MatchResult => {
    const start = lineStart[firstLine];
    const end = lineStart[lastLine] + fileLines[lastLine].length;
    return { start, end, matchedText: haystack.slice(start, end), strategy: "line-trim" };
  };

  // ── Tier 1 — line-trim: same line count, each line equal after trim ───────
  // Handles the dominant real drift (indentation / trailing whitespace) without
  // touching intra-line whitespace, which is semantically significant in Markdown.
  {
    const n = searchLines.length;
    const trimmed = searchLines.map((l) => l.trim());
    const candidates: number[] = [];
    for (let i = 0; i + n <= fileLines.length; i++) {
      let ok = true;
      for (let j = 0; j < n; j++) {
        if (fileLines[i + j].trim() !== trimmed[j]) {
          ok = false;
          break;
        }
      }
      if (ok) candidates.push(i);
    }
    if (candidates.length === 1) {
      const i = candidates[0];
      return spanFor(i, i + n - 1);
    }
    if (candidates.length > 1) return null; // ambiguous — never guess
  }

  // ── Tier 2 — anchored (search ≥ 3 lines) ──────────────────────────────────
  // Match the first and last NON-BLANK trimmed lines as anchors, accept exactly
  // one minimal non-overlapping span between them, and reject if the matched
  // region balloons past 3× the search size.
  {
    const nonBlank = searchLines
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    if (searchLines.length >= 3 && nonBlank.length >= 2) {
      const firstAnchor = nonBlank[0];
      const lastAnchor = nonBlank[nonBlank.length - 1];
      const spans: Array<{ i: number; k: number }> = [];
      for (let i = 0; i < fileLines.length; i++) {
        if (fileLines[i].trim() !== firstAnchor) continue;
        for (let k = i; k < fileLines.length; k++) {
          if (fileLines[k].trim() === lastAnchor) {
            spans.push({ i, k }); // nearest last-anchor → minimal span for this i
            break;
          }
        }
      }
      if (spans.length === 1) {
        const { i, k } = spans[0];
        if (k - i + 1 > searchLines.length * 3) return null; // max-span guard
        const start = lineStart[i];
        const end = lineStart[k] + fileLines[k].length;
        return { start, end, matchedText: haystack.slice(start, end), strategy: "anchored" };
      }
      if (spans.length > 1) return null; // ambiguous — never guess
    }
  }

  return null;
}
