import { describe, expect, it, vi } from "vitest";
import { resolveSelectionCitations } from "./citationContext";

/**
 * The reported failure, end to end.
 *
 * 2026-08-31: reading a paper in the Quick Query popover, the user asked for a
 * reference's title. The title was in that paper's own last pages. They got
 * nothing — the model, given no bibliography and told it had tools it did not
 * have, reached for a URL tool it was not allowed to use, and the turn died.
 *
 * These exercise the real resolver against a real fake document, not the shape
 * of a dict.
 */
const PAPER = [
  "1 Introduction. We build on [12] and on the splatting line of work.",
  "2 Method. Rays are optimised on the z=0 view plane.",
  "References\n[11] Barron et al. Mip-NeRF 360: Unbounded Anti-Aliased Neural Radiance Fields.\n[12] Kerbl et al. 3D Gaussian Splatting for Real-Time Radiance Field Rendering.\n[13] Mildenhall et al. NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis.",
];

function fetcher() {
  return vi.fn(async (pageNum: number) => PAPER[pageNum - 1]);
}

const SOURCE = { documentId: "paper-1", pageCount: PAPER.length };

describe("asking the popover about a reference in the open paper", () => {
  it("answers a typed question with no selection at all", async () => {
    const citations = await resolveSelectionCitations(
      "",
      SOURCE,
      fetcher(),
      "reference 12의 제목이 뭐야?"
    );
    const entries = citations.map((c) => c.entry).join("\n");
    expect(entries).toContain("3D Gaussian Splatting");
  });

  it("answers the same question asked in English", async () => {
    const citations = await resolveSelectionCitations(
      "",
      SOURCE,
      fetcher(),
      "what is the title of reference 12?"
    );
    expect(citations.map((c) => c.entry).join("\n")).toContain(
      "3D Gaussian Splatting"
    );
  });

  it("hands over the list when the ask names no number", async () => {
    const citations = await resolveSelectionCitations(
      "",
      SOURCE,
      fetcher(),
      "이 논문 참고문헌 목록 보여줘"
    );
    expect(citations.length).toBe(3);
    expect(citations.map((c) => c.entry).join("\n")).toContain("Mip-NeRF 360");
  });

  it("still resolves from a selection when the question says nothing", async () => {
    const citations = await resolveSelectionCitations(
      "we build on [12] and on the splatting line",
      SOURCE,
      fetcher(),
      "explain this"
    );
    expect(citations).toHaveLength(1);
    expect(citations[0].entry).toContain("3D Gaussian Splatting");
  });

  it("does not fetch the document for a question about the argument", async () => {
    const fetch = fetcher();
    const citations = await resolveSelectionCitations(
      "",
      SOURCE,
      fetch,
      "why optimise on the z=0 view plane?"
    );
    expect(citations).toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not fetch for a question that merely says the word reference", async () => {
    const fetch = fetcher();
    await resolveSelectionCitations(
      "",
      SOURCE,
      fetch,
      "what is the reference frame of the camera?"
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});
