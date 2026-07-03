import { describe, expect, it } from "vitest";

import type { ZoteroImportProfile } from "../types";
import {
  ZOTERO_PROFILES_PATH,
  extractLegacyZoteroProfiles,
  mergeZoteroProfilesFiles,
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

  it("coerces missing/non-string path fields to '' instead of dropping the profile (second review)", () => {
    // A profile damaged at the field level (or predating newer fields, e.g.
    // pre-assetFolder-split) must reach UI/runtime code with usable string
    // fields — not be silently deleted on the next save.
    const norm = normalizeZoteroProfilesFile({
      profiles: [
        { name: "Damaged", templatePath: 42, outputFilename: null, imageFolder: "legacy/img" },
      ],
      recentItems: [],
    });
    expect(norm.profiles).toHaveLength(1);
    const p = norm.profiles[0] as unknown as Record<string, unknown>;
    expect(p.templatePath).toBe("");
    expect(p.outputFolder).toBe("");
    expect(p.outputSubfolder).toBe("");
    expect(p.outputFilename).toBe("");
    expect(p.assetFolder).toBe("");
    expect(p.assetSubfolder).toBe("");
    expect(p.bibliographyStyle).toBe("");
    // Extra/deprecated keys survive — the asset-folder migration reads them.
    expect(p.imageFolder).toBe("legacy/img");
  });

  it("preserves lastUsedAt only when numeric", () => {
    const norm = normalizeZoteroProfilesFile({
      profiles: [
        { ...profile("A"), lastUsedAt: 123 },
        { ...profile("B"), lastUsedAt: "yesterday" },
      ],
      recentItems: [],
    });
    expect(norm.profiles[0].lastUsedAt).toBe(123);
    expect(norm.profiles[1].lastUsedAt).toBeUndefined();
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

describe("mergeZoteroProfilesFiles", () => {
  it("preserves peer-only profiles and recent keys on a stale local save", () => {
    const merged = mergeZoteroProfilesFiles(
      { profiles: [profile("Peer")], recentItems: ["PEER"] },
      { profiles: [profile("Local")], recentItems: ["LOCAL"] }
    );
    expect(merged.profiles.map((item) => item.name)).toEqual(["Local", "Peer"]);
    expect(merged.recentItems).toEqual(["LOCAL", "PEER"]);
  });

  it("uses the local edit for a same-name profile without duplicating it", () => {
    const disk = profile("Shared");
    const local = { ...profile("Shared"), outputFolder: "03_Notes/New" };
    const merged = mergeZoteroProfilesFiles(
      { profiles: [disk], recentItems: [] },
      { profiles: [local], recentItems: [] }
    );
    expect(merged.profiles).toHaveLength(1);
    expect(merged.profiles[0].outputFolder).toBe("03_Notes/New");
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

  it("returns null for structurally unrecognizable JSON (second review)", () => {
    // Valid JSON whose structure is not a ZoteroProfilesFile (no profiles /
    // recentItems arrays) may still hold recoverable data — treating it as an
    // empty loaded store would let the next save overwrite it with [].
    for (const wrongShape of [
      '{"unexpected": true}',
      "[]",
      '"a string"',
      "42",
      "null",
      '{"profiles": {"0": {"name": "A"}}, "recentItems": []}', // object, not array
      '{"profiles": [], "recentItems": "junk"}',
    ]) {
      expect(parseZoteroProfilesFile(wrongShape)).toBeNull();
    }
  });

  it("accepts the exact shape the plugin writes, including the empty store", () => {
    expect(
      parseZoteroProfilesFile('{"profiles": [], "recentItems": []}')
    ).toEqual({ profiles: [], recentItems: [] });
  });
});
