import { describe, expect, it } from "vitest";
import {
  buildOpenTabContextKey,
  isEligibleOpenTabView,
  shouldIncludeOpenTab,
} from "./openTabContext";

describe("open tab context policy", () => {
  it("enumerates only Markdown and PDF content leaves", () => {
    expect(isEligibleOpenTabView("markdown")).toBe(true);
    expect(isEligibleOpenTabView("pdf")).toBe(true);
    expect(isEligibleOpenTabView("ai-agent-external-pdf")).toBe(true);
    expect(isEligibleOpenTabView("ai-agent-chat")).toBe(false);
    expect(isEligibleOpenTabView("canvas")).toBe(false);
  });

  it("defaults visible ready tabs on and hidden ready tabs off", () => {
    expect(
      shouldIncludeOpenTab({
        isVisible: true,
        isReady: true,
        explicitlyIncluded: false,
        explicitlyExcluded: false,
      })
    ).toBe(true);
    expect(
      shouldIncludeOpenTab({
        isVisible: false,
        isReady: true,
        explicitlyIncluded: false,
        explicitlyExcluded: false,
      })
    ).toBe(false);
  });

  it("honors explicit eye state but never includes unavailable context", () => {
    expect(
      shouldIncludeOpenTab({
        isVisible: false,
        isReady: true,
        explicitlyIncluded: true,
        explicitlyExcluded: false,
      })
    ).toBe(true);
    expect(
      shouldIncludeOpenTab({
        isVisible: true,
        isReady: true,
        explicitlyIncluded: false,
        explicitlyExcluded: true,
      })
    ).toBe(false);
    expect(
      shouldIncludeOpenTab({
        isVisible: false,
        isReady: false,
        explicitlyIncluded: true,
        explicitlyExcluded: false,
      })
    ).toBe(false);
  });

  it("deduplicates exact identities while keeping different PDF pages distinct", () => {
    const pageOne = buildOpenTabContextKey({
      viewType: "ai-agent-external-pdf",
      filePath: "/references/paper.pdf",
      label: "paper.pdf",
      pageNum: 1,
    });
    const samePage = buildOpenTabContextKey({
      viewType: "ai-agent-external-pdf",
      filePath: "/references/paper.pdf",
      label: "paper.pdf",
      pageNum: 1,
    });
    const pageTwo = buildOpenTabContextKey({
      viewType: "ai-agent-external-pdf",
      filePath: "/references/paper.pdf",
      label: "paper.pdf",
      pageNum: 2,
    });

    expect(pageOne).toBe(samePage);
    expect(pageOne).not.toBe(pageTwo);
  });

  it("prefers a portable source identity over a machine-local runtime path", () => {
    expect(
      buildOpenTabContextKey({
        viewType: "ai-agent-external-pdf",
        sourceIdentity: "zotero:ABCD1234",
        filePath: "/Users/example/Zotero/storage/ABCD1234/paper.pdf",
        label: "paper.pdf",
        pageNum: 4,
      })
    ).toBe('["ai-agent-external-pdf","zotero:ABCD1234",4]');
  });
});
