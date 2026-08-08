/**
 * Sanitize text read out of a PDF text layer before it crosses a process boundary.
 *
 * pdf.js emits U+0000 for glyphs whose embedded font carries no usable ToUnicode
 * mapping — common in exactly the scanned/rasterized regions where a reader most
 * wants a LaTeX transcription. Node's `spawn` rejects any argv entry containing a
 * null byte with a synchronous `TypeError: The argument 'args[0]' must be a string
 * without null bytes`, so such a selection never reaches the backend at all. The
 * plugin surfaced that as an LLM-provider fault, which it is not.
 *
 * These code points are extraction artifacts, not content: dropping them is the
 * fix, not a workaround for the spawn rule.
 */

/**
 * C0 controls (U+0000–U+001F) except tab/newline/carriage-return, DEL (U+007F),
 * and the C1 range (U+0080–U+009F). Everything else — including all Unicode math,
 * CJK, and combining marks — is content and is preserved verbatim.
 */
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g;

/**
 * Strip control characters and trim. Returns `""` when the selection carried no
 * readable characters at all, which callers must distinguish from "nothing was
 * selected" — an unreadable region deserves a message, an empty selection does not.
 */
export function sanitizePdfSelectionText(raw: string): string {
  if (!raw) return "";
  return raw.replace(CONTROL_CHARS, "").trim();
}

/** True when the selection had characters but every one of them was an artifact. */
export function isUnreadableSelection(raw: string): boolean {
  return raw.trim().length > 0 && sanitizePdfSelectionText(raw).length === 0;
}
