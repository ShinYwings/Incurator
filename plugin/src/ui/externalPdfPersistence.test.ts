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

  it("persists only id/name/path per entry as [id, doc] pairs", () => {
    // The serialized shape is Array<[string, {id,name,path}]>; the persisted doc
    // must carry exactly these three fields (no view/render state leaks in).
    expect(source).toContain("id: doc.id,");
    expect(source).toContain("name: doc.name,");
    expect(source).toContain("path: doc.path,");
    expect(source).toContain("JSON.stringify(toPersist)");
  });

  it("retains path-bearing docs at load time via isRetainablePersistedDoc", () => {
    // Load-time retention delegates to the pure, unit-tested predicate
    // (see externalPdfState.test.ts) rather than existsSync, which would race
    // Obsidian startup. P4 must preserve this delegation.
    expect(source).toContain("isRetainablePersistedDoc(doc)");
  });

  it("builds the in-memory doc map at module load", () => {
    expect(source).toContain("const externalPdfDocs = loadPersistedDocs();");
  });

  it("replaces stale persisted doc paths through the registry boundary", () => {
    expect(source).toContain("export function replaceExternalPdfDocPath(");
    expect(source).toContain("if (!current || current.path === resolvedPath) return current;");
    expect(source).toContain("const next = { ...current, path: resolvedPath };");
    expect(source).toContain("putExternalPdfDoc(next);");
  });

  it("refreshes a Zotero leaf's persisted path when the attachment resolves elsewhere", () => {
    expect(mainSource).toContain("replaceExternalPdfDocPath(existingState.docId, pdfPath);");
    expect(mainSource).toContain("l.view.getState()?.zoteroAttachmentKey === effectiveKey");
    expect(mainSource).toContain("path: pdfPath,");
  });
});
