import { describe, expect, it } from "vitest";
import {
  LOCAL_PDF_TOOL_NAMES,
  buildLocalPdfTools,
  isLocalPdfToolName,
  parseLocalPdfToolCall,
  type LocalPdfToolContext,
} from "./localPdfTools";

const ACTIVE: LocalPdfToolContext = {
  hasActivePdf: true,
  pageCount: 673,
  currentPage: 276,
  documentId: "doc-1",
  outlineState: "present",
};

describe("buildLocalPdfTools", () => {
  it("exposes fetch_pdf_page for an active PDF with a known page count", () => {
    const names = buildLocalPdfTools(ACTIVE).map((t) => t.function.name);
    expect(names).toContain("fetch_pdf_page");
  });

  it("withholds search_pdf_anchor when the document has an outline", () => {
    const names = buildLocalPdfTools(ACTIVE).map((t) => t.function.name);
    expect(names).not.toContain("search_pdf_anchor");
  });

  it("exposes search_pdf_anchor only for a document proven outline-less", () => {
    const names = buildLocalPdfTools({ ...ACTIVE, outlineState: "absent" }).map(
      (t) => t.function.name
    );
    expect(names).toContain("search_pdf_anchor");
  });

  it("treats an unparsed outline as present (conservative withhold)", () => {
    const names = buildLocalPdfTools({ ...ACTIVE, outlineState: "unknown" }).map(
      (t) => t.function.name
    );
    expect(names).not.toContain("search_pdf_anchor");
  });

  it("emits nothing without an active PDF", () => {
    expect(buildLocalPdfTools({ ...ACTIVE, hasActivePdf: false })).toEqual([]);
  });

  it("emits nothing when the page count is unknown or non-positive", () => {
    expect(buildLocalPdfTools({ ...ACTIVE, pageCount: undefined })).toEqual([]);
    expect(buildLocalPdfTools({ ...ACTIVE, pageCount: 0 })).toEqual([]);
  });

  it("emits nothing without a stable document identity", () => {
    expect(buildLocalPdfTools({ ...ACTIVE, documentId: undefined })).toEqual([]);
  });

  it("never emits a name outside the closed set", () => {
    for (const state of ["present", "absent", "unknown"] as const) {
      const names = buildLocalPdfTools({ ...ACTIVE, outlineState: state }).map(
        (t) => t.function.name
      );
      for (const name of names) {
        expect(LOCAL_PDF_TOOL_NAMES).toContain(name as (typeof LOCAL_PDF_TOOL_NAMES)[number]);
      }
    }
  });
});

describe("isLocalPdfToolName", () => {
  it("recognizes only the closed set", () => {
    expect(isLocalPdfToolName("fetch_pdf_page")).toBe(true);
    expect(isLocalPdfToolName("search_pdf_anchor")).toBe(true);
    expect(isLocalPdfToolName("curator_search")).toBe(false);
    expect(isLocalPdfToolName("read_file")).toBe(false);
  });
});

describe("parseLocalPdfToolCall", () => {
  it("parses a valid page fetch", () => {
    const parsed = parseLocalPdfToolCall("fetch_pdf_page", '{"page_number": 599}', ACTIVE);
    expect(parsed).toEqual({ kind: "fetch_page", pageNum: 599 });
  });

  it("rejects a page beyond the document with a typed error", () => {
    const parsed = parseLocalPdfToolCall("fetch_pdf_page", '{"page_number": 9999}', ACTIVE);
    expect(parsed).toMatchObject({ kind: "error", code: "out_of_range" });
  });

  it("rejects a non-positive or non-integer page with a typed error", () => {
    expect(parseLocalPdfToolCall("fetch_pdf_page", '{"page_number": 0}', ACTIVE)).toMatchObject({
      kind: "error",
      code: "out_of_range",
    });
    expect(parseLocalPdfToolCall("fetch_pdf_page", '{"page_number": 1.5}', ACTIVE)).toMatchObject({
      kind: "error",
      code: "invalid_arguments",
    });
  });

  it("rejects unparseable arguments with a typed error", () => {
    expect(parseLocalPdfToolCall("fetch_pdf_page", "not json", ACTIVE)).toMatchObject({
      kind: "error",
      code: "invalid_arguments",
    });
  });

  it("refuses any page fetch when the context cannot bound it", () => {
    const parsed = parseLocalPdfToolCall(
      "fetch_pdf_page",
      '{"page_number": 5}',
      { ...ACTIVE, pageCount: undefined }
    );
    expect(parsed).toMatchObject({ kind: "error", code: "unavailable" });
  });

  it("parses a search only when the tool is exposed", () => {
    const outlineless = { ...ACTIVE, outlineState: "absent" as const };
    expect(parseLocalPdfToolCall("search_pdf_anchor", '{"query": "Jacobi"}', outlineless)).toEqual({
      kind: "search_anchor",
      query: "Jacobi",
    });
    // With an outline the tool is never exposed, so a call to it is invalid.
    expect(parseLocalPdfToolCall("search_pdf_anchor", '{"query": "Jacobi"}', ACTIVE)).toMatchObject({
      kind: "error",
      code: "unavailable",
    });
  });

  it("rejects an empty search query", () => {
    const outlineless = { ...ACTIVE, outlineState: "absent" as const };
    expect(parseLocalPdfToolCall("search_pdf_anchor", '{"query": "   "}', outlineless)).toMatchObject(
      { kind: "error", code: "invalid_arguments" }
    );
  });

  it("rejects an unknown tool name", () => {
    expect(parseLocalPdfToolCall("read_file", "{}", ACTIVE)).toMatchObject({
      kind: "error",
      code: "unknown_tool",
    });
  });
});

/**
 * v0.54.0 P2 — the pixel escape hatch is model-invoked, not heuristic.
 *
 * The page-level `isScannedLike` verdict cannot route this: on the paper that
 * motivated the feature, the page holding a rasterized equation reports 4,193
 * text characters, so any page-aggregate test calls it a text page. The model
 * is the only party that knows the answer it needs is missing.
 */
describe("read_pdf_page_image", () => {
  it("is offered whenever a page can be fetched at all", () => {
    const names = buildLocalPdfTools(ACTIVE).map((t) => t.function.name);
    expect(names).toContain("read_pdf_page_image");
  });

  it("disappears with the rest of the reader when no PDF is active", () => {
    const names = buildLocalPdfTools({ ...ACTIVE, hasActivePdf: false }).map(
      (t) => t.function.name,
    );
    expect(names).not.toContain("read_pdf_page_image");
  });

  it("tells the model when to reach for it, not just that it exists", () => {
    const tool = buildLocalPdfTools(ACTIVE).find(
      (t) => t.function.name === "read_pdf_page_image",
    );
    // Without a stated trigger the model defaults to the text tool and never
    // discovers that the equation it needs was never in the text layer.
    expect(tool?.function.description.toLowerCase()).toMatch(
      /equation|figure|image|scan/,
    );
  });

  it("applies the same page validation as the text reader", () => {
    expect(
      parseLocalPdfToolCall("read_pdf_page_image", '{"page_number": 11}', ACTIVE),
    ).toEqual({ kind: "read_page_image", pageNum: 11 });
    expect(
      parseLocalPdfToolCall("read_pdf_page_image", '{"page_number": 9999}', ACTIVE),
    ).toMatchObject({ kind: "error", code: "out_of_range" });
    expect(
      parseLocalPdfToolCall("read_pdf_page_image", '{"page_number": 1.5}', ACTIVE),
    ).toMatchObject({ kind: "error", code: "invalid_arguments" });
  });
});

