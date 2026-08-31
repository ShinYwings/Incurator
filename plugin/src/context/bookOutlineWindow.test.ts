import { describe, expect, it } from "vitest";
import { formatOutline } from "./providerContextFormat";
import type { PdfOutlineItem } from "../types";

/**
 * An outline is truncated to fit. WHERE it truncates decides whether a book
 * reader gets anything useful.
 *
 * Slicing the first 80 entries is invisible on a paper, which never has 80. On a
 * 600-page book it means a reader sitting on page 400 is handed the table of
 * contents for pages 1-100 — the part of the book they are not in — and nothing
 * about where they actually are. Every structural question they ask ("what
 * chapter is this", "where was this defined") is then answered from front
 * matter.
 */
function book(entries: number): PdfOutlineItem[] {
  return Array.from({ length: entries }, (_, i) => ({
    title: `Section ${i + 1}`,
    level: 1,
    pageNum: (i + 1) * 3,
  })) as PdfOutlineItem[];
}

describe("the outline a book reader is given", () => {
  it("keeps the part of the book the reader is actually in", () => {
    // 200 sections spanning 600 pages; the reader is on page 400.
    const out = formatOutline(book(200), 400);
    expect(out).toContain("Section 133"); // p.399 — where they are
    expect(out).toContain("p.399");
    // And NOT dominated by front matter it used to show instead.
    expect(out).not.toContain("Section 2 p.6");
  });

  it("keeps the book's top-level shape when it has one", () => {
    // Real outlines nest; chapters sit at level 0 and are few, so they survive
    // in full and the reader still knows where they are in the whole book.
    const nested = book(200).map((item, i) => ({
      ...item,
      level: i % 10 === 0 ? 0 : 1,
    }));
    const out = formatOutline(nested, 400);
    expect(out).toContain("Section 1 p.3"); // chapter 1, still present
    expect(out).toContain("Section 133"); // and where the reader is
  });

  it("stays bounded for a long book", () => {
    const out = formatOutline(book(400), 600);
    expect(out.split("\n").length).toBeLessThanOrEqual(80);
  });

  it("is unchanged for a paper, which never reaches the limit", () => {
    const paper = book(20);
    expect(formatOutline(paper, 5)).toBe(formatOutline(paper));
  });

  it("falls back to the head when no page is known", () => {
    const out = formatOutline(book(200));
    expect(out).toContain("Section 1");
  });
});
