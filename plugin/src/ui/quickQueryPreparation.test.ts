import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("../context/pdfReferenceContext", () => ({ resolveSelectionContextAsync: vi.fn() }));
vi.mock("../context/quickQueryContext", () => ({
  buildQuickQueryMessages: vi.fn(() => []), buildQuickQueryRetrievalQuery: (_selection: string, query: string) => query,
}));
vi.mock("../context/providerContextFormat", () => ({ formatCuratorContextPack: () => "READY_EVIDENCE" }));
import { resolveSelectionContextAsync } from "../context/pdfReferenceContext";
import { buildQuickQueryMessages } from "../context/quickQueryContext";
import { QuickQueryPopover } from "./quickQueryPopover";

afterEach(() => vi.useRealTimers());

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("popover evidence preparation", () => {
  it("keeps evidence ready after the deadline, without enriching a gated follow-up", async () => {
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
        getPinnedContextRefs: () => [], incuratorClient: { available: true, fetchContext },
        settings: { provider: "openai", streamingEnabled: true }, llmClient: { streamChat },
      },
    });
    const answerEl = { empty: vi.fn(), createSpan: vi.fn() };
    const pending = popover.runQuery("Explain this", answerEl, {}, {});
    await vi.advanceTimersByTimeAsync(5000);
    evidence.resolve({ ok: true });
    await vi.advanceTimersByTimeAsync(5000);
    references.resolve({ block: "explicit reference" });
    await pending;
    expect(vi.mocked(buildQuickQueryMessages).mock.lastCall?.[0].vaultEvidenceBlock).toBe("READY_EVIDENCE");
    await popover.runQuery("again", answerEl, {}, {});
    expect(vi.mocked(buildQuickQueryMessages).mock.lastCall?.[0].vaultEvidenceBlock).toBeUndefined();
    expect(fetchContext).toHaveBeenCalledOnce();
  });
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
