import { describe, expect, it, vi } from "vitest";
import { QuickQueryPopover } from "./quickQueryPopover";
import { PdfDocumentIndexService } from "../context/pdfDocumentIndex";

describe("popover source-bound document index", () => {
  it("keeps distant seen-page lookup after focus moves away from the captured viewer", async () => {
    const capturedIndex = new PdfDocumentIndexService();
    capturedIndex.upsertDocument("captured-paper", [
      { pageNum: 42, text: "Equation 7.3 wave function collapse" },
      { pageNum: 1, text: "Introduction" },
    ]);
    const context = {
      viewType: "pdf", pdfPage: {
        pageNum: 1, pageCount: 50, text: "Introduction",
        windowPages: [{ pageNum: 1, text: "Introduction" }],
      },
    };
    const fetchPage = vi.fn(async (pageNum: number) => pageNum === 42
      ? "Equation 7.3 wave function collapse — CAPTURED_PAPER_DETAIL" : undefined);
    const activeIndexLookup = vi.fn(() => { throw new Error("wrong workspace view"); });
    const streamChat = vi.fn(async () => undefined);
    const popover: any = Object.create(QuickQueryPopover.prototype);
    Object.assign(popover, {
      capturedSelection: "as shown in Eq. (7.3)", turns: [], popoverEl: null,
      startThinkingTimer: vi.fn(), stopThinkingTimer: vi.fn(), vaultEvidenceFor: async () => "",
      plugin: {
        refreshActiveContext: () => context,
        createActivePdfReader: () => ({
          documentKey: "/paper/a.pdf", searchDocumentId: "captured-paper",
          searchIndex: capturedIndex, prepare: async () => context.pdfPage, fetchPage,
        }),
        getActivePdfDocumentId: () => "other-active-paper",
        getActivePdfDocumentIndex: activeIndexLookup,
        getPinnedContextRefs: () => [],
        settings: { provider: "openai", streamingEnabled: true }, llmClient: { streamChat },
      },
    });
    await popover.runQuery("Explain this equation", { empty: vi.fn(), createSpan: vi.fn() }, {}, {});
    expect(fetchPage).toHaveBeenCalledWith(42);
    expect(JSON.stringify(streamChat.mock.calls[0])).toContain("CAPTURED_PAPER_DETAIL");
    expect(activeIndexLookup).not.toHaveBeenCalled();
  });
});
