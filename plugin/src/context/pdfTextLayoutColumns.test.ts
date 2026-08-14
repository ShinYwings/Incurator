import { describe, expect, it } from "vitest";
import { layoutTextItems, type LayoutTextItem } from "./pdfTextLayout";

/**
 * v0.56.0 — two-column pages are read column by column.
 *
 * `layoutTextItems` grouped by y and sorted by x, which is right for one column
 * and wrong for every two-column paper: each visual line concatenated the left
 * and right columns. Measured on "3D Line Mapping Revisited" p.24, its
 * References page:
 *
 *   `[1] Hichem Abdellali, Robert Frohlich, Viktor Vilagos, and [18] Daniel
 *    DeTone, Tomasz Malisi...`
 *
 * — two unrelated references welded into one line. Parsing that page for a
 * bibliography found 16 contaminated entries; with column detection it finds
 * 28 clean ones on the same page, and 110 across the section.
 *
 * The detector is deliberately conservative. A false positive reorders a
 * single-column page, which is far worse than the false negative of leaving a
 * two-column page interleaved — that is merely today's behaviour.
 */

function item(text: string, x: number, y: number, width = 40): LayoutTextItem {
  return { text, x, y, width, height: 10, fontSize: 10 };
}

/** n lines of two columns: left at x=50, right at x=300, gutter between. */
function twoColumnPage(n: number): LayoutTextItem[] {
  const items: LayoutTextItem[] = [];
  for (let i = 0; i < n; i += 1) {
    const y = 700 - i * 12;
    items.push(item(`L${i}`, 50, y, 180));
    items.push(item(`R${i}`, 300, y, 180));
  }
  return items;
}

function singleColumnPage(n: number): LayoutTextItem[] {
  const items: LayoutTextItem[] = [];
  for (let i = 0; i < n; i += 1) {
    const y = 700 - i * 12;
    items.push(item(`w${i}a`, 50, y, 100));
    items.push(item(`w${i}b`, 160, y, 100));
    items.push(item(`w${i}c`, 270, y, 100));
  }
  return items;
}

describe("column-aware layout", () => {
  it("reads a two-column page down one column then the other", () => {
    const { text } = layoutTextItems(twoColumnPage(30), { source: "pdfjs", yAxis: "up" });
    const lines = text.split("\n");
    // Every left line precedes every right line.
    const lastLeft = lines.findLastIndex((l) => l.startsWith("L"));
    const firstRight = lines.findIndex((l) => l.startsWith("R"));
    expect(firstRight).toBeGreaterThan(lastLeft);
    // And no line welds the two columns together — the old failure.
    expect(lines.some((l) => /L\d+\s+R\d+/.test(l))).toBe(false);
  });

  it("leaves a single-column page exactly as before", () => {
    const items = singleColumnPage(30);
    const withDetection = layoutTextItems(items, { source: "pdfjs", yAxis: "up" });
    const withoutDetection = layoutTextItems(items, {
      source: "pdfjs",
      yAxis: "up",
      columns: false,
    });
    // Byte-identical: detection must be a no-op when there is no gutter.
    expect(withDetection.text).toEqual(withoutDetection.text);
    // One line per y, all three runs on it — not one line per run.
    expect(withDetection.text.split("\n").length).toBe(30);
  });

  it("does not split a short page, where a gutter cannot be established", () => {
    // Two lines of two columns is indistinguishable from a table row or a
    // heading with a page number. Splitting on that evidence would reorder
    // ordinary content.
    const { text } = layoutTextItems(twoColumnPage(2), { source: "pdfjs", yAxis: "up" });
    expect(text.split("\n")[0]).toBe("L0 R0");
  });

  it("does not split when items straddle the candidate gutter", () => {
    // A full-width heading or figure crossing the middle means there is no
    // gutter there, whatever the rest of the page looks like.
    const items = twoColumnPage(30);
    for (let i = 0; i < 6; i += 1) {
      items.push(item(`WIDE${i}`, 40, 690 - i * 12, 450));
    }
    const { text } = layoutTextItems(items, { source: "pdfjs", yAxis: "up" });
    expect(text.split("\n").some((l) => /L\d+\s+R\d+/.test(l))).toBe(true);
  });

  it("does not split when one side holds almost nothing", () => {
    // A narrow marginal note, line numbers, or a citation gutter is not a
    // column.
    const items = singleColumnPage(30);
    for (let i = 0; i < 4; i += 1) items.push(item(`m${i}`, 520, 700 - i * 12, 20));
    const { text } = layoutTextItems(items, { source: "pdfjs", yAxis: "up" });
    // 30 body lines, not 30 left + 4 right split into two blocks.
    expect(text.split("\n").length).toBe(30);
    expect(text.split("\n")[0]).toContain("m0");
  });
});
