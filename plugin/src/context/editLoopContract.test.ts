import { describe, it, expect } from "vitest";
import { parseEditLoopPhases, validateEditLoop } from "./editLoopContract";

const EDIT_BLOCK =
  '```ai-agent-edit filepath="note.md"\n' +
  "<<<< SEARCH\n" +
  "old line\n" +
  "==== REPLACE\n" +
  "new line\n" +
  ">>>>\n" +
  "```";

function conformingResponse(): string {
  return [
    "[[PHASE:ANALYSED]]",
    "The user wants the heading fixed; the gap is a typo.",
    "[[PHASE:REVIEWED]]",
    "My plan only touches the heading line, nothing else.",
    "[[PHASE:UPDATED]]",
    EDIT_BLOCK,
    "[[PHASE:REVIEWED]]",
    "The edit closes the typo gap and leaves the rest intact.",
  ].join("\n\n");
}

describe("parseEditLoopPhases", () => {
  it("extracts phase markers in document order and counts edit blocks", () => {
    const result = parseEditLoopPhases(conformingResponse());
    expect(result.phases.map((p) => p.label)).toEqual([
      "ANALYSED",
      "REVIEWED",
      "UPDATED",
      "REVIEWED",
    ]);
    expect(result.editBlocks).toBe(1);
  });

  it("reports zero edit blocks for pure prose", () => {
    const result = parseEditLoopPhases("Just an explanation, no edits here.");
    expect(result.phases).toHaveLength(0);
    expect(result.editBlocks).toBe(0);
  });
});

describe("validateEditLoop", () => {
  it("passes a fully conforming edit response", () => {
    const result = validateEditLoop(conformingResponse());
    expect(result.hasEdits).toBe(true);
    expect(result.ok).toBe(true);
    expect(result.missing).toEqual([]);
  });

  it("does not gate a pure Q&A response with no edits", () => {
    const result = validateEditLoop("Here is the answer to your question.");
    expect(result.hasEdits).toBe(false);
    expect(result.ok).toBe(true);
  });

  it("fails an edit response that omits the phase loop entirely", () => {
    const result = validateEditLoop("Sure, here is the change:\n\n" + EDIT_BLOCK);
    expect(result.hasEdits).toBe(true);
    expect(result.ok).toBe(false);
    expect(result.missing.length).toBeGreaterThan(0);
  });

  it("fails when the second REVIEWED (post-edit self-check) is missing", () => {
    const partial = [
      "[[PHASE:ANALYSED]]",
      "gap",
      "[[PHASE:REVIEWED]]",
      "plan",
      "[[PHASE:UPDATED]]",
      EDIT_BLOCK,
    ].join("\n\n");
    const result = validateEditLoop(partial);
    expect(result.hasEdits).toBe(true);
    expect(result.ok).toBe(false);
    expect(result.missing).toContain("REVIEWED (post-edit)");
  });

  it("passes when a stray REVIEWED precedes ANALYSED but a valid one sits before UPDATED", () => {
    const withStray = [
      "[[PHASE:REVIEWED]]", // stray/duplicate ahead of ANALYSED
      "premature note",
      "[[PHASE:ANALYSED]]",
      "the real gap",
      "[[PHASE:REVIEWED]]", // the valid pre-edit review
      "plan critique",
      "[[PHASE:UPDATED]]",
      EDIT_BLOCK,
      "[[PHASE:REVIEWED]]",
      "post-edit check",
    ].join("\n\n");
    const result = validateEditLoop(withStray);
    expect(result.ok).toBe(true);
  });

  it("ignores an inline-quoted marker that is not at a line start", () => {
    const inlineQuote =
      "You should emit `[[PHASE:ANALYSED]]` as a marker.\n\n" + EDIT_BLOCK;
    const parse = parseEditLoopPhases(inlineQuote);
    expect(parse.phases).toHaveLength(0);
    // Edits present but no real phase markers → gated.
    expect(validateEditLoop(inlineQuote).ok).toBe(false);
  });

  it("fails when UPDATED appears before the first REVIEWED (out of order)", () => {
    const outOfOrder = [
      "[[PHASE:ANALYSED]]",
      "gap",
      "[[PHASE:UPDATED]]",
      EDIT_BLOCK,
      "[[PHASE:REVIEWED]]",
      "late review",
    ].join("\n\n");
    const result = validateEditLoop(outOfOrder);
    expect(result.ok).toBe(false);
  });
});
