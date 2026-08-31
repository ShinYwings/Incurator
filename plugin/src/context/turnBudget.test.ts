import { describe, expect, it } from "vitest";
import { fitTurnBudget, type TurnBlock } from "./turnBudget";

/**
 * The reader's selection must not be crowded out by material they did not ask
 * for.
 *
 * Measured worst case before this existed: a 102-character selection inside a
 * 53,032-character turn — 0.19% — outweighed by the vault evidence pack alone by
 * about 206x. Every block had its own cap; none knew about any other; nothing
 * reserved a share for the thing the reader actually pointed at.
 */
const sel = (t: string): TurnBlock => ({
  text: t,
  priority: 0,
  pinned: true,
  label: "selection",
});
const block = (label: string, priority: number, n: number): TurnBlock => ({
  text: `<${label}>${"x".repeat(n)}</${label}>`,
  priority,
  label,
});

describe("fitting a turn around what the reader pointed at", () => {
  it("changes nothing when everything fits", () => {
    const blocks = [sel("this bit"), block("evidence", 4, 100)];
    expect(fitTurnBudget(blocks, 100_000)).toHaveLength(2);
  });

  it("never trims the selection, however tight the budget", () => {
    const out = fitTurnBudget(
      [sel("이게 뭐야"), block("evidence", 4, 50_000)],
      200
    );
    expect(out[0]).toBe("이게 뭐야");
  });

  it("drops what the vault volunteered before what the reader pointed at", () => {
    const out = fitTurnBudget(
      [
        sel("the selection"),
        block("citations", 1, 3000),
        block("evidence", 4, 3000),
      ],
      3500
    ).join("\n");
    expect(out).toContain("<citations>");
    expect(out).not.toContain("<evidence>");
  });

  it("says what it omitted, so the model does not fill the gap", () => {
    const out = fitTurnBudget(
      [sel("s"), block("evidence", 4, 9000), block("pinned_sources", 5, 9000)],
      500
    ).join("\n");
    expect(out).toContain("Omitted to fit this turn");
    expect(out).toContain("evidence");
  });

  it("keeps a straddling block in part when there is real room", () => {
    const out = fitTurnBudget([sel("s"), block("evidence", 4, 5000)], 2000).join(
      "\n"
    );
    expect(out).toContain("<evidence>");
    expect(out).toContain("truncated to fit this turn");
  });

  it("drops a straddling block whole when only a fragment would fit", () => {
    const out = fitTurnBudget([sel("s"), block("evidence", 4, 5000)], 300).join(
      "\n"
    );
    expect(out).not.toContain("<evidence>");
  });

  it("ignores empty blocks entirely", () => {
    const out = fitTurnBudget(
      [sel("s"), { text: "", priority: 1, label: "citations" }],
      100
    );
    expect(out).toEqual(["s"]);
  });
});
