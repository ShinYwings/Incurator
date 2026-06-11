import { describe, expect, it, vi } from "vitest";

// assetLocalization transitively imports templateRenderer → obsidian; mock it so
// the node test env can load the pure helpers (mirrors templateRenderer.test).
vi.mock("obsidian", () => ({ moment: (value: string) => ({ format: () => value }) }));

import { joinVaultPath, resolveProfileAssetSpec } from "./assetLocalization";
import type { ZoteroImportProfile } from "../types";

function profile(overrides: Partial<ZoteroImportProfile>): ZoteroImportProfile {
  return {
    name: "p",
    templatePath: "t.md",
    outputFolder: "04_Resources",
    outputSubfolder: "",
    outputFilename: "{{title}}",
    assetFolder: "05_Assets",
    assetSubfolder: "{{citekey}}",
    bibliographyStyle: "",
    ...overrides,
  };
}

describe("resolveProfileAssetSpec", () => {
  it("uses the modern assetFolder/assetSubfolder when present", () => {
    expect(
      resolveProfileAssetSpec(profile({ assetFolder: "05_Assets/Zotero Assets", assetSubfolder: "{{citekey}}" }))
    ).toEqual({ assetFolder: "05_Assets/Zotero Assets", assetSubfolder: "{{citekey}}" });
  });

  it("defaults a blank assetSubfolder to {{citekey}}", () => {
    expect(resolveProfileAssetSpec(profile({ assetFolder: "05_Assets", assetSubfolder: "" })))
      .toEqual({ assetFolder: "05_Assets", assetSubfolder: "{{citekey}}" });
  });

  it("migrates a legacy imageFolder into folder + subfolder (the reload bug)", () => {
    // The reload command read this deprecated field; an old profile that only has
    // imageFolder must still localize to a vault-relative folder, not absolute.
    const p = profile({ assetFolder: undefined as unknown as string, imageFolder: "05_Assets/Zotero Assets/Vision/hartley" });
    expect(resolveProfileAssetSpec(p)).toEqual({
      assetFolder: "05_Assets/Zotero Assets/Vision",
      assetSubfolder: "hartley",
    });
  });

  it("falls back to 05_Assets/{{citekey}} when neither modern nor legacy is set", () => {
    const p = profile({ assetFolder: undefined as unknown as string, imageFolder: undefined });
    expect(resolveProfileAssetSpec(p)).toEqual({ assetFolder: "05_Assets", assetSubfolder: "{{citekey}}" });
  });
});

describe("joinVaultPath", () => {
  it("joins parts, drops empties, collapses duplicate slashes", () => {
    expect(joinVaultPath("05_Assets", "hartley")).toBe("05_Assets/hartley");
    expect(joinVaultPath("05_Assets/", "/hartley")).toBe("05_Assets/hartley");
    expect(joinVaultPath("05_Assets", "")).toBe("05_Assets");
    expect(joinVaultPath("", "")).toBe("");
  });
});
