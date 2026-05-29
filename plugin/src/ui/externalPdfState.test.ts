import { describe, expect, it } from "vitest";
import { buildSyncedExternalPdfState } from "./externalPdfState";

describe("buildSyncedExternalPdfState", () => {
  it("preserves Zotero navigation state while syncing page state", () => {
    const state = buildSyncedExternalPdfState({
      docId: "doc-1",
      name: "paper.pdf",
      fallbackName: "External PDF",
      path: "/tmp/paper.pdf",
      zoom: 1.25,
      darkMode: true,
      tocOpen: false,
      currentPage: 3,
      zoteroAttachmentKey: "PZBCB9LJ",
      targetAnnotationKey: "KN63LR6C",
    });

    expect(state).toMatchObject({
      docId: "doc-1",
      name: "paper.pdf",
      path: "/tmp/paper.pdf",
      zoom: 1.25,
      darkMode: true,
      tocOpen: false,
      currentPage: 3,
      zoteroAttachmentKey: "PZBCB9LJ",
      targetAnnotationKey: "KN63LR6C",
    });
  });

  it("uses the fallback name when the current state has no name", () => {
    const state = buildSyncedExternalPdfState({
      docId: "doc-1",
      fallbackName: "cached.pdf",
      zoom: 1,
      darkMode: false,
      tocOpen: false,
      currentPage: 1,
    });

    expect(state.name).toBe("cached.pdf");
  });
});
