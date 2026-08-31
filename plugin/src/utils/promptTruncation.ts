/**
 * Cutting an over-long system prompt from the middle, not from the end.
 *
 * `slice(0, limit)` keeps the head and drops the tail. That is the wrong end for
 * this prompt: the assembly deliberately puts its most attention-critical
 * material LAST — the recency anchor exists for exactly that reason and says so
 * in its own comment, and the resolved-wikilinks block, the active-file pointer
 * and the edit-loop contract sit beside it. Under load the old truncation
 * removed precisely what was placed there to survive attention decay, and kept
 * the boilerplate instead.
 *
 * The head still matters — it says what the assistant is and what it may do — so
 * the elision goes in the middle, where the supporting evidence sits and where
 * losing some of it degrades the answer rather than changing the rules.
 */

/** Share of the budget given to the opening. The rest holds the conclusion. */
const HEAD_SHARE = 0.65;

/** Below this, keeping two ends leaves too little of either to be worth it. */
const MIN_SPLIT_BUDGET = 400;

export function truncateSystemPrompt(text: string, maxLength: number): string {
  if (!text || text.length <= maxLength) return text;

  if (maxLength < MIN_SPLIT_BUDGET) {
    return `${text.slice(0, maxLength)}\n\n[Context truncated at ${maxLength} characters]`;
  }

  const head = Math.floor(maxLength * HEAD_SHARE);
  const tail = maxLength - head;
  const dropped = text.length - maxLength;
  return (
    `${text.slice(0, head)}\n\n` +
    `[${dropped} characters of supporting context truncated here to fit the ` +
    `model's window. The instructions above and the invariants below are ` +
    `complete.]\n\n` +
    `${text.slice(text.length - tail)}`
  );
}
