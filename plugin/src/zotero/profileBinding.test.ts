import { describe, expect, it } from "vitest";
import {
  resolveZoteroRefreshProfile,
  stampZoteroProfile,
} from "./profileBinding";
import type { ZoteroImportProfile } from "../types";

function profile(name: string, templatePath = `${name}.md`): ZoteroImportProfile {
  return {
    name,
    templatePath,
    outputFolder: "03_Notes",
    outputSubfolder: "",
    outputFilename: "{{title}}",
    assetFolder: "05_Assets",
    assetSubfolder: "{{citekey}}",
    bibliographyStyle: "",
  };
}

describe("Zotero profile binding", () => {
  it("stamps the originating import profile into existing frontmatter", () => {
    expect(stampZoteroProfile("---\ntitle: Paper\n---\n\nBody\n", "Books")).toBe(
      "---\ntitle: Paper\nzotero_profile: \"Books\"\n---\n\nBody\n"
    );
  });

  it("adds frontmatter when the template did not render any", () => {
    expect(stampZoteroProfile("# Paper\n", "Papers")).toBe(
      "---\nzotero_profile: \"Papers\"\n---\n\n# Paper\n"
    );
  });

  it("replaces a stale profile stamp instead of duplicating it", () => {
    expect(stampZoteroProfile("---\nzotero_profile: \"Old\"\ntitle: Paper\n---\nBody", "New")).toBe(
      "---\ntitle: Paper\nzotero_profile: \"New\"\n---\nBody"
    );
  });

  it("uses the stamped profile for refresh and falls back to the first profile", () => {
    const profiles = [profile("Papers"), profile("Books", "book-template.md")];

    expect(resolveZoteroRefreshProfile(profiles, { zotero_profile: "Books" })?.templatePath).toBe(
      "book-template.md"
    );
    expect(resolveZoteroRefreshProfile(profiles, { zotero_profile: "Missing" })?.name).toBe(
      "Papers"
    );
    expect(resolveZoteroRefreshProfile(profiles, {})?.name).toBe("Papers");
  });
});
