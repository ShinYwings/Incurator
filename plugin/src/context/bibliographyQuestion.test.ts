import { describe, expect, it } from "vitest";
import {
  BIBLIOGRAPHY_HEADING,
  asksAboutBibliography,
  collectBibliography,
} from "./citationResolver";

/**
 * Reported 2026-08-31: the user asked the Quick Query popover for a reference's
 * title while reading a paper. The answer was in that paper's own last pages.
 * The popover returned nothing at all.
 *
 * Two reasons, both here. The popover only ever fed the highlighted SELECTION
 * into citation resolution, never the typed question — so a question that names
 * a reference without the reader re-selecting the bracket resolved nothing. And
 * the bibliography parser only recognised English headings, so a paper headed
 * `참고문헌` had no bibliography as far as the plugin was concerned even with the
 * page text already in memory.
 */
describe("a question that asks about the bibliography is recognised", () => {
  it("recognises the ask in the languages this vault actually holds", () => {
    for (const q of [
      "what is the title of reference 12?",
      "reference 12의 제목이 뭐야?",
      "참고문헌 12번 제목 알려줘",
      "이 논문 레퍼런스 목록 보여줘",
      "give me the bibliography entry for [12]",
      "citation 4 は何の論文ですか",
      "参考文献の12番は?",
    ]) {
      expect(asksAboutBibliography(q), q).toBe(true);
    }
  });

  it("does not fire on questions that are about the paper's argument", () => {
    for (const q of [
      "what does figure 3 show?",
      "이 수식 설명해줘",
      "summarise section 4",
      "왜 z=0 평면에서 최적화했어?",
      "what is the reference frame of the camera?",
    ]) {
      expect(asksAboutBibliography(q), q).toBe(false);
    }
  });

  it("ignores an empty or missing question", () => {
    expect(asksAboutBibliography("")).toBe(false);
    expect(asksAboutBibliography(undefined as unknown as string)).toBe(false);
  });
});

describe("the bibliography heading is not English-only", () => {
  it("matches the headings a multilingual library actually uses", () => {
    for (const heading of [
      "References",
      "BIBLIOGRAPHY",
      "Works Cited",
      "참고문헌",
      "참 고 문 헌",
      "参考文献",
      "引用文献",
    ]) {
      expect(BIBLIOGRAPHY_HEADING.test(heading), heading).toBe(true);
    }
  });

  it("finds entries under a Korean heading", () => {
    const pages = [
      "본문입니다.",
      "참고문헌\n[1] Mildenhall et al. NeRF: Representing Scenes as Neural Radiance Fields.\n[2] Kerbl et al. 3D Gaussian Splatting.",
    ];
    const bib = collectBibliography(pages);
    expect(bib.get(1)).toContain("NeRF");
    expect(bib.get(2)).toContain("Gaussian Splatting");
  });
});
