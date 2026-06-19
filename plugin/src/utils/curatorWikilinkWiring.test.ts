import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";

// The curator-wikilink post-processor lives in main.ts `onload`, which cannot be
// instantiated under the node test env (no Obsidian Plugin runtime / no DOM).
// Assert the wiring at the source level, mirroring noteLatexCopyWiring.test.ts.
const root = fileURLToPath(new URL("../../", import.meta.url));
const main = readFileSync(join(root, "main.ts"), "utf8");

describe("curator wikilink resolution wiring (main.ts)", () => {
  it("imports the rewrite helper", () => {
    expect(main).toMatch(
      /import \{ rewriteCuratorLinks \} from "\.\/src\/utils\/curatorWikilinks"/
    );
  });

  it("registers a markdown post-processor that rewrites curator links", () => {
    expect(main).toMatch(/registerMarkdownPostProcessor\(\(el\) =>/);
    expect(main).toContain("rewriteCuratorLinks(el, {");
  });

  it("opens the hidden page via openLinkText and checks existence via the vault", () => {
    expect(main).toMatch(
      /open: \(linktext\) => void this\.app\.workspace\.openLinkText\(linktext, "", false\)/
    );
    expect(main).toMatch(
      /exists: \(path\) => this\.app\.vault\.getAbstractFileByPath\(path\) != null/
    );
  });
});
