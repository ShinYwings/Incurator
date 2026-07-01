import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Plan G P0/P4 characterization (Arena red-team C1). The external-PDF persisted
// state format and its load-time retention contract live in the P4 registry
// extraction. `persistDocs`/`loadPersistedDocs` are module-private and run
// against localStorage, so this pins the format as a source-string contract
// (project convention for code that can't render/run under node vitest).
const source = readFileSync(join(__dirname, "externalPdfRegistry.ts"), "utf-8");
const mainSource = readFileSync(join(__dirname, "../../main.ts"), "utf-8");

describe("external-PDF persisted state format (P0 characterization)", () => {
  it("uses the stable localStorage key", () => {
    expect(source).toContain(
      'const STORAGE_KEY = "incurator-obsidian-agent-external-pdfs"'
    );
    expect(source).toContain("localStorage.getItem(STORAGE_KEY)");
    expect(source).toContain("localStorage.setItem(STORAGE_KEY,");
  });

  it("persists portable identity and never the resolved path", () => {
    expect(source).toContain("id: doc.id,");
    expect(source).toContain("name: doc.name,");
    expect(source).toContain("zoteroAttachmentKey: doc.zoteroAttachmentKey");
    expect(source).toContain("externalRef: doc.externalRef");
    // The toPersist mapping block inside persistDocs must not include path.
    // (loadPersistedDocs restores path into in-memory registry only.)
    const persistDocsBlock = source.slice(source.indexOf("function persistDocs"), source.indexOf("JSON.stringify(toPersist)"));
    expect(persistDocsBlock).not.toContain("path:");
    expect(source).toContain("JSON.stringify(toPersist)");
  });

  it("retains path-bearing docs at load time via isRetainablePersistedDoc", () => {
    // Load-time retention delegates to the pure, unit-tested predicate
    // (see externalPdfState.test.ts) rather than existsSync, which would race
    // Obsidian startup. P4 must preserve this delegation.
    expect(source).toContain("isRetainablePersistedDoc(doc)");
  });

  it("rewrites legacy localStorage entries without their resolved path", () => {
    expect(source).toContain("migrated ||= Boolean(doc.path)");
    expect(source).toContain("if (migrated)");
    expect(source).toContain("persistDocs(map)");
  });

  it("builds the in-memory doc map at module load", () => {
    expect(source).toContain("const externalPdfDocs = loadPersistedDocs();");
  });

  it("restores Zotero leaves by key without persisting a resolved path", () => {
    expect(mainSource).not.toContain("replaceExternalPdfDocPath(existingState.docId, pdfPath);");
    expect(mainSource).toContain("l.view.getState()?.zoteroAttachmentKey === effectiveKey");
    expect(source).not.toContain("resolveZoteroAttachmentPath");
    expect(source).not.toContain('from "os"');
  });
});
