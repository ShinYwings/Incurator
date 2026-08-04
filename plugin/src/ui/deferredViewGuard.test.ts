import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

import { asLoadedExternalPdfView } from "./pdf/externalPdfLeaf";
import { EXTERNAL_PDF_VIEW_TYPE } from "./pdf/externalPdfViewType";

/**
 * v0.41.1 regression: Obsidian >= 1.7.2 restores workspace tabs as *deferred*
 * views. A deferred `leaf.view` reports the real `getViewType()` but is a
 * placeholder object without the concrete view class's methods, so a matching
 * view-type string is NOT proof of class identity.
 *
 * `main.ts` used to cast on the string alone and then call
 * `getRuntimePath()`, throwing `TypeError: t.getRuntimePath is not a function`
 * inside `getLeafFile()`. That function feeds BOTH `updateActiveContext()` and
 * the open-tab inventory, so one deferred PDF tab took down the purple context
 * pins, sidechat Send, and the Quick Query popover together.
 */

const deferredPdfLeafView = () => ({
  // A deferred view answers the type honestly...
  getViewType: () => EXTERNAL_PDF_VIEW_TYPE,
  // ...but carries none of ExternalPdfView's methods.
});

const loadedPdfLeafView = () => ({
  getViewType: () => EXTERNAL_PDF_VIEW_TYPE,
  getRuntimePath: () => "/abs/path/paper.pdf",
  getActivePdfContext: () => ({ pageNum: 3 }),
  getDisplayText: () => "paper.pdf",
  getState: () => ({ currentPage: 3 }),
});

describe("deferred-view guard: asLoadedExternalPdfView", () => {
  it("rejects a deferred view that reports the PDF view type but has no methods", () => {
    expect(asLoadedExternalPdfView(deferredPdfLeafView())).toBeNull();
  });

  it("accepts a fully loaded ExternalPdfView-shaped view", () => {
    const view = loadedPdfLeafView();
    expect(asLoadedExternalPdfView(view)).toBe(view);
  });

  it("rejects a view of an unrelated type", () => {
    expect(asLoadedExternalPdfView({ getViewType: () => "markdown" })).toBeNull();
  });

  it("rejects null/undefined and objects without getViewType", () => {
    expect(asLoadedExternalPdfView(null)).toBeNull();
    expect(asLoadedExternalPdfView(undefined)).toBeNull();
    expect(asLoadedExternalPdfView({})).toBeNull();
  });

  it("rejects a partially loaded view missing one required method", () => {
    // A stale instance from a previous bundle can satisfy the type string and
    // some methods while lacking a newer one; it must still fail closed.
    const partial = {
      getViewType: () => EXTERNAL_PDF_VIEW_TYPE,
      getActivePdfContext: () => ({ pageNum: 1 }),
    };
    expect(asLoadedExternalPdfView(partial)).toBeNull();
  });
});

describe("main.ts must not cast on the view-type string alone", () => {
  const mainSource = () =>
    readFileSync(join(__dirname, "..", "..", "main.ts"), "utf8");

  it("routes every ExternalPdfView access through the guard", () => {
    const src = mainSource();
    // The unsafe pattern is a bare cast guarded only by the type string.
    expect(src).not.toContain("leaf.view as ExternalPdfView");
    expect(src).not.toContain("view as ExternalPdfView");
    expect(src).toContain("asLoadedExternalPdfView");
  });
});
