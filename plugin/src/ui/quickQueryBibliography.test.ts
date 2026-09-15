import { describe, expect, it, vi } from "vitest";
import { QuickQueryPopover } from "./quickQueryPopover";
import { createPdfDocumentReader } from "../context/pdfDocumentReader";

describe("native popover bibliography preparation", () => {
  it("delivers distant source text and retains it on an author followup", async () => {
    const context: any = {
      viewType: "pdf", absolutePath: "/vault/A.pdf", filePath: "A.pdf",
      pdfPage: { pageNum: 7, pageCount: 7, text: "Body [...truncated]",
        windowPages: [{ pageNum: 7, text: "Body [...truncated]" }] },
    };
    const backend = vi.fn(async (args: any) => ({
      totalPages: 11, outline: [{ title: "References", pageNum: 11, level: 0 }],
      pages: [{ pageNum: args.pageNum, text: args.pageNum === 11
        ? "References\n[1] DISTINCT_AUTHOR. Paper title. 2026." : "Body text." }],
    }));
    const streamChat = vi.fn(async () => undefined);
    const popover: any = Object.create(QuickQueryPopover.prototype);
    Object.assign(popover, {
      capturedSelection: "passage", turns: [], popoverEl: null,
      startThinkingTimer: vi.fn(), stopThinkingTimer: vi.fn(), vaultEvidenceFor: async () => "",
      plugin: {
        refreshActiveContext: () => context,
        createActivePdfReader: (ctx: any) => createPdfDocumentReader(ctx, backend),
        getActivePdfDocumentId: () => undefined, getPinnedContextRefs: () => [],
        settings: { provider: "openai", streamingEnabled: true }, llmClient: { streamChat },
      },
    });
    const answer = { empty: vi.fn(), createSpan: vi.fn() };
    await popover.runQuery("참고문헌 알려줘", answer, {}, {});
    expect(backend.mock.calls.some(([args]) => args.pageNum === 11 && args.filePath === "/vault/A.pdf")).toBe(true);
    expect(JSON.stringify(streamChat.mock.calls[0])).toContain("DISTINCT_AUTHOR");
    await popover.runQuery("저자 전체 이름은?", answer, {}, {});
    expect(JSON.stringify(streamChat.mock.calls[1])).toContain("DISTINCT_AUTHOR");
    expect(JSON.stringify(streamChat.mock.calls[1])).toContain("Previous assistant answers are not evidence");
  });
});
