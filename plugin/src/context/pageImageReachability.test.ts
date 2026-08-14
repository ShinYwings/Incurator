import { describe, expect, it } from "vitest";
import { boundaryConstraints, POPOVER_PROFILE } from "./promptRegistry";
import { contextPriorityInstruction } from "./chatContextPriority";
import {
  buildResolvedReferencesBlock,
  type ResolvedReference,
} from "./crossReferenceResolver";

/**
 * A tool the prompt argues against is a tool that does not exist.
 *
 * v0.55.0 added `read_pdf_page_image`, and shipped it unreachable: three prompt
 * sites steered the model away from it and none mentioned it. The worst was
 * `crossReferenceResolver.ts`'s UNRESOLVED_NOTE, which fires on *exactly* the
 * condition the tool was built for — "commonly a rasterized equation or figure"
 * — and then told the model to describe the target from what it already had.
 *
 * So the headline scenario, "explain equation 29" where equation 29 is a
 * picture, would have produced the same non-answer as before the feature: the
 * resolver finds no text, emits the unresolved block, and the note talks the
 * model out of looking.
 *
 * These assertions drive the exported builders and read their OUTPUT, so a
 * comment cannot satisfy them and a source-scraping regex cannot be fooled by
 * this file's many regex literals.
 */

const MENTIONS_IMAGE_READ = /page as an image|as an image|page image/i;

/** An unresolved pointer — the only input that emits UNRESOLVED_NOTE. */
function unresolvedPointer(): ResolvedReference[] {
  return [
    {
      query: { label: "Eq. (29)", kind: "equation", raw: "Eq. (29)" } as never,
      label: "Eq. (29)",
      confidence: 0,
      method: "unresolved",
    },
  ];
}

describe("the page-image capability is reachable from the prompt", () => {
  it("the unresolved-reference note points at it instead of away from it", () => {
    const block = buildResolvedReferencesBlock(unresolvedPointer());
    // Sanity: this input really does produce the unresolved block.
    expect(block).toContain("<unresolved_cross_references");
    expect(block).toMatch(MENTIONS_IMAGE_READ);

    // The specific regression: the note used to end the search right here.
    expect(block).not.toMatch(/working from the blocks given/);
  });

  it("the pointer instruction does not send the model back to the blocks", () => {
    const instruction = contextPriorityInstruction(true);
    expect(instruction).toMatch(MENTIONS_IMAGE_READ);
    expect(instruction).not.toMatch(
      /keep working from the supplied blocks rather than reading the source file/,
    );
  });

  it("the popover's boundary text declares the image read, not just page-by-number", () => {
    const rules = boundaryConstraints(POPOVER_PROFILE);
    expect(rules).toMatch(MENTIONS_IMAGE_READ);
    // It also must not still claim a single tool now that there are three.
    expect(rules).not.toMatch(/ONLY tool is/);
  });

  it("still says why the text layer can be complete and wrong", () => {
    // Without the reason, "you may read a page as an image" reads as a fallback
    // for scanned documents — and the papers this is for are not scanned.
    const rules = boundaryConstraints(POPOVER_PROFILE);
    expect(rules).toMatch(/equations and figures as pictures|no text|not in that page's text/i);
  });

  it("keeps the boundary itself intact", () => {
    const rules = boundaryConstraints(POPOVER_PROFILE);
    expect(rules).toMatch(/NO filesystem access/);
    expect(rules).toMatch(/NO MCP tools/);
  });
});
