import { describe, it, expect } from "vitest";
import { parseZoteroLink } from "./zoteroUtils";

describe("zoteroUtils", () => {
  it("should parse a valid zotero link without page", () => {
    const info = parseZoteroLink("zotero://open-pdf/library/items/PZBCB9LJ");
    expect(info).not.toBeNull();
    expect(info?.attachmentKey).toBe("PZBCB9LJ");
    expect(info?.pageNum).toBeUndefined();
  });

  it("should parse a valid zotero link with page and annotation", () => {
    const info = parseZoteroLink("zotero://open-pdf/library/items/PZBCB9LJ?page=5&annotation=ZJKGLJQ6");
    expect(info).not.toBeNull();
    expect(info?.attachmentKey).toBe("PZBCB9LJ");
    expect(info?.pageNum).toBe(5);
    // The annotation key must survive so the view can jump to it (#1d).
    expect(info?.annotationKey).toBe("ZJKGLJQ6");
  });

  it("should parse a parent-item select link (no annotation/page)", () => {
    // zotero_app_url carries the parent item key; backend resolves it to the
    // child PDF attachment (#1b), then annotations jump via the child key (#1d).
    const info = parseZoteroLink("zotero://select/library/items/PARENT01");
    expect(info).not.toBeNull();
    expect(info?.attachmentKey).toBe("PARENT01");
    expect(info?.annotationKey).toBeUndefined();
  });

  it("should return null if viewer=zotero is present", () => {
    const info = parseZoteroLink("zotero://open-pdf/library/items/PZBCB9LJ?page=5&viewer=zotero");
    expect(info).toBeNull();
  });

  it("should parse a valid zotero link with mixed case", () => {
    const info = parseZoteroLink("ZOTERO://open-pdf/library/items/PzbcB9LJ?page=10");
    expect(info).not.toBeNull();
    expect(info?.attachmentKey).toBe("PzbcB9LJ");
    expect(info?.pageNum).toBe(10);
  });

  it("should return null for invalid zotero link", () => {
    const info = parseZoteroLink("https://google.com");
    expect(info).toBeNull();
  });
});
