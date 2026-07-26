import { describe, expect, it } from "vitest";
import {
  buildOpenTabContextKey,
  collectOpenTabLayoutContexts,
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

  it("collects deferred pop-out tabs from the public workspace layout", () => {
    const tabs = collectOpenTabLayoutContexts({
      main: {
        type: "split",
        children: [
          {
            type: "leaf",
            state: {
              type: "ai-agent-external-pdf",
              title: "paper.pdf",
              state: {
                docId: "paper",
                zoteroAttachmentKey: "ABCD1234",
                currentPage: 5,
              },
            },
          },
        ],
      },
      floating: {
        type: "floating",
        children: [
          {
            type: "window",
            children: [
              {
                type: "tabs",
                currentTab: 2,
                children: [
                  {
                    type: "leaf",
                    state: {
                      type: "markdown",
                      title: "First note",
                      state: { file: "03_Notes/First note.md" },
                    },
                  },
                  {
                    type: "leaf",
                    state: {
                      type: "markdown",
                      title: "Second note",
                      state: { file: "03_Notes/Second note.md" },
                    },
                  },
                  {
                    type: "leaf",
                    state: {
                      type: "ai-agent-chat",
                      state: {},
                    },
                  },
                ],
              },
            ],
          },
        ],
      },
    });

    expect(tabs).toEqual([
      {
        viewType: "ai-agent-external-pdf",
        sourceIdentity: "zotero:ABCD1234",
        filePath: undefined,
        label: "paper.pdf",
        pageNum: 5,
      },
      {
        viewType: "markdown",
        sourceIdentity: "03_Notes/First note.md",
        filePath: "03_Notes/First note.md",
        label: "First note",
        pageNum: undefined,
      },
      {
        viewType: "markdown",
        sourceIdentity: "03_Notes/Second note.md",
        filePath: "03_Notes/Second note.md",
        label: "Second note",
        pageNum: undefined,
      },
    ]);
  });

  it("keeps deferred copies of the same PDF on different pages distinct", () => {
    const tabs = collectOpenTabLayoutContexts({
      type: "tabs",
      children: [3, 4].map((currentPage) => ({
        type: "leaf",
        state: {
          type: "ai-agent-external-pdf",
          title: "paper.pdf",
          state: {
            zoteroAttachmentKey: "ABCD1234",
            currentPage,
          },
        },
      })),
    });

    expect(tabs.map((tab) => tab.pageNum)).toEqual([3, 4]);
  });
});
