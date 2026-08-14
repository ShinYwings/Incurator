import { describe, expect, it } from "vitest";
import {
  collectBibliography,
  extractCitationNumbers,
  parseBibliography,
  parseBibliographyContinuation,
  resolveCitations,
} from "./citationResolver";

/**
 * v0.56.0 P3 — `[8]` resolved to the paper it names.
 *
 * The user's request was concrete: "popover 질문할때 ... 래퍼런스 예를들어 [8]
 * 적혀있으면 그 논문에 대해 설명하고". Reading a paper means following its
 * citations, and until now `[8]` was just three characters of noise.
 *
 * PLAN §4.8 makes the scoping rule explicit, and it is the whole reason this
 * is tractable: a bare `[N]` is ambiguous with footnotes, markdown reference
 * links, and array indices, so **a citation number that does not resolve
 * against a parsed References section is dropped, not rendered as unresolved**.
 * The bibliography is the disambiguator, not a nice-to-have.
 */

const REFERENCES_PAGE = `
References

[1] R. Hartley and A. Zisserman. Multiple View Geometry in Computer Vision.
    Cambridge University Press, 2003.
[2] J. L. Schonberger and J.-M. Frahm. Structure-from-motion revisited. In
    CVPR, 2016.
[8] S. Liu, Y. Yu, R. Pautrat, M. Pollefeys, and V. Larsson. 3D line mapping
    revisited. In CVPR, 2023.
[9] Y. Furukawa and J. Ponce. Accurate, dense, and robust multiview
    stereopsis. TPAMI, 2010.
`;

describe("parseBibliography", () => {
  it("parses numbered entries and joins their continuation lines", () => {
    const bib = parseBibliography(REFERENCES_PAGE);
    expect(bib.get(8)).toContain("3D line mapping");
    expect(bib.get(8)).toContain("Liu");
    // The continuation line must be folded in, not dropped.
    expect(bib.get(8)).toContain("CVPR, 2023");
    expect(bib.size).toBe(4);
  });

  it("does not treat body text as a bibliography", () => {
    // A page that merely cites things is not a References section. Without
    // this the parser would 'find' a bibliography on every page and the
    // §4.8 disambiguator would stop disambiguating.
    const body = `
      As shown in [8], line mapping benefits from structure. We follow [2]
      for the SfM stage and evaluate against [1].
    `;
    expect(parseBibliography(body).size).toBe(0);
  });

  it("requires the heading, not merely entry-shaped lines", () => {
    // The case above passes even without the heading check, because none of
    // its citations start a line. This one is entry-shaped in every way EXCEPT
    // the heading — an enumerated list, a numbered figure caption block, a
    // changelog. Dropping the heading requirement turns this red.
    const listLikeButNotABibliography = `
[1] first configuration we tried
[2] second configuration we tried
[8] the one that worked
    `;
    expect(parseBibliography(listLikeButNotABibliography).size).toBe(0);
  });

  it("accepts a BIBLIOGRAPHY heading and mixed case", () => {
    expect(parseBibliography("BIBLIOGRAPHY\n[1] A. Author. A title. 1999.").size).toBe(1);
    expect(parseBibliography("Bibliography\n[1] A. Author. A title. 1999.").size).toBe(1);
  });

  it("stops at a following section so appendix text is not absorbed", () => {
    const withAppendix = `${REFERENCES_PAGE}\n\nA. Implementation Details\n\n[99] not a reference\n`;
    const bib = parseBibliography(withAppendix);
    expect(bib.has(99)).toBe(false);
    expect(bib.has(8)).toBe(true);
  });
});

