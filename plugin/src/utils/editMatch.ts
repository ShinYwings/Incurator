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

/** Lifecycle of a single `ai-agent-edit` proposal, derived from the live file. */
export type ProposalStatus = "reviewable" | "applied" | "not_found";

/**
 * Classify an edit proposal against the CURRENT file content (v0.14.1, Bug 9).
 *
 * Derived — never persisted — so it self-heals across re-render, session reload,
 * and the propose→accept→next-turn cycle:
 *  - `fileContent === null` → a new-file proposal: always reviewable.
 *  - SEARCH still matches (via the tolerant matcher) → reviewable.
 *  - SEARCH gone and REPLACE is empty/whitespace-only → deletion already applied.
 *  - SEARCH gone but the REPLACE block is present → already applied.
 *  - neither → not_found (reported honestly on the pill, not only after a click).
 *
 * `applied` is detected with the same tolerant, ambiguity-safe matcher used for
 * SEARCH (`findSearchBlock`) — NOT a bare substring test. This means the full
 * REPLACE block must appear as contiguous lines (whitespace-drift tolerant), and
 * a REPLACE string that also occurs elsewhere (≥2 places) is ambiguous and is
 * NOT reported as applied. A bare `includes` would falsely flag a short/common
 * replacement (e.g. a heading) that merely appears somewhere in the file.
 */
export function classifyProposalStatus(
  fileContent: string | null,
  search: string,
  replace: string
): ProposalStatus {
  if (fileContent === null) return "reviewable";
  if (findSearchBlock(fileContent, search)) return "reviewable";
  if (replace.trim().length === 0) return "applied";
  if (replace.trim().length > 0 && findUniqueStatusBlock(fileContent, replace)) return "applied";
  return "not_found";
}

function findUniqueStatusBlock(haystack: string, search: string): MatchResult | null {
  const match = findSearchBlock(haystack, search);
  if (!match) return null;

  if (match.strategy === "exact") {
    const second = haystack.indexOf(search, match.start + Math.max(search.length, 1));
    if (second !== -1) return null;
  }

  return match;
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
        // Start at i+1: a ≥3-line search always spans ≥2 file lines, so the first
        // and last anchors must be DIFFERENT lines. Starting at i would let an
        // identical first/last anchor (e.g. a closing `}`) match the same single
        // line, collapsing the span to length 1 and replacing one line with the
        // whole REPLACE block.
        for (let k = i + 1; k < fileLines.length; k++) {
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
