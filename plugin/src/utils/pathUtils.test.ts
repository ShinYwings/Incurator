import { describe, it, expect } from "vitest";
import { inferIngestDestination } from "./pathUtils";

describe("inferIngestDestination", () => {
  // ── 03_Notes mirror ──────────────────────────────────────────────────────

  it("mirrors 03_Notes/Foo.md to 04_Resources/Foo", () => {
    expect(inferIngestDestination("03_Notes/Foo.md", "04_Resources")).toBe(
      "04_Resources/Foo"
    );
  });

  it("mirrors 03_Notes/Vision/Foo.md to 04_Resources/Vision/Foo", () => {
    expect(inferIngestDestination("03_Notes/Vision/Foo.md", "04_Resources")).toBe(
      "04_Resources/Vision/Foo"
    );
  });

  it("mirrors deep subfolder structure", () => {
    expect(
      inferIngestDestination("03_Notes/A/B/C/Note.md", "04_Resources")
    ).toBe("04_Resources/A/B/C/Note");
  });

  it("strips .md extension from note name", () => {
    const result = inferIngestDestination("03_Notes/Science/Paper.md", "04_Resources");
    expect(result.endsWith("Paper")).toBe(true);
    expect(result).not.toContain(".md");
  });

  // ── Non-03_Notes paths fall back to configured destination ───────────────

  it("returns configured destination for undefined mdPath", () => {
    expect(inferIngestDestination(undefined, "04_Resources")).toBe("04_Resources");
  });

  it("returns configured destination for 04_Resources path", () => {
    expect(
      inferIngestDestination("04_Resources/file.pdf", "04_Resources")
    ).toBe("04_Resources");
  });

  it("returns configured destination for non-vault path", () => {
    expect(inferIngestDestination("/home/user/doc.pdf", "04_Resources")).toBe(
      "04_Resources"
    );
  });

  // ── Custom default destination ───────────────────────────────────────────

  it("respects custom default destination", () => {
    expect(
      inferIngestDestination("03_Notes/ML/Transformer.md", "04_Resources/Papers")
    ).toBe("04_Resources/Papers/ML/Transformer");
  });

  it("strips trailing slash from configured destination", () => {
    expect(
      inferIngestDestination("03_Notes/Note.md", "04_Resources/")
    ).toBe("04_Resources/Note");
  });

  it("falls back to 04_Resources when configured destination is empty", () => {
    expect(inferIngestDestination(undefined, "")).toBe("04_Resources");
  });
});
