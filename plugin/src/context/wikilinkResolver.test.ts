import { describe, expect, it, vi } from "vitest";
import {
  buildWikilinksBlock,
  extractWikilinks,
  resolveWikilinks,
  sectionUnderHeading,
} from "./wikilinkResolver";

/**
 * A note's `[[link]]` is a paper's `[12]`.
 *
 * Papers have had a citation resolver since v0.56.0: the reader points at a
 * reference, and the pipeline goes and gets it. Notes had nothing. The plugin
 * only ever WROTE wikilinks, as output locators, and never read one as an input —
 * so "what did I conclude in [[Gaussian Splatting]]?" was answered from a title.
 *
 * Same reader action, same document-kind blind spot as the reported bug.
 */
const NOTES: Record<string, string> = {
  "Gaussian Splatting": [
    "---",
    "tags: [graphics]",
    "---",
    "# Gaussian Splatting",
    "Rasterises anisotropic 3D Gaussians instead of marching rays.",
    "",
    "## Method",
    "Each Gaussian carries position, covariance, opacity and SH colour.",
    "",
    "## Limitations",
    "Struggles with view-dependent specular highlights.",
  ].join("\n"),
  NeRF: "# NeRF\nVolume rendering through a coordinate MLP.",
};

const read = vi.fn(async (target: string) =>
  NOTES[target] ? { path: `03_Notes/${target}.md`, text: NOTES[target] } : undefined
);

describe("extracting the links a note makes", () => {
  it("reads plain, aliased, sectioned and embedded forms", () => {
    const links = extractWikilinks(
      "See [[NeRF]], [[Gaussian Splatting|3DGS]], [[Gaussian Splatting#Method]] and ![[NeRF]]."
    );
    expect(links.map((l) => l.target)).toEqual([
      "NeRF",
      "Gaussian Splatting",
      "Gaussian Splatting",
    ]);
    expect(links[1].heading).toBeUndefined();
    expect(links[2].heading).toBe("Method");
  });

  it("returns nothing for text that links nowhere", () => {
    expect(extractWikilinks("just prose, no links")).toEqual([]);
    expect(extractWikilinks("")).toEqual([]);
  });
});

describe("delivering the section a link points into", () => {
  it("returns only the named section, not the whole note", () => {
    const section = sectionUnderHeading(NOTES["Gaussian Splatting"], "Method");
    expect(section).toContain("covariance");
    expect(section).not.toContain("specular highlights");
  });

  it("returns nothing for a heading the note does not have", () => {
    expect(sectionUnderHeading(NOTES["Gaussian Splatting"], "Results")).toBe("");
  });
});

describe("following the links, as the reader would", () => {
  it("answers about a linked note from its content, not its title", async () => {
    const resolved = await resolveWikilinks(
      "what did I conclude in [[Gaussian Splatting]]?",
      read
    );
    expect(resolved).toHaveLength(1);
    expect(resolved[0].text).toContain("anisotropic 3D Gaussians");
    expect(resolved[0].path).toBe("03_Notes/Gaussian Splatting.md");
  });

  it("delivers the section when the link names one", async () => {
    const resolved = await resolveWikilinks("[[Gaussian Splatting#Limitations]]", read);
    expect(resolved[0].text).toContain("specular highlights");
    expect(resolved[0].text).not.toContain("covariance");
  });

  it("falls back to the whole note when the named heading is gone", async () => {
    const resolved = await resolveWikilinks("[[Gaussian Splatting#Ablation]]", read);
    expect(resolved[0].text).toContain("anisotropic 3D Gaussians");
  });

  it("drops a link that does not resolve instead of failing the turn", async () => {
    const resolved = await resolveWikilinks("[[NeRF]] and [[Deleted Note]]", read);
    expect(resolved.map((r) => r.target)).toEqual(["NeRF"]);
  });

  it("survives a reader that throws", async () => {
    const boom = vi.fn(async () => {
      throw new Error("vault unavailable");
    });
    await expect(resolveWikilinks("[[NeRF]]", boom)).resolves.toEqual([]);
  });

  it("bounds how many links one turn follows", async () => {
    const many = "[[a]] [[b]] [[c]] [[d]] [[e]] [[f]]";
    const always = vi.fn(async (t: string) => ({ path: `${t}.md`, text: `body of ${t}` }));
    const resolved = await resolveWikilinks(many, always);
    expect(resolved).toHaveLength(4);
    expect(always).toHaveBeenCalledTimes(4);
  });
});

describe("the context block", () => {
  it("is empty when nothing resolved, so no empty tag reaches the prompt", () => {
    expect(buildWikilinksBlock([])).toBe("");
  });

  it("names the target and carries the text", async () => {
    const block = buildWikilinksBlock(
      await resolveWikilinks("[[Gaussian Splatting#Method]]", read)
    );
    expect(block).toContain('target="Gaussian Splatting#Method"');
    expect(block).toContain("covariance");
  });
});
