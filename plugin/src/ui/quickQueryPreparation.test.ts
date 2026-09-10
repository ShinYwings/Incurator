import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("../context/pdfReferenceContext", () => ({ resolveSelectionContextAsync: vi.fn() }));
vi.mock("../context/quickQueryContext", () => ({
  buildQuickQueryMessages: () => [], buildQuickQueryRetrievalQuery: (_selection: string, query: string) => query,
}));
import { resolveSelectionContextAsync } from "../context/pdfReferenceContext";
import { QuickQueryPopover } from "./quickQueryPopover";

afterEach(() => vi.useRealTimers());

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("popover evidence preparation", () => {
  it("starts evidence while references resolve, with one deadline from the start", async () => {
    vi.useFakeTimers();
    const references = deferred<any>();
    const evidence = deferred<any>();
    vi.mocked(resolveSelectionContextAsync).mockReturnValue(references.promise);
    const fetchContext = vi.fn(() => evidence.promise);
    const streamChat = vi.fn(async () => undefined);
    const popover: any = Object.create(QuickQueryPopover.prototype);
    Object.assign(popover, {
      capturedSelection: "passage", turns: [], popoverEl: null,
      startThinkingTimer: vi.fn(), stopThinkingTimer: vi.fn(), vaultWorkspacePath: () => "/vault",
      plugin: {
        refreshActiveContext: () => ({ pdfPage: { pageNum: 1 } }),
        getActivePdfDocumentId: () => "doc1", getActivePdfDocumentIndex: () => undefined,
        getPinnedContextRefs: () => [],
        incuratorClient: { available: true, fetchContext },
        settings: { provider: "openai", streamingEnabled: true }, llmClient: { streamChat },
      },
    });
    const answerEl = { empty: vi.fn(), createSpan: vi.fn() };
    const pending = popover.runQuery("Explain this", answerEl, {}, {});
    expect(fetchContext).toHaveBeenCalledTimes(1);
    expect(streamChat).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(4000);
    references.resolve({ block: "explicit reference" });
    await pending;
    expect(streamChat).toHaveBeenCalledTimes(1);
    // Reuse the same still-pending background lookup after the first turn.
    evidence.resolve({ ok: false });
    await Promise.resolve();
    await popover.vaultEvidenceFor("What else?");
    expect(fetchContext).toHaveBeenCalledTimes(1);
  });
});
