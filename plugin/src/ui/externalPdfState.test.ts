import { describe, expect, it } from "vitest";
import {
  buildSyncedExternalPdfState,
  isRetainablePersistedDoc,
  resolveExternalPdfPath,
} from "./externalPdfState";

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

describe("isRetainablePersistedDoc", () => {
  it("retains any doc with a non-empty path (no existsSync at load time)", () => {
    // A path on a not-yet-mounted volume must NOT be dropped at startup; the
    // missing-file case is reported distinctly at resolve time.
    expect(isRetainablePersistedDoc({ path: "/Volumes/ext/paper.pdf" })).toBe(true);
  });

  it("drops entries with no path or an empty path (no recoverable identity)", () => {
    expect(isRetainablePersistedDoc({})).toBe(false);
    expect(isRetainablePersistedDoc({ path: "" })).toBe(false);
    expect(isRetainablePersistedDoc({ path: undefined })).toBe(false);
  });
});

describe("resolveExternalPdfPath", () => {
  it("prefers the live docState path", () => {
    expect(resolveExternalPdfPath("/a/live.pdf", "/b/cache.pdf")).toBe("/a/live.pdf");
  });

  it("falls back to the cache path when docState has none", () => {
    expect(resolveExternalPdfPath(undefined, "/b/cache.pdf")).toBe("/b/cache.pdf");
    expect(resolveExternalPdfPath("", "/b/cache.pdf")).toBe("/b/cache.pdf");
  });

  it("returns undefined only when neither source knows a path", () => {
    expect(resolveExternalPdfPath(undefined, undefined)).toBeUndefined();
    expect(resolveExternalPdfPath("", "")).toBeUndefined();
  });
});
