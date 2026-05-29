import { describe, expect, it } from "vitest";
import { buildZoteroAnnotationBoxStyle } from "./externalPdfAnnotationStyle";

describe("buildZoteroAnnotationBoxStyle", () => {
  it("keeps Zotero annotation boxes empty inside", () => {
    const style = buildZoteroAnnotationBoxStyle("#ff0000");

    expect(style.backgroundColor).toBe("transparent");
    expect(style.border).toBe("2px solid #ff0000");
  });

  it("uses yellow as the fallback annotation color", () => {
    const style = buildZoteroAnnotationBoxStyle();

    expect(style.border).toBe("2px solid #ffff00");
  });
});
