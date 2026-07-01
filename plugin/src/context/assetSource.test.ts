import { describe, expect, it } from "vitest";
import {
  type AssetSource,
  assetStatusKey,
  zoteroConfigEpoch,
  ZoteroPathCache,
  resolveAssetSource,
} from "./assetSource";

function src(partial: Partial<AssetSource>): AssetSource {
  return { displayName: "doc", resolutionStatus: "untracked", ...partial };
}

describe("assetStatusKey", () => {
  it("is Zotero-identity-first so the key is stable before/after path resolution", () => {
    // The badge desync (audit item 3) came from keying by sourcePath sometimes
    // and zotero:<key> other times. A Zotero source must yield the SAME key
    // whether or not its absPath has been resolved yet.
    const beforePath = src({ zoteroKey: "ABC", displayName: "Paper" });
    const afterPath = src({ zoteroKey: "ABC", absPath: "/Zotero/storage/ABC/p.pdf" });
    expect(assetStatusKey(beforePath)).toBe("zotero:ABC");
    expect(assetStatusKey(afterPath)).toBe("zotero:ABC");
    expect(assetStatusKey(beforePath)).toBe(assetStatusKey(afterPath));
  });

  it("falls back through absPath -> relpath -> hash -> name", () => {
    expect(assetStatusKey(src({ absPath: "/a/b.pdf" }))).toBe("/a/b.pdf");
    expect(assetStatusKey(src({ relpath: "04_Resources/x.md" }))).toBe("04_Resources/x.md");
    expect(assetStatusKey(src({ fileHash: "deadbeef" }))).toBe("hash:deadbeef");
    expect(assetStatusKey(src({ displayName: "Only Name" }))).toBe("name:Only Name");
  });
});

describe("zoteroConfigEpoch", () => {
  it("changes when the Zotero data dir or workspace changes", () => {
    const a = zoteroConfigEpoch({ zoteroBasePath: "~/Zotero", workspaceId: "w1" });
    const b = zoteroConfigEpoch({ zoteroBasePath: "~/Zotero2", workspaceId: "w1" });
    const c = zoteroConfigEpoch({ zoteroBasePath: "~/Zotero", workspaceId: "w2" });
    expect(a).not.toBe(b);
    expect(a).not.toBe(c);
    expect(a).toBe(zoteroConfigEpoch({ zoteroBasePath: "~/Zotero", workspaceId: "w1" }));
  });
});

describe("ZoteroPathCache", () => {
  it("invalidates the whole cache when the config epoch changes", () => {
    const cache = new ZoteroPathCache({ fileExists: () => true });
    cache.set("ABC", "epoch1", "/old/path.pdf");
    expect(cache.get("ABC", "epoch1")).toBe("/old/path.pdf");
    // Settings changed -> new epoch -> stale path must NOT be served.
    expect(cache.get("ABC", "epoch2")).toBeUndefined();
  });

  it("treats a cached path whose file no longer exists as a miss", () => {
    let present = true;
    const cache = new ZoteroPathCache({ fileExists: () => present });
    cache.set("ABC", "e", "/zotero/ABC/p.pdf");
    expect(cache.get("ABC", "e")).toBe("/zotero/ABC/p.pdf");
    present = false; // user moved/deleted the file
    expect(cache.get("ABC", "e")).toBeUndefined();
  });

  it("clear() empties the cache (plugin reload)", () => {
    const cache = new ZoteroPathCache({ fileExists: () => true });
    cache.set("ABC", "e", "/p.pdf");
    cache.clear();
    expect(cache.get("ABC", "e")).toBeUndefined();
  });
});

describe("resolveAssetSource", () => {
  const baseDeps = () => ({
    resolveZoteroViaBackend: async () => "/backend/resolved.pdf",
    cache: new ZoteroPathCache({ fileExists: () => true }),
    epoch: "e1",
    fileExists: () => true,
  });

  it("prefers backend resolution for a Zotero key when backend is available", async () => {
    const out = await resolveAssetSource({ zoteroKey: "ABC", displayName: "P" }, baseDeps());
    expect(out.absPath).toBe("/backend/resolved.pdf");
    expect(out.zoteroKey).toBe("ABC");
    expect(out.resolutionStatus).toBe("resolved");
  });

  it("serves a cached Zotero path without re-resolving", async () => {
    const deps = baseDeps();
    deps.cache.set("ABC", "e1", "/cached/hit.pdf");
    let backendCalls = 0;
    deps.resolveZoteroViaBackend = async () => {
      backendCalls += 1;
      return "/backend/resolved.pdf";
    };
    const out = await resolveAssetSource({ zoteroKey: "ABC", displayName: "P" }, deps);
    expect(out.absPath).toBe("/cached/hit.pdf");
    expect(backendCalls).toBe(0);
  });

  it("reports path_unresolved when a Zotero key cannot be resolved anywhere", async () => {
    const deps = {
      ...baseDeps(),
      resolveZoteroViaBackend: async () => undefined,
    };
    const out = await resolveAssetSource({ zoteroKey: "GONE", displayName: "P" }, deps);
    expect(out.absPath).toBeUndefined();
    expect(out.resolutionStatus).toBe("path_unresolved");
  });

  it("does not let a Reference Mode relpath stub mark an unresolved Zotero PDF as resolved", async () => {
    const deps = {
      ...baseDeps(),
      resolveZoteroViaBackend: async () => undefined,
      fileExists: () => false,
    };
    const out = await resolveAssetSource(
      {
        relpath: "04_Resources/References/paper.md",
        zoteroKey: "GONE",
        displayName: "Paper",
      },
      deps
    );
    expect(out.resolutionStatus).toBe("path_unresolved");
  });

  it("uses a freshly resolved Zotero path before a stale absolute hint", async () => {
    const deps = baseDeps();
    const out = await resolveAssetSource(
      {
        absPath: "/stale/synced/mac/path.pdf",
        zoteroKey: "ABC",
        displayName: "Paper",
      },
      deps
    );
    expect(out.absPath).toBe("/backend/resolved.pdf");
    expect(out.resolutionStatus).toBe("resolved");
  });

  it("does not treat an external reference stub relpath as a resolved local file", async () => {
    const out = await resolveAssetSource(
      {
        relpath: "04_Resources/References/external.md",
        isReference: true,
        displayName: "External",
      },
      baseDeps()
    );
    expect(out.resolutionStatus).toBe("path_unresolved");
  });

  it("resolves a plain vault relpath as resolved without Zotero work", async () => {
    const out = await resolveAssetSource(
      { relpath: "04_Resources/x.md", displayName: "x" },
      baseDeps()
    );
    expect(out.relpath).toBe("04_Resources/x.md");
    expect(out.resolutionStatus).toBe("resolved");
  });
});
