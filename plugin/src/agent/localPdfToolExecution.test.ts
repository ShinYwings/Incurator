import { describe, expect, it, vi } from "vitest";

vi.mock("obsidian", () => ({
  Notice: class Notice {
    constructor(_message: string) {}
  },
  requestUrl: vi.fn(async () => ({ json: {} })),
}));

import { LLMClient } from "./llm/LLMClient";
import { DEFAULT_SETTINGS } from "../types";
import type {
  LocalPdfToolContext,
  LocalPdfToolRunner,
} from "./llm/localPdfTools";

/**
 * Execution semantics of the local PDF reader (v0.41.0, PLUGIN_SCHEMA §13.7).
 * Every failure mode must become a typed tool message the model can answer
 * around — never a thrown turn, and never a read against a swapped document.
 */

const CONTEXT: LocalPdfToolContext = {
  hasActivePdf: true,
  pageCount: 673,
  currentPage: 276,
  documentId: "doc-1",
  outlineState: "present",
};

function makeClient(): LLMClient {
  return new LLMClient(
    { ...DEFAULT_SETTINGS, provider: "openai", model: "test-model" },
    { resolveCredential: async () => ({}) } as never,
  );
}

function runTool(
  client: LLMClient,
  name: string,
  rawArgs: string,
  runner: LocalPdfToolRunner | undefined,
  captured: LocalPdfToolContext | undefined,
  budget: number,
): Promise<{ content: string; pagesFetched: number }> {
  return (client as never as {
    runLocalPdfTool: (
      n: string,
      a: string,
      r: LocalPdfToolRunner | undefined,
      c: LocalPdfToolContext | undefined,
      b: number,
    ) => Promise<{ content: string; pagesFetched: number }>;
  }).runLocalPdfTool(name, rawArgs, runner, captured, budget);
}

function makeRunner(overrides: Partial<LocalPdfToolRunner> = {}): LocalPdfToolRunner {
  return {
    describeContext: () => CONTEXT,
    fetchPage: async (pageNum: number) => `text of page ${pageNum}`,
    searchAnchor: async () => [],
    ...overrides,
  };
}

describe("runLocalPdfTool", () => {
  it("returns the fetched page text and charges one page to the budget", async () => {
    const result = await runTool(
      makeClient(), "fetch_pdf_page", '{"page_number": 599}', makeRunner(), CONTEXT, 6
    );
    expect(result.content).toContain("Page 599:");
    expect(result.content).toContain("text of page 599");
    expect(result.pagesFetched).toBe(1);
  });

  it("refuses to read a different document when identity changed mid-request", async () => {
    const swapped = makeRunner({
      describeContext: () => ({ ...CONTEXT, documentId: "doc-2" }),
    });
    const fetchPage = vi.fn();
    const result = await runTool(
      makeClient(),
      "fetch_pdf_page",
      '{"page_number": 599}',
      { ...swapped, fetchPage },
      CONTEXT,
      6,
    );
    expect(result.content).toContain("document changed");
    expect(result.pagesFetched).toBe(0);
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it("reports an exhausted budget instead of fetching", async () => {
    const fetchPage = vi.fn();
    const result = await runTool(
      makeClient(),
      "fetch_pdf_page",
      '{"page_number": 599}',
      makeRunner({ fetchPage }),
      CONTEXT,
      0,
    );
    expect(result.content).toContain("budget_exhausted");
    expect(result.pagesFetched).toBe(0);
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it("reports an out-of-range page without calling the runner", async () => {
    const fetchPage = vi.fn();
    const result = await runTool(
      makeClient(),
      "fetch_pdf_page",
      '{"page_number": 99999}',
      makeRunner({ fetchPage }),
      CONTEXT,
      6,
    );
    expect(result.content).toContain("out_of_range");
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it("reports an empty page as not_found rather than empty content", async () => {
    const result = await runTool(
      makeClient(),
      "fetch_pdf_page",
      '{"page_number": 12}',
      makeRunner({ fetchPage: async () => "   " }),
      CONTEXT,
      6,
    );
    expect(result.content).toContain("not_found");
  });

  it("converts a thrown runner error into a typed message", async () => {
    const result = await runTool(
      makeClient(),
      "fetch_pdf_page",
      '{"page_number": 12}',
      makeRunner({
        fetchPage: async () => {
          throw new Error("viewer detached");
        },
      }),
      CONTEXT,
      6,
    );
    expect(result.content).toContain("viewer detached");
    expect(result.pagesFetched).toBe(0);
  });

  it("reports an unavailable reader when no runner is installed", async () => {
    const result = await runTool(
      makeClient(), "fetch_pdf_page", '{"page_number": 12}', undefined, CONTEXT, 6
    );
    expect(result.content).toContain("not available");
    expect(result.pagesFetched).toBe(0);
  });

  it("runs an anchor search for an outline-less document without charging pages", async () => {
    const outlineless: LocalPdfToolContext = { ...CONTEXT, outlineState: "absent" };
    const result = await runTool(
      makeClient(),
      "search_pdf_anchor",
      '{"query": "Jacobi"}',
      makeRunner({
        describeContext: () => outlineless,
        searchAnchor: async () => [
          { pageNum: 604, score: 7, snippet: "Jacobi's algorithm diagonalizes" },
        ],
      }),
      outlineless,
      6,
    );
    expect(result.content).toContain("p.604");
    expect(result.content).toContain("Jacobi's algorithm");
    expect(result.pagesFetched).toBe(0);
  });
});