describe("extractCitationNumbers", () => {
  it("extracts a plain citation", () => {
    expect(extractCitationNumbers("as shown in [8], the method").map((c) => c.num)).toEqual([8]);
  });

  it("extracts grouped and ranged citations", () => {
    expect(extractCitationNumbers("prior work [8, 9] and [1-3]").map((c) => c.num))
      .toEqual([8, 9, 1, 2, 3]);
  });

  // ── the three collisions §4.8 names ──────────────────────────────────────
  it("does not extract a footnote marker", () => {
    expect(extractCitationNumbers("see the note[^8] below")).toEqual([]);
  });

  it("does not extract a markdown reference link", () => {
    expect(extractCitationNumbers("see [the paper][8] for detail")).toEqual([]);
  });

  it("does not extract an array index", () => {
    expect(extractCitationNumbers("the value of arr[8] is")).toEqual([]);
    expect(extractCitationNumbers("matrix[0][8] holds")).toEqual([]);
    expect(extractCitationNumbers("compute()[8]")).toEqual([]);
  });

  it("does not extract from inside code", () => {
    // These two are already caught by the index rule (`f` and `y` precede the
    // bracket), so they do NOT prove the code-span guard works...
    expect(extractCitationNumbers("`buf[8]` is the byte")).toEqual([]);
    expect(extractCitationNumbers("```\nx = y[8]\n```")).toEqual([]);

    // ...these do. A bare bracket inside code is preceded by a backtick or a
    // newline, neither of which the index rule rejects. Deleting the code-span
    // guard turns these two red and leaves the two above green.
    expect(extractCitationNumbers("the literal `[8]` in the format string")).toEqual([]);
    expect(extractCitationNumbers("```\nconst x = [8];\n```")).toEqual([]);
  });

  it("ignores an equation label, which is parenthesised not bracketed", () => {
    expect(extractCitationNumbers("as in Eq. (8) above")).toEqual([]);
  });
});

describe("resolveCitations", () => {
  const bib = parseBibliography(REFERENCES_PAGE);

  it("resolves a citation to its bibliography entry", () => {
    const [hit] = resolveCitations("we build on [8] for the line stage", bib);
    expect(hit.num).toBe(8);
    expect(hit.label).toBe("[8]");
    expect(hit.entry).toContain("3D line mapping");
  });

  it("DROPS a citation with no bibliography match, rather than reporting it unresolved", () => {
    // §4.8. An unmatched [42] is far more likely to be an array index or a
    // stray bracket than a citation, and reporting it as an unresolved
    // reference would put noise in front of the model on ordinary prose.
    expect(resolveCitations("the coefficient [42] in the table", bib)).toEqual([]);
  });

  it("keeps the matched ones when a selection mixes matched and unmatched", () => {
    const hits = resolveCitations("compare [8] against [42]", bib);
    expect(hits.map((h) => h.num)).toEqual([8]);
  });

  it("deduplicates a citation repeated in one selection", () => {
    const hits = resolveCitations("[8] improves on [8] again", bib);
    expect(hits.map((h) => h.num)).toEqual([8]);
  });

  it("returns nothing when no bibliography was found", () => {
    expect(resolveCitations("we build on [8]", new Map())).toEqual([]);
  });
});

/**
 * A References section spans pages and prints its heading once.
 *
 * Measured on the motivating paper: p.24 carries the heading and entries 1–28,
 * p.25 and p.26 carry 35 and 32 more entry-shaped lines with no heading at all.
 * Requiring a heading per page finds 28 of ~95 — and `[42]`, a perfectly real
 * citation, would have been silently dropped by §4.8 for "not being in the
 * bibliography".
 */
describe("collectBibliography across pages", () => {
  const headingPage = "References\n[1] A. One. First. 2001.\n[2] B. Two. Second. 2002.";
  const continuation = "[3] C. Three. Third. 2003.\n[4] D. Four. Fourth. 2004.";

  it("continues onto a page that has entries but no heading", () => {
    const bib = collectBibliography([headingPage, continuation]);
    expect([...bib.keys()].sort((a, b) => a - b)).toEqual([1, 2, 3, 4]);
    expect(bib.get(4)).toContain("Fourth");
  });

  it("stops when the numbering restarts — that is a different list", () => {
    // An appendix that happens to use bracketed enumeration must not be
    // absorbed. This is what makes it safe to drop the heading requirement.
    const restart = "[1] not a reference at all\n[2] also not";
    const bib = collectBibliography([headingPage, restart]);
    expect([...bib.keys()].sort((a, b) => a - b)).toEqual([1, 2]);
    expect(bib.get(1)).toContain("First");
  });

  it("stops at the first page that adds nothing", () => {
    const bib = collectBibliography([headingPage, "Appendix A\n\nSome prose.", continuation]);
    expect([...bib.keys()].sort((a, b) => a - b)).toEqual([1, 2]);
  });

  it("skips leading pages until the heading is found", () => {
    const bib = collectBibliography(["body text citing [1] and [2]", headingPage, continuation]);
    expect([...bib.keys()].sort((a, b) => a - b)).toEqual([1, 2, 3, 4]);
  });

  it("the continuation parser alone does not require a heading", () => {
    expect(parseBibliographyContinuation(continuation).size).toBe(2);
    // ...which is exactly why it must never be used on an arbitrary page.
    expect(parseBibliography(continuation).size).toBe(0);
  });
});
