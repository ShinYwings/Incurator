import { readFileSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";

/**
 * Both surfaces must actually follow links, not merely be able to.
 *
 * A resolver nobody calls fixes nothing, and this repo has shipped that shape
 * before — v0.75.0 put the persona in the backend pack and stopped there, so the
 * formatter never rendered it and the claim that "the assistant knows the voice
 * the vault was set up for" was false for a release.
 *
 * The reader's action is the same in both places: they point at a note and ask
 * about it. So the check is the same in both places.
 */
const SRC = join(__dirname, "..");

function read(rel: string): string {
  return readFileSync(join(SRC, rel), "utf-8");
}

describe("wikilink following is wired into both surfaces", () => {
  it("the popover resolves links before building its turn", () => {
    const src = read("ui/quickQueryPopover.ts");
    expect(src).toContain("resolveWikilinks");
    expect(src).toContain("buildWikilinksBlock");
    // The block has to reach the prompt, not just be computed.
    expect(src).toContain("resolvedWikilinksBlock");
  });

  it("the chat sidebar resolves links before building its turn", () => {
    const src = read("ui/chat/ChatSidebarView.ts");
    expect(src).toContain("resolveWikilinks");
    expect(src).toContain("buildWikilinksBlock");
    expect(src).toContain("systemText += `\\n\\n${wikilinksBlock}`");
  });

  it("the popover threads the block into the assembled context", () => {
    const src = read("context/quickQueryContext.ts");
    expect(src).toContain("resolvedWikilinksBlock");
    // Emitted in the content array, beside the other resolved-pointer blocks.
    expect(src).toContain('args.resolvedWikilinksBlock ?? ""');
  });

  it("both surfaces read the note through the vault's own link rules", () => {
    for (const f of ["ui/quickQueryPopover.ts", "ui/chat/ChatSidebarView.ts"]) {
      expect(read(f), f).toContain("readVaultNote");
    }
    // `getFirstLinkpathDest` is what makes a link the reader can click resolve
    // here too — shortest-path matching and folder-relative resolution.
    expect(readFileSync(join(SRC, "..", "main.ts"), "utf-8")).toContain(
      "getFirstLinkpathDest"
    );
  });
});
