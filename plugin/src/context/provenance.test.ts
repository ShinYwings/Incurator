import { describe, expect, it } from "vitest";
import { buildProvenance, summarizeProvenance } from "./provenance";
import type { ResolvedReference } from "./crossReferenceResolver";

/**
 * PLUGIN_SCHEMA §13.9 — provenance comes from the resolution record.
 *
 * The design this replaces scanned the model's answer for `[[wikilink]]`
 * citations. `quickQueryContext.ts` contains zero `[[`, so that check would
 * have fired "no citation" on every popover answer ever produced. These tests
 * pin the alternative: everything here is derived from what the plugin
 * resolved, so nothing depends on what the model chose to write.
 */

function ref(over: Partial<ResolvedReference> = {}): ResolvedReference {
  return {
    query: { label: "Eq. (29)", kind: "equation", raw: "Eq. (29)", index: 0 } as never,
    label: "Eq. (29)",
    confidence: 0.9,
    method: "explicit-page",
    ...over,
  };
}

describe("buildProvenance", () => {
  it("names the page a reference was read from", () => {
    const { items } = buildProvenance([ref({ targetPage: 11 })]);
    expect(items).toEqual([
      { label: "Eq. (29)", origin: "page", detail: "p.11" },
    ]);
  });

  it("reports an unresolved pointer as not retrieved, never as absent", () => {
    // The distinction is contractual: the popover searches only loaded pages,
    // so "we did not reach it" is what the code can support. "The paper does
    // not contain it" is a claim it cannot.
    const { items, hasUnresolved } = buildProvenance([ref({ method: "unresolved" })]);
    expect(items[0].detail).toBe("not retrieved");
    expect(items[0].origin).toBe("unresolved");
    expect(hasUnresolved).toBe(true);
    expect(items[0].detail).not.toMatch(/absent|does not exist|not in the paper/i);
  });

  it("says 'found by search' rather than naming the algorithm", () => {
    const { items } = buildProvenance([ref({ method: "bm25-object", targetPage: 7 })]);
    expect(items[0].detail).toContain("found by search");
    expect(items[0].detail).not.toMatch(/bm25/i);
  });

  it("omits a reference folded into a sibling, so one lookup shows one source", () => {
    const { items } = buildProvenance([
      ref({ label: "Section 11.1.2", targetPage: 281 }),
      ref({ label: "p281", consumedBySibling: true }),
    ]);
    expect(items.map((i) => i.label)).toEqual(["Section 11.1.2"]);
  });

  it("condenses a citation to author and year", () => {
    const { items } = buildProvenance(
      [],
      [
        {
          num: 8,
          label: "[8]",
          entry:
            "S. Liu, Y. Yu, R. Pautrat, M. Pollefeys, and V. Larsson. 3D line mapping revisited. In CVPR, 2023.",
        },
      ]
    );
    expect(items[0]).toEqual({
      label: "[8]",
      origin: "bibliography",
      detail: "Liu et al., 2023",
    });
  });

  it("takes the surname when the bibliography spells names in full", () => {
    // Caught by running against the real paper, not by the synthetic cases
    // above: this bibliography writes "Hichem Abdellali, ..." rather than
    // "H. Abdellali, ...", and taking the first word gave the GIVEN name.
    const { items } = buildProvenance(
      [],
      [
        {
          num: 1,
          label: "[1]",
          entry:
            "Hichem Abdellali, Robert Frohlich, Viktor Vilagos, and Zoltan Kato. L2d2: Learnable line detector. In ICCV, 2021.",
        },
        {
          num: 8,
          label: "[8]",
          entry: "Adrien Bartoli and Peter Sturm. Structure-from-motion using lines. 2005.",
        },
      ]
    );
    expect(items[0].detail).toBe("Abdellali et al., 2021");
    expect(items[1].detail).toBe("Bartoli et al., 2005");
  });

  it("does not say 'et al.' for a single author", () => {
    const { items } = buildProvenance(
      [],
      [{ num: 3, label: "[3]", entry: "K. Levenberg. A method for solving problems. 1944." }]
    );
    expect(items[0].detail).toBe("Levenberg, 1944");
  });

  it("is empty for a turn that resolved nothing", () => {
    const record = buildProvenance([], []);
    expect(record.items).toEqual([]);
    expect(record.hasUnresolved).toBe(false);
  });
});

describe("summarizeProvenance", () => {
  it("returns nothing when nothing resolved, so no empty chrome is shown", () => {
    expect(summarizeProvenance(buildProvenance([], []))).toBe("");
  });

  it("lists each lookup with where it came from", () => {
    const line = summarizeProvenance(
      buildProvenance(
        [ref({ targetPage: 11 })],
        [{ num: 8, label: "[8]", entry: "S. Liu and V. Larsson. A paper. 2023." }]
      )
    );
    expect(line).toBe("Eq. (29) — p.11 · [8] — Liu et al., 2023");
  });
});
