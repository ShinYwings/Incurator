import { describe, it, expect } from "vitest";
import { workspaceRelpathForFile, resolveWorkspacePath } from "./workspaceScope";

describe("workspaceRelpathForFile", () => {
  it("resolves a note inside a workspace", () => {
    expect(
      workspaceRelpathForFile("01_Workspaces/COLMAP free GS/00_Project/milestones.md")
    ).toBe("01_Workspaces/COLMAP free GS");
  });

  it("keeps only the project level, not deeper folders", () => {
    expect(
      workspaceRelpathForFile("01_Workspaces/Lab/a/b/c/deep.md")
    ).toBe("01_Workspaces/Lab");
  });

  it("returns nothing for a note outside any workspace", () => {
    // The common case for this vault: the user asks about a paper in 03_Notes.
    // No workspace applies, and pretending one does is what the old vault-root
    // fallback did.
    expect(workspaceRelpathForFile("03_Notes/Papers/3DRec/paper.md")).toBe("");
    expect(workspaceRelpathForFile("02_Wiki/note.md")).toBe("");
  });

  it("does not treat a loose file directly under 01_Workspaces as a project", () => {
    expect(workspaceRelpathForFile("01_Workspaces/readme.md")).toBe("");
    expect(workspaceRelpathForFile("01_Workspaces")).toBe("");
  });

  it("tolerates leading slashes and backslashes", () => {
    expect(workspaceRelpathForFile("/01_Workspaces/Lab/x.md")).toBe("01_Workspaces/Lab");
    expect(workspaceRelpathForFile("01_Workspaces\\Lab\\x.md")).toBe("01_Workspaces/Lab");
  });

  it("returns nothing for empty input", () => {
    expect(workspaceRelpathForFile("")).toBe("");
  });
});

describe("resolveWorkspacePath", () => {
  it("builds the absolute workspace path the backend expects", () => {
    expect(
      resolveWorkspacePath("/Users/x/vault", "01_Workspaces/COLMAP free GS/a.md")
    ).toBe("/Users/x/vault/01_Workspaces/COLMAP free GS");
  });

  it("returns empty rather than the vault root when no workspace applies", () => {
    // This is the whole fix. Passing the vault root made the backend look for
    // curate.yml there, find none, and silently use the default policy while
    // reporting workspace_id "default" — indistinguishable from a real answer.
    expect(resolveWorkspacePath("/Users/x/vault", "03_Notes/paper.md")).toBe("");
  });

  it("normalizes a trailing slash on the vault base", () => {
    expect(
      resolveWorkspacePath("/Users/x/vault/", "01_Workspaces/Lab/a.md")
    ).toBe("/Users/x/vault/01_Workspaces/Lab");
  });

  it("returns empty when the vault base is unknown", () => {
    expect(resolveWorkspacePath("", "01_Workspaces/Lab/a.md")).toBe("");
  });
});
