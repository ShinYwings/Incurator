/**
 * Helpers for recovering from output-token truncation (v0.24.0).
 *
 * When a provider stops with `finish_reason: "length"` (Gemini `MAX_TOKENS`,
 * Claude `max_tokens`) the answer is cut off mid-sentence — often mid-edit-block.
 * The chat layer issues a "continue" request and must splice the continuation
 * onto the partial WITHOUT duplicating the overlap the model frequently re-emits,
 * and without leaving a mangled ` ```ai-agent-edit ` fence at the seam.
 *
 * All functions here are pure and unit-tested; the chat sidebar owns the loop.
 */

/**
 * Minimum suffix/prefix overlap (in chars) we trust when de-duplicating the
 * seam. Below this, an "overlap" is just a common boundary (a backtick, a
 * newline, "ed") and trusting it would wrongly delete real text — so we append
 * verbatim instead.
 */
export const MIN_STITCH_OVERLAP = 8;

/** Cap the overlap search so very long answers stay O(window), not O(n²). */
const MAX_OVERLAP_WINDOW = 4000;

/**
 * Collapse a doubled `ai-agent-edit` fence marker created when the model
 * re-opens the block at the seam (e.g. ` ```ai-agent-ai-agent-edit `). Targeted
 * to the edit fence only — we never rewrite arbitrary backtick runs.
 */
export function repairMangledEditFence(text: string): string {
  return text.replace(/ai-agent-(?:ai-agent-)+edit/g, "ai-agent-edit");
}

/**
 * Splice a continuation onto a truncated partial. Finds the longest suffix of
 * `existing` that is a prefix of `continuation` (≥ MIN_STITCH_OVERLAP) and drops
 * the duplicate; otherwise appends verbatim. Repairs a doubled edit fence at the
 * seam.
 */
export function stitchContinuation(existing: string, continuation: string): string {
  if (!existing) return repairMangledEditFence(continuation ?? "");
  if (!continuation) return existing;

  const window = Math.min(existing.length, continuation.length, MAX_OVERLAP_WINDOW);
  let overlap = 0;
  for (let len = window; len >= MIN_STITCH_OVERLAP; len--) {
    if (existing.slice(existing.length - len) === continuation.slice(0, len)) {
      overlap = len;
      break;
    }
  }

  const joined = overlap > 0 ? existing + continuation.slice(overlap) : existing + continuation;
  return repairMangledEditFence(joined);
}

/**
 * True when the text ends with an opened ` ```ai-agent-edit ` fence that was
 * never closed by a later ` ``` ` line — i.e. truncation happened inside an
 * edit block, so the continuation must resume and close it.
 */
export function hasUnterminatedEditFence(text: string): boolean {
  const marker = "```ai-agent-edit";
  const lastOpen = text.lastIndexOf(marker);
  if (lastOpen === -1) return false;
  const after = text.slice(lastOpen + marker.length);
  // Anchor on the `>>>>` REPLACE terminator, NOT a bare ``` fence: a nested
  // markdown code block inside the REPLACE body (e.g. a Python snippet) would
  // fool a fence-only check into thinking the edit block already closed. The
  // edit block is complete only once `>>>>` appears AND the surrounding code
  // fence closes after it.
  const closer = after.search(/\n>{3,}/);
  if (closer === -1) return true;
  return !/\n\s*```/.test(after.slice(closer));
}

/**
 * Build the continuation user-turn that resumes a truncated answer. When the cut
 * happened inside an edit block, the prompt explicitly tells the model to finish
 * the SEARCH/REPLACE body and close the fence instead of re-opening a new block.
 */
export function buildContinuationPrompt(partial: string): string {
  const base =
    "Your previous message was cut off by the output-token limit. " +
    "Continue from EXACTLY where you stopped. Output ONLY the missing remainder: " +
    "do not repeat any text you already wrote, do not restate earlier content, and do not start over.";
  if (hasUnterminatedEditFence(partial)) {
    return (
      base +
      " You stopped INSIDE an `ai-agent-edit` block. Resume its SEARCH/REPLACE body and close it " +
      "with a line `>>>>` then the closing ``` fence. Do NOT re-open a new ai-agent-edit block."
    );
  }
  return base;
}
