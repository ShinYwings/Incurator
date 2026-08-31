import { describe, expect, it } from "vitest";
import { buildRecencyAnchor, POPOVER_PROFILE, SIDECHAT_PROFILE } from "./promptRegistry";
import { contextPriorityInstruction } from "./chatContextPriority";

/**
 * A context block the instructions never name is a block the model ignores.
 *
 * This has now been missed three times, by three different changes, always at
 * the same two sites:
 *
 *  - v0.48.4 → PR #131: `<unresolved_cross_references>` was added and
 *    `buildRecencyAnchor` was not updated.
 *  - v0.55.0 → PR #154: the page-image capability was added and
 *    `buildRecencyAnchor` was not updated.
 *  - v0.56.0 → this PR: `<resolved_citations>` was added and
 *    `buildRecencyAnchor` was not updated.
 *
 * Each time it was caught by a human reading the diff. The pattern is stable
 * enough to test: whatever block the context builders can emit, the last
 * instruction the model reads must name it, because that is the position of
 * strongest attention and the one that wins a long session.
 *
 * So this asserts the *set*, not one block. A fourth block added without a
 * matching mention turns this red on the commit that adds it.
 */

/** Every block the context builders can put in front of the model. */
const EMITTED_BLOCKS = [
  "<resolved_cross_references>",
  "<unresolved_cross_references>",
  "<resolved_citations>",
  "<workspace_notes>",
] as const;

/** Named without the angle brackets in prose is fine; the name must appear. */
function names(text: string, block: string): boolean {
  return text.includes(block.replace(/[<>]/g, ""));
}

describe("every emitted context block is announced to the model", () => {
  it("the recency anchor names all of them", () => {
    // Emitted LAST, at the recency position. If a block is missing here, a long
    // session steers back to the blocks that are named and ignores the rest.
    const anchor = buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: true , reality: "plugin-injected"});
    for (const block of EMITTED_BLOCKS) {
      expect(names(anchor, block), `recency anchor does not name ${block}`).toBe(true);
    }
  });

  it("the pointer instruction names all of them", () => {
    const instruction = contextPriorityInstruction(true);
    for (const block of EMITTED_BLOCKS) {
      expect(names(instruction, block), `pointer instruction does not name ${block}`).toBe(
        true
      );
    }
  });

  it("holds for the sidechat profile too, not just the popover", () => {
    const anchor = buildRecencyAnchor(SIDECHAT_PROFILE, { hasPrimarySelection: true , reality: "plugin-injected"});
    for (const block of EMITTED_BLOCKS) {
      expect(names(anchor, block), `sidechat anchor does not name ${block}`).toBe(true);
    }
  });

  it("says what to DO with the citations block, not merely that it exists", () => {
    // Naming a block without a verb leaves the model to guess. The page-image
    // regression was exactly this shape: the tool was reachable in principle
    // and the prompt gave no instruction to reach for it.
    const anchor = buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: true , reality: "plugin-injected"});
    expect(anchor).toMatch(/answer about the cited work|from its entry/i);
  });
});
