import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(join(__dirname, "externalPdfView.ts"), "utf-8");

describe("ExternalPdfView device-portable restore contract", () => {
  it("re-resolves Zotero-backed restored views before trusting synced absolute paths", () => {
    expect(source).toContain("resolvePortableStatePath");
    expect(source).toContain("resolveAssetSource");
    expect(source).toContain("zoteroAttachmentKey");
    expect(source).toContain("resolveZoteroViaBackend");
    expect(source).toContain("resolveZoteroLocally");
    expect(source).toContain("return resolved.absPath || hintedPath");
    expect(source).toContain("path: resolvedPath");
  });
});

describe("Convert-to-LaTeX (v0.22.0: latexModel setting removed)", () => {
  it("no longer references the removed latexModel plugin setting", () => {
    expect(source).not.toContain("settings.latexModel");
    expect(source).not.toContain("ollama pull ${resolvedModel");
  });

  it("routes the conversion through the backend PDF extraction model", () => {
    expect(source).toContain("this.plugin.incuratorClient.transcribePdfRegion({ text: rawText })");
    expect(source).not.toContain("this.plugin.llmClient.complete");
  });
});
