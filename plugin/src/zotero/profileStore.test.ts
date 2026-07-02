import { describe, expect, it } from "vitest";

import type { ZoteroImportProfile } from "../types";
import {
  ZOTERO_PROFILES_PATH,
  extractLegacyZoteroProfiles,
  normalizeZoteroProfilesFile,
  parseZoteroProfilesFile,
} from "./profileStore";

function profile(name: string): ZoteroImportProfile {
  return {
    name,
    templatePath: "00_System/templates/zotero.md",
    outputFolder: "03_Notes/Papers",
    outputSubfolder: "",
    outputFilename: "{{title}}",
    assetFolder: "05_Assets",
    assetSubfolder: "{{citekey}}",
    bibliographyStyle: "apa",
    lastUsedAt: 1_700_000_000_000,
  };
}

describe("normalizeZoteroProfilesFile", () => {
  it("passes a well-formed file through", () => {
    const raw = { profiles: [profile("A")], recentItems: ["KEY1", "KEY2"] };
    const norm = normalizeZoteroProfilesFile(raw);
    expect(norm.profiles).toHaveLength(1);
    expect(norm.profiles[0].name).toBe("A");
    expect(norm.recentItems).toEqual(["KEY1", "KEY2"]);
  });

  it("recovers an empty file from malformed input", () => {
    for (const bad of [null, undefined, 42, "junk", [], {}]) {
      const norm = normalizeZoteroProfilesFile(bad);
      expect(norm.profiles).toEqual([]);
      expect(norm.recentItems).toEqual([]);
    }
  });

  it("drops non-object profile entries and non-string recent keys", () => {
    const norm = normalizeZoteroProfilesFile({
      profiles: [profile("A"), null, "junk", 7],
      recentItems: ["OK", 3, null, "ALSO"],
    });
    expect(norm.profiles.map((p) => p.name)).toEqual(["A"]);
    expect(norm.recentItems).toEqual(["OK", "ALSO"]);
  });

  it("drops profile entries without a string name (PR #78 review)", () => {
    // {} and name-less/typed-wrong objects are not valid ZoteroImportProfiles —
    // they would render as empty dropdown entries or crash name-dependent code.
    const norm = normalizeZoteroProfilesFile({
      profiles: [profile("A"), {}, { name: 42 }, { templatePath: "x.md" }, { name: null }],
      recentItems: [],
    });
    expect(norm.profiles.map((p) => p.name)).toEqual(["A"]);
  });

  it("keeps a profile whose name is an empty string (settings-UI rename edge)", () => {
    // The settings UI allows blanking a name and renders a "Profile N" fallback;
    // normalization must not destroy such a real profile.
    const norm = normalizeZoteroProfilesFile({
      profiles: [{ ...profile("A"), name: "" }],
      recentItems: [],
    });
    expect(norm.profiles).toHaveLength(1);
  });

  it("caps recentItems at 50 (LRU contract, PLUGIN_SCHEMA)", () => {
    const norm = normalizeZoteroProfilesFile({
      profiles: [],
      recentItems: Array.from({ length: 80 }, (_, i) => `K${i}`),
    });
    expect(norm.recentItems).toHaveLength(50);
    expect(norm.recentItems[0]).toBe("K0"); // newest-first order preserved
  });
});

describe("extractLegacyZoteroProfiles", () => {
  it("returns the legacy data.json fields when profiles exist", () => {
    const legacy = extractLegacyZoteroProfiles({
      zoteroProfiles: [profile("Legacy")],
      recentZoteroItems: ["KEY9"],
    });
    expect(legacy).not.toBeNull();
    expect(legacy!.profiles[0].name).toBe("Legacy");
    expect(legacy!.recentItems).toEqual(["KEY9"]);
  });

  it("returns non-null when only recent items exist", () => {
    const legacy = extractLegacyZoteroProfiles({
      zoteroProfiles: [],
      recentZoteroItems: ["KEY1"],
    });
    expect(legacy).not.toBeNull();
    expect(legacy!.profiles).toEqual([]);
    expect(legacy!.recentItems).toEqual(["KEY1"]);
  });

  it("returns null when there is nothing to migrate", () => {
    expect(extractLegacyZoteroProfiles({})).toBeNull();
    expect(
      extractLegacyZoteroProfiles({ zoteroProfiles: [], recentZoteroItems: [] })
    ).toBeNull();
    expect(
      extractLegacyZoteroProfiles({
        zoteroProfiles: undefined,
        recentZoteroItems: undefined,
      })
    ).toBeNull();
  });
});

describe("ZOTERO_PROFILES_PATH", () => {
  it("lives in .curator so Syncthing carries it (like sessions.json)", () => {
    expect(ZOTERO_PROFILES_PATH).toBe(".curator/zotero_profiles.json");
  });
});

describe("parseZoteroProfilesFile", () => {
  it("returns null for corrupted (non-JSON) content — never an empty store", () => {
    // PR #78 review: a corrupted-but-existing file must be distinguishable from
    // a missing one, so the caller can refuse to mark profiles loaded and never
    // overwrite the recoverable file with an empty list.
    for (const corrupt of ["", "{truncated", "not json at all", '{"profiles": [']) {
      expect(parseZoteroProfilesFile(corrupt)).toBeNull();
    }
  });

  it("parses and normalizes valid JSON content", () => {
    const store = parseZoteroProfilesFile(
      JSON.stringify({ profiles: [profile("A")], recentItems: ["K1"] })
    );
    expect(store).not.toBeNull();
    expect(store!.profiles[0].name).toBe("A");
    expect(store!.recentItems).toEqual(["K1"]);
  });

  it("degrades valid JSON with a wrong shape to an empty store (not null)", () => {
    // Shape damage is recoverable data-loss-free: normalization applies, and
    // the parse did not fail, so the caller may treat the store as loaded.
    const store = parseZoteroProfilesFile('{"unexpected": true}');
    expect(store).toEqual({ profiles: [], recentItems: [] });
  });
});
