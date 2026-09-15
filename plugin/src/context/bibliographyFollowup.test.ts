import { describe, expect, it } from "vitest";
import { bibliographyFollowupQuestion } from "./bibliographyFollowup";

describe("bibliography source intent on followups", () => {
  it("retains the original reference target for a short author question", () => {
    expect(bibliographyFollowupQuestion("저자 전체 이름은?", "reference 90 제목", true))
      .toContain("reference 90");
  });
  it("does not transfer reference intent across documents or explicit new topics", () => {
    expect(bibliographyFollowupQuestion("저자 이름은?", "References", false)).toBe("저자 이름은?");
    expect(bibliographyFollowupQuestion("Explain equation (3)", "References", true))
      .toBe("Explain equation (3)");
  });
});
