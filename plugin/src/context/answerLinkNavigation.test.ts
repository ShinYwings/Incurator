import { describe, expect, it } from "vitest";
import { parseAnswerLinkTarget } from "./answerLinkNavigation";

describe("parseAnswerLinkTarget", () => {
  it("parses markdown page links and plain page labels", () => {
    expect(parseAnswerLinkTarget("#page=604")).toEqual({
      kind: "page",
      pageNum: 604,
      pageKind: "physical",
    });
    expect(parseAnswerLinkTarget("", "p.580")).toEqual({
      kind: "page",
      pageNum: 580,
      pageKind: "printed",
    });
    expect(parseAnswerLinkTarget("", "page 19")).toEqual({
      kind: "page",
      pageNum: 19,
      pageKind: "printed",
    });
  });

  it("parses section links from href or rendered text", () => {
    expect(parseAnswerLinkTarget("#section=A4.2")).toEqual({
      kind: "section",
      sectionNumber: "A4.2",
    });
    expect(parseAnswerLinkTarget("", "Section 19.3")).toEqual({
      kind: "section",
      sectionNumber: "19.3",
    });
    expect(parseAnswerLinkTarget("", "§19.3.4")).toEqual({
      kind: "section",
      sectionNumber: "19.3.4",
    });
  });

  it("ignores ordinary links", () => {
    expect(parseAnswerLinkTarget("https://example.com")).toBeNull();
    expect(parseAnswerLinkTarget("", "Hartley and Zisserman")).toBeNull();
  });
});
