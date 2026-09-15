import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildCitationsBlock,
  forgetBibliography,
  resolveSelectionCitations,
  resolveSelectionBibliography,
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
  21: "body text before the tail",
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

describe("bibliography recovery", () => {
  it("retries a cached negative when document extent becomes authoritative", async () => {
    const source = { documentId: "extent7to11", pageCount: 7 };
    await resolveSelectionBibliography("", source, async () => "Body", "References");
    const fetch = vi.fn(async (n: number) => n === 11 ? "References\nSmith. Newly reachable bibliography." : "Body");
    const result = await resolveSelectionBibliography("", { ...source, pageCount: 11 }, fetch, "References");
    expect(fetch).toHaveBeenCalledWith(11);
    expect(result.block).toContain("Newly reachable bibliography");
  });

  it("refreshes cached content when extent or outline coverage changes", async () => {
    const source = { documentId: "extent-outline-refresh", pageCount: 7 };
    await resolveSelectionBibliography("", source, async n => n === 7 ? "References\n[1] Original." : "Body", "References");
    const extended = await resolveSelectionBibliography("", { ...source, pageCount: 11 },
      async n => n === 7 ? "References\n[1] Original." : n === 8 ? "[2] Newly reachable continuation." : "", "References");
    expect(extended.block).toContain("Newly reachable continuation");

    const outlined = await resolveSelectionBibliography("", { ...source, pageCount: 11, outline: [{ title: "References", pageNum: 2 }] },
      async n => n === 2 ? "References\n[1] Correct outline location." : "", "References");
    expect(outlined.block).toContain("Correct outline location");
  });

  it("supplies actual author-year References page text and page coverage", async () => {
    const fetch = vi.fn(async (n: number) => n === 11
      ? "References\nSmith, Alice (2024). Distinctive source title." : "Body");
    const result = await resolveSelectionBibliography("page7", { documentId: "raw11", pageCount: 11 }, fetch, "참고문헌 보여줘");
    expect(result.block).toContain("Smith, Alice");
    expect(result.block).toContain('page="11"');
    expect(result.block).toContain('failed_pages=""');
  });

  it("tries an outline heading outside the tail and stops before an appendix", async () => {
    const fetch = vi.fn(async (n: number) => n === 4
      ? "References\nSmith (2024). Work.\nAppendix A\nPRIVATE_APPENDIX" : "");
    const result = await resolveSelectionBibliography("", {
      documentId: "outline4", pageCount: 100, outline: [{ title: "References", pageNum: 4 }],
    }, fetch, "References");
    expect(fetch.mock.calls[0][0]).toBe(4);
    expect(result.block).toContain("Smith");
    expect(result.block).not.toContain("PRIVATE_APPENDIX");
  });

  it("retries failed reads with the same document identity", async () => {
    const source = { documentId: "retry11", pageCount: 11 };
    const failed = await resolveSelectionBibliography("", source, async () => undefined, "References");
    expect(failed.failedPages).toContain(11);
    const result = await resolveSelectionBibliography("", source, async n => n === 11 ? "References\n[1] Restored author." : "Body", "References");
    expect(result.block).toContain("Restored author");
  });

  it("retries a missing continuation after finding the heading", async () => {
    const source = { documentId: "retry-continuation", pageCount: 11 };
    await resolveSelectionBibliography("[8]", source, async n => n === 10 ? "References\n[1] First." : n === 11 ? undefined : "Body");
    const result = await resolveSelectionBibliography("[8]", source, async n => n === 10 ? "References\n[1] First." : n === 11 ? "[8] Recovered continuation." : "Body");
    expect(result.block).toContain("Recovered continuation");
  });

  it("matches prose reference90 before the general-list cap", async () => {
    const result = await resolveSelectionCitations("", { documentId: "entry90", pageCount: 1 },
      async () => "References\n" + Array.from({ length: 90 }, (_, i) => `[${i + 1}] Author${i + 1}.`).join("\n"),
      "reference 90의 저자는?");
    expect(result.map(c => c.num)).toEqual([90]);
  });

  it("attributes clipping to the exact fetched bibliography page", async () => {
    const result = await resolveSelectionBibliography("", { documentId: "clip11", pageCount: 11 },
      async n => n === 11 ? "References\nSmith " + "x".repeat(9000) : "Body", "References");
    expect(result.block).toContain('page="11" clipped="true"');
    expect(result.block).toContain("bibliography page 11 excerpt clipped");
  });

  it("preserves plain numbered and initialled author entries in raw excerpts", async () => {
    const result = await resolveSelectionBibliography("", { documentId: "plain-numbered", pageCount: 1 },
      async () => "References\n1. Alice Smith. A first paper.\n2. Bob Jones. Another paper.\nA. Zhang. A third paper.", "References");
    expect(result.block).toContain("1. Alice Smith");
    expect(result.block).toContain("2. Bob Jones");
    expect(result.block).toContain("A. Zhang");
    expect(result.citations).toEqual([]);
  });
});
