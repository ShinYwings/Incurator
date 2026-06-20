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

describe("Convert-to-LaTeX fast/light model (v0.21.0)", () => {
  it("overrides the model only for Ollama with a non-empty latexModel", () => {
    expect(source).toContain("this.plugin.settings.latexModel?.trim()");
    expect(source).toContain('this.plugin.settings.provider === "ollama"');
    expect(source).toContain("complete(messages, { model: latexModel })");
    // Non-Ollama / unset falls back to the plain main-model call.
    expect(source).toContain("await this.plugin.llmClient.complete(messages)");
  });

  it("names the resolved model in the failure notice for an actionable ollama pull hint", () => {
    expect(source).toContain("ollama pull ${resolvedModel");
  });
});
