import { describe, expect, it, vi } from "vitest";

vi.mock("obsidian", () => ({
  Modal: class {},
  Notice: class {},
  Setting: class {},
}));

import {
  compactHomePath,
  describeZoteroState,
  zoteroRepairCandidates,
} from "./zoteroRepairModal";

describe("describeZoteroState", () => {
  it("distinguishes Zotero setup and attachment resolution failures", () => {
    expect(describeZoteroState("db_missing")).toContain("database was not found");
    expect(describeZoteroState("attachment_key_missing", "ATT")).toContain("ATT");
    expect(describeZoteroState("attachment_file_missing")).toContain("PDF file was not found");
  });

  it("deduplicates candidate roots from status and resolution paths", () => {
    const candidates = zoteroRepairCandidates(
      { ok: false, state: "db_missing", rootsChecked: ["/Users/me/Zotero/zotero.sqlite"], issues: [] },
      {
        ok: false,
        state: "attachment_file_missing",
        rootsChecked: ["/Users/me/Linked"],
        pathsChecked: ["/Users/me/Linked/papers/paper.pdf", "/Users/me/Linked/papers/paper.pdf"],
      }
    );

    expect(candidates).toEqual([
      "/Users/me/Zotero",
      "/Users/me/Linked",
      "/Users/me/Linked/papers",
    ]);
  });

  it("compacts home-directory paths for setup display values", () => {
    expect(compactHomePath("/Users/me/Zotero", "/Users/me")).toBe("~/Zotero");
    expect(compactHomePath("/Users/me/Zotero/zotero.sqlite", "/Users/me")).toBe("~/Zotero/zotero.sqlite");
    expect(compactHomePath("/Volumes/Zotero", "/Users/me")).toBe("/Volumes/Zotero");
  });
});
