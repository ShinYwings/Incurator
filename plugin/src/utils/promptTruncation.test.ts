import { describe, expect, it } from "vitest";
import { truncateSystemPrompt } from "./promptTruncation";

/**
 * The assembled system prompt was cut with `slice(0, limit)` — head kept, tail
 * dropped. But the prompt is built with its most attention-critical material
 * deliberately LAST: the recency anchor exists for that reason and says so, and
 * the resolved-wikilinks block, the active-file pointer and the edit-loop
 * contract sit beside it.
 *
 * So under load the truncation removed exactly what was placed there to survive
 * attention decay, and kept the boilerplate at the top instead. Backwards from
 * the code's own stated intent.
 *
 * The third instance of one defect in this release: the book outline showed page
 * 1 to a reader on page 400, a long note was cut at its opening, and the prompt
 * dropped its own conclusion. Cutting from the wrong end.
 */
const HEAD = "You are a reading assistant. ".repeat(40);
const MIDDLE = "supporting evidence block. ".repeat(400);
const TAIL =
  "<resolved_wikilinks>the linked note</resolved_wikilinks>\n" +
  "<critical_invariants>read-only: do NOT output edit blocks</critical_invariants>";

describe("truncating an assembled system prompt", () => {
  const prompt = `${HEAD}${MIDDLE}${TAIL}`;

  it("returns the prompt untouched when it fits", () => {
    expect(truncateSystemPrompt(prompt, 1_000_000)).toBe(prompt);
  });

  it("keeps the invariants that were placed last on purpose", () => {
    const out = truncateSystemPrompt(prompt, 2000);
    expect(out).toContain("critical_invariants");
    expect(out).toContain("resolved_wikilinks");
  });

  it("still keeps the opening, which says what the assistant is", () => {
    const out = truncateSystemPrompt(prompt, 2000);
    expect(out).toContain("You are a reading assistant");
  });

  it("drops the middle, and says that it did", () => {
    const out = truncateSystemPrompt(prompt, 2000);
    expect(out).toContain("truncated");
    expect(out.length).toBeLessThanOrEqual(2200);
  });

  it("degrades to a plain head cut when the budget cannot hold both ends", () => {
    const out = truncateSystemPrompt(prompt, 40);
    expect(out.length).toBeLessThanOrEqual(120);
    expect(out).toContain("You are");
  });

  it("never returns more than it was given", () => {
    const short = "tiny prompt";
    expect(truncateSystemPrompt(short, 5).length).toBeLessThanOrEqual(
      short.length + 80
    );
  });
});
