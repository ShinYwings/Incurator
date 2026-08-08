/**
 * Handle text read out of a PDF text layer before it crosses a process boundary.
 *
 * ## What a U+0000 in a PDF selection actually means
 *
 * It is not noise. It is a glyph pdf.js could not map to a character. A LaTeX
 * paper embeds its math in Computer Modern subsets (CMMI/CMSY/MSBM); when those
 * carry no `/ToUnicode` map, pdf.js has nothing to resolve the glyph with and
 * emits NUL in its place. Measured on `3D Line Mapping Revisited`, page 4,
 * whose CMMI10 subset has no ToUnicode: the text layer for equation (3) yields
 *
 *   "\0 = (\0 1, \0 2) with a single constraint: min \0 2 R 2 \0 T A \0 + b T \0, ..."
 *
 * with **10 NULs and zero U+03BB** — every one of those NULs is a lambda.
 *
 * ## Why deleting them is the wrong fix
 *
 * v0.52.1 stripped control characters so `spawn` would stop throwing
 * `TypeError: … must be a string without null bytes`. That silenced the crash
 * and produced something worse: the model received the equation with every
 * lambda deleted and faithfully transcribed the wreckage, so a wrong equation
 * landed on the clipboard looking plausible. A loud failure became silent
 * corruption.
 *
 * No text processing can recover the character, because the information is not
 * in the text layer at all — it is only in the rendered pixels. A selection
 * carrying unmapped glyphs must therefore be read as an IMAGE, not repaired as
 * text. That is what `hasUnmappedGlyphs` is for.
 */

/** The code point pdf.js emits where a glyph has no usable Unicode mapping. */
const UNMAPPED_GLYPH = "\u0000";

/**
 * How many glyphs in this selection the PDF could not map to characters.
 *
 * Each one is a character the reader can see and the text layer cannot name —
 * in a maths paper, almost always a Greek letter or an operator.
 */
export function countUnmappedGlyphs(raw: string): number {
  if (!raw) return 0;
  let n = 0;
  for (const ch of raw) if (ch === UNMAPPED_GLYPH) n += 1;
  return n;
}

/** True when any glyph in the selection lost its identity in the text layer. */
export function hasUnmappedGlyphs(raw: string): boolean {
  return countUnmappedGlyphs(raw) > 0;
}

/**
 * Make a selection safe to pass as an argv entry, removing nothing else.
 *
 * ONLY U+0000 is removed, because U+0000 is the only code point `spawn`
 * rejects. v0.52.1 also stripped the rest of C0, DEL, and C1 — none of which
 * break the boundary, and all of which may be real content. Deleting a
 * character that a process boundary would have accepted is data loss with no
 * reason behind it.
 *
 * Callers that care about fidelity — the LaTeX conversion does — must check
 * `hasUnmappedGlyphs` FIRST and take the image path. This function is the last
 * resort for paths that only need the prose.
 */
export function sanitizePdfSelectionText(raw: string): string {
  if (!raw) return "";
  return raw.split(UNMAPPED_GLYPH).join("").trim();
}

/** True when the selection had characters but none survive as readable text. */
export function isUnreadableSelection(raw: string): boolean {
  return raw.trim().length > 0 && sanitizePdfSelectionText(raw).length === 0;
}
