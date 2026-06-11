import { describe, it, expect } from "vitest";
import { parseMathSources } from "./mathSource";

describe("parseMathSources", () => {
  it("returns [] for source with no math", () => {
    expect(parseMathSources("just plain text, no formulas")).toEqual([]);
    expect(parseMathSources("")).toEqual([]);
  });

  it("extracts a single inline formula", () => {
    expect(parseMathSources("The energy $E=mc^2$ is famous.")).toEqual([
      { tex: "E=mc^2", display: false },
    ]);
  });

  it("extracts a single block formula and trims it", () => {
    expect(parseMathSources("$$\n\\int_0^1 x\\,dx\n$$")).toEqual([
      { tex: "\\int_0^1 x\\,dx", display: true },
    ]);
  });

  it("extracts multiple formulas IN ORDER (the mapping invariant)", () => {
    const src = "Given $a^2$ and $b^2$, then $$c^2 = a^2 + b^2$$ holds.";
    expect(parseMathSources(src)).toEqual([
      { tex: "a^2", display: false },
      { tex: "b^2", display: false },
      { tex: "c^2 = a^2 + b^2", display: true },
    ]);
  });

  it("does NOT treat currency like `$5 and $10` as math (space-adjacent guard)", () => {
    expect(parseMathSources("It costs $5 and $10 total.")).toEqual([]);
  });

  it("ignores escaped \\$ delimiters", () => {
    expect(parseMathSources("A literal \\$x\\$ dollar sign.")).toEqual([]);
  });

  it("ignores `$...$` inside an inline code span", () => {
    expect(parseMathSources("Use `$x^2$` for inline math, like $y^2$ here.")).toEqual([
      { tex: "y^2", display: false },
    ]);
  });

  it("ignores math inside a fenced code block", () => {
    const src = "Before $a$\n```\n$not_math$\n$$also_not$$\n```\nAfter $b$";
    expect(parseMathSources(src)).toEqual([
      { tex: "a", display: false },
      { tex: "b", display: false },
    ]);
  });

  it("ignores math inside a ~~~ fenced block too", () => {
    const src = "~~~python\nx = '$z$'\n~~~\nReal $w$";
    expect(parseMathSources(src)).toEqual([{ tex: "w", display: false }]);
  });

  it("does not span a newline for inline math (single-line rule)", () => {
    // A lone `$` then newline then `$` is not inline math.
    expect(parseMathSources("price is $5\nor $6 maybe")).toEqual([]);
  });

  it("handles block math with inner subscripts containing braces", () => {
    expect(parseMathSources("$$x_{i+1} = f(x_i)$$")).toEqual([
      { tex: "x_{i+1} = f(x_i)", display: true },
    ]);
  });

  it("prefers $$ block over two inline $ on the same run", () => {
    expect(parseMathSources("$$a$$")).toEqual([{ tex: "a", display: true }]);
  });

  it("counts mixed inline/block so the caller can match against rendered spans", () => {
    const src = "Intro $p$ mid $$Q$$ end $r$.";
    const parsed = parseMathSources(src);
    expect(parsed.length).toBe(3);
    expect(parsed.map((m) => m.display)).toEqual([false, true, false]);
  });

  it("does not let an escaped backtick swallow the rest of the document", () => {
    // Review fix: an escaped backtick (`\``) must be skipped at the top level, so
    // it is NOT mistaken for an inline-code opener that consumes everything — which
    // would drop the trailing real formula and break the parsed/rendered count.
    expect(parseMathSources("A literal \\` backtick, then $x^2$ stays visible.")).toEqual([
      { tex: "x^2", display: false },
    ]);
  });

  it("treats other escaped chars (\\\\, \\*) as literal without losing later math", () => {
    expect(parseMathSources("Path C:\\\\dir and a star \\* then $y$.")).toEqual([
      { tex: "y", display: false },
    ]);
  });
});
