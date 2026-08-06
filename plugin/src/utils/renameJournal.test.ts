import { describe, it, expect } from "vitest";
import { RenameJournal, MAX_RENAME_ENTRIES } from "./renameJournal";

describe("RenameJournal", () => {
  it("resolves a historical path to where the file lives now", () => {
    const j = new RenameJournal();
    j.record(
      "03_Notes/Vision/3DRec/3D Line Mapping Revisited.md",
      "03_Notes/Papers/3DRec/3D Line Mapping Revisited.md"
    );

    expect(j.resolve("03_Notes/Vision/3DRec/3D Line Mapping Revisited.md")).toBe(
      "03_Notes/Papers/3DRec/3D Line Mapping Revisited.md"
    );
  });

  it("returns null for a path that was never moved", () => {
    const j = new RenameJournal();
    j.record("a.md", "b.md");
    expect(j.resolve("never-moved.md")).toBeNull();
  });

  it("collapses a chain so the ORIGINAL path still resolves", () => {
    // The case that makes naive journals wrong: the user moves a file twice.
    // A reference captured before the first move must reach the final location.
    const j = new RenameJournal();
    j.record("a.md", "b.md");
    j.record("b.md", "c.md");

    expect(j.resolve("a.md")).toBe("c.md");
    expect(j.resolve("b.md")).toBe("c.md");
  });

  it("collapses a three-hop chain", () => {
    const j = new RenameJournal();
    j.record("a.md", "b.md");
    j.record("b.md", "c.md");
    j.record("c.md", "d.md");

    expect(j.resolve("a.md")).toBe("d.md");
    expect(j.resolve("b.md")).toBe("d.md");
    expect(j.resolve("c.md")).toBe("d.md");
  });

  it("handles a file moved away and back again", () => {
    const j = new RenameJournal();
    j.record("a.md", "b.md");
    j.record("b.md", "a.md");

    // 'a.md' is where the file actually is, so it needs no redirection —
    // leaving an a -> b entry would send a live path to an empty one.
    expect(j.resolve("a.md")).toBeNull();
    // But a reference captured while the file sat at 'b.md' is still historical
    // and must reach the current location.
    expect(j.resolve("b.md")).toBe("a.md");
  });

  it("never resolves a path to itself", () => {
    const j = new RenameJournal();
    j.record("a.md", "a.md");
    expect(j.resolve("a.md")).toBeNull();
    expect(j.size).toBe(0);
  });

  it("ignores empty paths", () => {
    const j = new RenameJournal();
    j.record("", "b.md");
    j.record("a.md", "");
    expect(j.size).toBe(0);
  });

  it("forgets a deleted path so the reference reports the deletion honestly", () => {
    const j = new RenameJournal();
    j.record("a.md", "b.md");
    j.forget("b.md");

    expect(j.resolve("a.md")).toBeNull();
    expect(j.resolve("b.md")).toBeNull();
  });

  it("round-trips through JSON so the journal survives a reload", () => {
    const j = new RenameJournal();
    j.record("a.md", "b.md");
    j.record("b.md", "c.md");
    j.record("x.md", "y.md");

    const restored = new RenameJournal(j.toJSON());

    expect(restored.resolve("a.md")).toBe("c.md");
    expect(restored.resolve("x.md")).toBe("y.md");
  });

  it("stays bounded, dropping the oldest entries first", () => {
    const j = new RenameJournal();
    for (let i = 0; i < MAX_RENAME_ENTRIES + 25; i++) {
      j.record(`old-${i}.md`, `new-${i}.md`);
    }

    expect(j.size).toBe(MAX_RENAME_ENTRIES);
    expect(j.resolve("old-0.md")).toBeNull();
    expect(j.resolve(`old-${MAX_RENAME_ENTRIES + 24}.md`)).toBe(
      `new-${MAX_RENAME_ENTRIES + 24}.md`
    );
  });
});
