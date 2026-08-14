import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildCitationsBlock,
  forgetBibliography,
  resolveSelectionCitations,
} from "./citationContext";

/**
 * Where the bibliography is found, and how often it is paid for.
 *
 * Both behaviours are load-bearing on the real document. The References section
 * sits at the end (scanning forward reads the whole paper to find it) and spans
 * pages under one heading (stopping at the heading page found 28 of 110
 * entries). And without caching, every popover question would re-fetch and
 * re-parse several pages before the model saw anything.
 */

const PAGES: Record<number, string> = {
  22: "body text, no bibliography here",
  23: "more body text citing [8] in passing",
  24: "References\n[1] A. One. First work. 2001.\n[2] B. Two. Second work. 2002.",
  25: "[3] C. Three. Third work. 2003.\n[8] H. Eight. The cited paper. 2008.",
  26: "[9] I. Nine. Ninth work. 2009.",
};

function makeFetcher() {
  const fetched: number[] = [];
  const fetch = vi.fn(async (pageNum: number) => {
    fetched.push(pageNum);
    return PAGES[pageNum];
  });
  return { fetch, fetched };
}

const SOURCE = { documentId: "doc-1", pageCount: 26 };

beforeEach(() => forgetBibliography("doc-1"));

describe("resolveSelectionCitations", () => {
  it("finds a bibliography that spans pages and resolves across it", async () => {
    const { fetch } = makeFetcher();
    const hits = await resolveSelectionCitations("we build on [8]", SOURCE, fetch);
    expect(hits.map((h) => h.label)).toEqual(["[8]"]);
    // [8] lives on the continuation page, not the heading page.
    expect(hits[0].entry).toContain("The cited paper");
  });

  it("never touches the document when the selection has no citation", async () => {
    const { fetch } = makeFetcher();
    const hits = await resolveSelectionCitations("just some prose about arr[8]", SOURCE, fetch);
    expect(hits).toEqual([]);
    // The array-index collision must be rejected BEFORE any page is fetched —
    // otherwise ordinary code-bearing prose pays for a bibliography scan.
    expect(fetch).not.toHaveBeenCalled();
  });

  it("scans backward from the end, not forward from page 1", async () => {
    const { fetch, fetched } = makeFetcher();
    await resolveSelectionCitations("see [8]", SOURCE, fetch);
    // Page 21 is the earliest the tail scan may reach; page 1 must never be read.
    expect(fetched).not.toContain(1);
    expect(Math.min(...fetched)).toBeGreaterThan(20);
  });

  it("pays for the scan once per document", async () => {
    const { fetch } = makeFetcher();
    await resolveSelectionCitations("see [8]", SOURCE, fetch);
    const afterFirst = fetch.mock.calls.length;
    expect(afterFirst).toBeGreaterThan(0);

    await resolveSelectionCitations("and also [9]", SOURCE, fetch);
    expect(fetch.mock.calls.length).toBe(afterFirst);
  });

  it("remembers a fruitless search too, so it is not repeated", async () => {
    const empty = vi.fn(async () => "no bibliography anywhere on this page");
    const source = { documentId: "doc-empty", pageCount: 10 };
    forgetBibliography("doc-empty");

    expect(await resolveSelectionCitations("see [8]", source, empty)).toEqual([]);
    const afterFirst = empty.mock.calls.length;
    expect(await resolveSelectionCitations("see [8]", source, empty)).toEqual([]);
    expect(empty.mock.calls.length).toBe(afterFirst);
  });

  it("prefers pages it already has over fetching them", async () => {
    const { fetch } = makeFetcher();
    const withKnown = {
      ...SOURCE,
      documentId: "doc-known",
      knownPages: [24, 25, 26].map((pageNum) => ({ pageNum, text: PAGES[pageNum] })),
    };
    forgetBibliography("doc-known");
    const hits = await resolveSelectionCitations("see [8]", withKnown, fetch);
    expect(hits.map((h) => h.label)).toEqual(["[8]"]);
    // 24/25/26 were supplied; only the pages above 26 (none) could need fetching.
    expect(fetch.mock.calls.map((c) => c[0])).not.toContain(24);
  });

  it("survives a fetch that throws", async () => {
    const boom = vi.fn(async () => {
      throw new Error("backend down");
    });
    forgetBibliography("doc-boom");
    await expect(
      resolveSelectionCitations("see [8]", { documentId: "doc-boom", pageCount: 5 }, boom)
    ).resolves.toEqual([]);
  });
});

describe("buildCitationsBlock", () => {
  it("is empty when nothing resolved, so no stray block reaches the prompt", () => {
    expect(buildCitationsBlock([])).toBe("");
  });

  it("labels each entry and tells the model what the block is for", () => {
    const block = buildCitationsBlock([
      { num: 8, label: "[8]", entry: "H. Eight. The cited paper. 2008." },
    ]);
    expect(block).toContain('<citation label="[8]">');
    expect(block).toContain("The cited paper");
    expect(block).toMatch(/Explain the cited work/);
  });
});
