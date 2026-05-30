import { describe, expect, it } from "vitest";
import { buildZoteroAnnotationBoxStyle } from "./externalPdfAnnotationStyle";

describe("buildZoteroAnnotationBoxStyle", () => {
  it("keeps Zotero annotation boxes empty inside by default", () => {
    const style = buildZoteroAnnotationBoxStyle("note", "#ff0000");

    expect(style.backgroundColor).toBe("transparent");
    expect(style.border).toBe("2px solid #ff0000");
  });

  it("uses yellow as the fallback annotation color", () => {
    const style = buildZoteroAnnotationBoxStyle();

    expect(style.border).toBe("2px solid #ffff00");
  });

  it("handles highlight type", () => {
    const style = buildZoteroAnnotationBoxStyle("highlight", "#ff0000");

    expect(style.border).toBe("none");
    expect(style.backgroundColor).toBe("#ff0000");
    expect(style.mixBlendMode).toBe("multiply");
  });

  it("handles underline type", () => {
    const style = buildZoteroAnnotationBoxStyle("underline", "#00ff00");

    expect(style.border).toBe("none");
    expect(style.borderBottom).toBe("2px solid #00ff00");
  });
});
