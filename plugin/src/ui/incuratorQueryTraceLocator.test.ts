import { describe, expect, it } from "vitest";
import { locatorTarget } from "./incuratorQueryTraceLocator";

// Behavioral contract for ContextService evidence-locator open-target
// resolution (Plan F P6, Sources & Trace). Exercises the pure decision instead
// of grepping the source string.
describe("locatorTarget", () => {
  it("returns null for an explicitly unavailable locator", () => {
    expect(
      locatorTarget({ locator_status: "unavailable", relpath: "01_Contexts/CTX.md" })
    ).toBeNull();
  });

  it("returns null when there is neither a relpath nor an external_uri", () => {
    expect(locatorTarget({ source_kind: "note" })).toBeNull();
  });

  it("opens a registered/vault PDF in Obsidian, jumping to the cited page", () => {
    // In-vault PDF: relpath present, no external_uri. Obsidian's native viewer
    // is reached by the #page=N anchor.
    const target = locatorTarget({
      source_kind: "vault_pdf",
      relpath: "05_Assets/resnet.pdf",
      page_number: 7,
    });
    expect(target).toEqual({
      kind: "vault",
      label: "05_Assets/resnet.pdf p.7#page=7",
      linkpath: "05_Assets/resnet.pdf#page=7",
    });
  });

  it("opens an unregistered external Reference Mode PDF in the plugin viewer at the cited page", () => {
    // Reference Mode source: external_uri is the real file on disk; relpath is
    // only an in-vault stub and must not shadow it. The plugin's external PDF
    // viewer (kind external_pdf) carries the page so it can scroll there.
    const target = locatorTarget({
      source_kind: "vault_pdf",
      relpath: "04_Resources/ref-stub.md",
      external_uri: "/Users/shin/Zotero/storage/ABCD/he2016.pdf",
      page_number: 3,
    });
    expect(target).toEqual({
      kind: "external_pdf",
      label: "he2016.pdf p.3",
      linkpath: "/Users/shin/Zotero/storage/ABCD/he2016.pdf",
      page: 3,
    });
  });

  it("detects a PDF by extension even when source_kind is not vault_pdf", () => {
    const target = locatorTarget({
      external_uri: "/tmp/notes/paper.pdf",
    });
    expect(target?.kind).toBe("external_pdf");
    expect(target?.linkpath).toBe("/tmp/notes/paper.pdf");
  });

  it("prefers external_uri over the in-vault stub for a non-PDF reference and uses the system handler", () => {
    // A non-PDF external reference: the stub relpath is non-null but must lose
    // to external_uri. kind external -> opened via the OS handler.
    const target = locatorTarget({
      relpath: "04_Resources/ref-stub.md",
      external_uri: "https://example.com/article",
    });
    expect(target).toEqual({
      kind: "external",
      label: "https://example.com/article",
      linkpath: "https://example.com/article",
    });
  });

  it("treats a URL-scheme external_uri as a non-file external reference even with a .pdf suffix in the path", () => {
    // isFilePath is false for a real URL scheme, so a remote .pdf opens through
    // the system handler, not the local external PDF viewer.
    const target = locatorTarget({
      external_uri: "https://example.com/he2016.pdf",
    });
    expect(target?.kind).toBe("external");
    expect(target?.linkpath).toBe("https://example.com/he2016.pdf");
  });

  it("anchors a vault note to its block id when present", () => {
    const target = locatorTarget({
      source_kind: "note",
      relpath: "03_Notes/idea.md",
      block_id: "abc123",
    });
    expect(target).toEqual({
      kind: "vault",
      label: "03_Notes/idea.md#^abc123",
      linkpath: "03_Notes/idea.md#^abc123",
    });
  });

  it("anchors a vault note to its heading when there is no block id", () => {
    const target = locatorTarget({
      relpath: "03_Notes/idea.md",
      heading: "Residual Learning",
    });
    expect(target).toEqual({
      kind: "vault",
      label: "03_Notes/idea.md#Residual Learning",
      linkpath: "03_Notes/idea.md#Residual Learning",
    });
  });

  it("returns a bare vault link when no anchor or page applies", () => {
    expect(locatorTarget({ relpath: "02_Atoms/ATM.md" })).toEqual({
      kind: "vault",
      label: "02_Atoms/ATM.md",
      linkpath: "02_Atoms/ATM.md",
    });
  });
});
