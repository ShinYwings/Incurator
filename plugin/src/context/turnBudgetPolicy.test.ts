import { readFileSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";
import { buildQuickQueryMessages } from "./quickQueryContext";

/**
 * The budget policy, as a gate rather than a paragraph.
 *
 * v0.77.0 found four ways the prompt spent itself badly, and every one of them
 * was invisible to the existing gates:
 *
 *  - blocks with independent caps that nobody summed, so the reader's own
 *    selection measured 0.19% of its own turn;
 *  - one fact told four times, in the section that can least afford dilution;
 *  - instruction about blocks the turn could not contain, ~1,700 chars on every
 *    markdown turn;
 *  - a char ceiling that was measuring comments, so a release spent real budget
 *    trimming wording to satisfy a broken number.
 *
 * A new block or instruction must not be able to reintroduce any of those
 * without turning something red.
 */
const CONTEXT_DIR = join(__dirname);

function src(f: string): string {
  return readFileSync(join(CONTEXT_DIR, f), "utf-8");
}

describe("the turn budget is enforced, not described", () => {
  it("every optional block declares a priority, so none is silently unbounded", () => {
    const s = src("quickQueryContext.ts");
    // Each entry handed to fitTurnBudget carries a priority and a label. A block
    // added without them is a type error; a block added OUTSIDE the call is what
    // this catches.
    const inFit = s.slice(s.indexOf("fitTurnBudget("), s.indexOf("DEFAULT_TURN_BUDGET\n"));
    for (const block of [
      "resolvedReferencesBlock",
      "resolvedWikilinksBlock",
      "vaultEvidenceBlock",
      "pinnedBlock",
      "followups",
    ]) {
      expect(inFit, `${block} is assembled outside the budget`).toContain(block);
    }
  });

  it("the selection and the invariants are pinned, and nothing else is", () => {
    const s = src("quickQueryContext.ts");
    const pinned = (s.match(/pinned: true/g) ?? []).length;
    // selection, question, invariants — and no fourth thing quietly exempted.
    expect(pinned).toBe(3);
  });

  it("a turn cannot exceed the budget however much is offered", () => {
    const enormous = `<evidence>${"x".repeat(200_000)}</evidence>`;
    const messages = buildQuickQueryMessages({
      selectedText: "the selection",
      question: "what is this?",
      vaultEvidenceBlock: enormous,
      resolvedReferencesBlock: enormous,
      resolvedWikilinksBlock: enormous,
      pinnedContextRefs: [],
    });
    expect(String(messages[1].content).length).toBeLessThan(45_000);
  });

  it("keeps the reader's selection whatever else is offered", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "이 문장이 핵심이다",
      question: "이게 뭐야?",
      vaultEvidenceBlock: `<evidence>${"x".repeat(200_000)}</evidence>`,
      pinnedContextRefs: [],
    });
    expect(String(messages[1].content)).toContain("이 문장이 핵심이다");
  });

  it("the prose ceiling measures prompt text, not commentary", () => {
    // The gate desynced on a quoted phrase inside a comment and erased a real
    // 630-char prohibition from its own count. Stripping comments first is the
    // property; this asserts the stripper exists rather than re-deriving it.
    expect(src("promptRoleBudget.test.ts")).toContain("stripComments");
  });

  it("pointer instruction is chosen by document kind, not emitted unconditionally", () => {
    expect(src("chatContextPriority.ts")).toContain("PointerKind");
  });
});
