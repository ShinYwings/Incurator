import { describe, expect, it, vi } from "vitest";

vi.mock("obsidian", () => ({
  moment: (value: string) => ({
    format: (fmt: string) => {
      if (fmt === "YYYY") return value.slice(0, 4);
      return value;
    },
  }),
}));

import { sanitizePathSegment, TemplateRenderer } from "./templateRenderer";

describe("TemplateRenderer", () => {
  it("renders Zotero-friendly filters in strings", async () => {
    const renderer = new TemplateRenderer({} as any);
    const out = await renderer.renderString(
      "{{ creators | firstAuthorLast }}_{{ date | format('YYYY') }}_{{ tags | joinTags('; ') }}",
      {
        creators: [{ firstName: "Ada", lastName: "Lovelace" }],
        date: "1843-01-01",
        tags: [{ tag: "notes" }, "math"],
      }
    );

    expect(out).toBe("Lovelace_1843_notes; math");
  });

  it("sanitizes path segments with the pathSafe filter", async () => {
    const renderer = new TemplateRenderer({} as any);
    await expect(
      renderer.renderString("{{ title | pathSafe }}", { title: "A/B:C*D" })
    ).resolves.toBe("A-B-C-D");
  });

  it("exposes path segment sanitization for callers", () => {
    expect(sanitizePathSegment("  A/B:C*D  ")).toBe("A-B-C-D");
  });
});
