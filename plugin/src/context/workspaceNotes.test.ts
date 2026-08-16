import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildWorkspaceNotesBlock,
  forgetWorkspaceIndex,
  isConsultableNote,
  notesInWorkspace,
  searchWorkspaceNotes,
  workspaceSignature,
  type WorkspaceVaultPort,
} from "./workspaceNotes";

/**
 * v0.57.0 P5b — the reader's own project notes, consulted but never ingested.
 *
 * Measured on the reporting vault: 137 markdown files, 36 ingested, and 75 of
 * the gap are research notes inside one workspace. Duty 2 ("remind me what I
 * already wrote") could not be true while those were invisible — and the user's
 * decision was that they must stay out of the knowledge graph, so this is a
 * retrieval path rather than an ingestion one.
 */

const WS = "01_Workspaces/COLMAP free GS";

function vaultWith(files: Record<string, string>, mtime = 1): WorkspaceVaultPort {
  return {
    list: () => Object.keys(files).map((path) => ({ path, mtime })),
    read: vi.fn(async (path: string) => files[path] ?? ""),
  };
}

beforeEach(() => forgetWorkspaceIndex(WS));

describe("isConsultableNote", () => {
  it("takes the reader's notes", () => {
    expect(isConsultableNote(`${WS}/Research Notes/svd.md`)).toBe(true);
    expect(isConsultableNote(`${WS}/01_Theory/rotations.md`)).toBe(true);
  });

  it("refuses the agent's own scaffolding", () => {
    // Quoting the agent's plans and relay state back to the reader as "notes
    // you wrote" is worse than surfacing nothing. 13 of the workspace's 88
    // markdown files are under .agents/.
    expect(isConsultableNote(`${WS}/.agents/RELAY.md`)).toBe(false);
    expect(isConsultableNote(`${WS}/.agents/plans/01_thing.md`)).toBe(false);
    expect(isConsultableNote(`${WS}/CLAUDE.md`)).toBe(false);
    expect(isConsultableNote(`${WS}/AGENTS.md`)).toBe(false);
  });

  it("refuses non-markdown and machine directories", () => {
    expect(isConsultableNote(`${WS}/curate.yml`)).toBe(false);
    expect(isConsultableNote(`${WS}/.obsidian/workspace.json`)).toBe(false);
    expect(isConsultableNote(`${WS}/.curator/state.sqlite`)).toBe(false);
  });
});

describe("notesInWorkspace", () => {
  const entries = [
    { path: `${WS}/Research Notes/a.md`, mtime: 1 },
    { path: `${WS}/.agents/RELAY.md`, mtime: 1 },
    { path: "01_Workspaces/Other Project/b.md", mtime: 1 },
    { path: "03_Notes/c.md", mtime: 1 },
  ];

  it("takes only this workspace, machinery excluded", () => {
    expect(notesInWorkspace(entries, WS).map((e) => e.path)).toEqual([
      `${WS}/Research Notes/a.md`,
    ]);
  });

  it("does not leak a sibling project's notes", () => {
    // Scoping is the point: another project's working notes are as irrelevant
    // as another user's.
    expect(notesInWorkspace(entries, WS).some((e) => e.path.includes("Other Project"))).toBe(
      false,
    );
  });

  it("returns nothing when there is no active workspace", () => {
    expect(notesInWorkspace(entries, "")).toEqual([]);
  });

  it("an empty workspace does not degenerate into matching everything", () => {
    // Without the explicit guard the prefix becomes "/", which matches nothing
    // for vault-relative paths but DOES match an absolute one. That difference
    // is the whole reason the guard is there, so pin it rather than leave a
    // defensive line no test covers.
    const withAbsolute = [
      { path: "/etc/passwd.md", mtime: 1 },
      { path: `${WS}/Research Notes/a.md`, mtime: 1 },
    ];
    expect(notesInWorkspace(withAbsolute, "")).toEqual([]);
  });
});

describe("workspaceSignature", () => {
  it("changes when a file is edited, added, or removed", () => {
    const base = [{ path: "a.md", mtime: 1 }, { path: "b.md", mtime: 1 }];
    const edited = [{ path: "a.md", mtime: 2 }, { path: "b.md", mtime: 1 }];
    const added = [...base, { path: "c.md", mtime: 1 }];
    const removed = [{ path: "a.md", mtime: 1 }];

    expect(workspaceSignature(base)).not.toEqual(workspaceSignature(edited));
    expect(workspaceSignature(base)).not.toEqual(workspaceSignature(added));
    expect(workspaceSignature(base)).not.toEqual(workspaceSignature(removed));
  });

  it("is stable under listing order", () => {
    const a = [{ path: "a.md", mtime: 1 }, { path: "b.md", mtime: 2 }];
    const b = [{ path: "b.md", mtime: 2 }, { path: "a.md", mtime: 1 }];
    expect(workspaceSignature(a)).toEqual(workspaceSignature(b));
  });
});

describe("searchWorkspaceNotes", () => {
  const files = {
    [`${WS}/Research Notes/degeneracy.md`]:
      "Degenerate configurations appear when the baseline collapses. " +
      "I concluded the line-based initialisation avoids this.",
    [`${WS}/01_Theory/rotations.md`]:
      "Rotation averaging notes. Quaternion parameterisation and its pitfalls.",
    [`${WS}/.agents/RELAY.md`]: "Degenerate baseline agent bookkeeping goes here.",
  };

  it("finds the reader's note by its content", async () => {
    const hits = await searchWorkspaceNotes(vaultWith(files), WS, "degenerate baseline");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].path).toBe(`${WS}/Research Notes/degeneracy.md`);
    expect(hits[0].snippet).toMatch(/baseline/i);
  });

  it("never returns agent scaffolding, even when it matches best", async () => {
    const hits = await searchWorkspaceNotes(vaultWith(files), WS, "agent bookkeeping");
    expect(hits.every((h) => !h.path.includes(".agents/"))).toBe(true);
  });

  it("consults nothing outside a workspace rather than falling back to the vault", async () => {
    // A vault-wide fallback would reintroduce the ephemeral whole-vault index
    // §4.7 rejected on measured grounds.
    expect(await searchWorkspaceNotes(vaultWith(files), "", "degenerate")).toEqual([]);
  });

  it("reads each note once per change, not once per question", async () => {
    // §4.7's whole objection to the rejected design was rebuild-per-call, which
    // measured 331x the bulk path elsewhere.
    const vault = vaultWith(files);
    await searchWorkspaceNotes(vault, WS, "degenerate");
    const afterFirst = (vault.read as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(afterFirst).toBeGreaterThan(0);

    await searchWorkspaceNotes(vault, WS, "rotation averaging");
    expect((vault.read as ReturnType<typeof vi.fn>).mock.calls.length).toBe(afterFirst);
  });

  it("re-reads after the reader edits a note", async () => {
    const vault = vaultWith(files, 1);
    await searchWorkspaceNotes(vault, WS, "degenerate");
    const afterFirst = (vault.read as ReturnType<typeof vi.fn>).mock.calls.length;

    const touched = vaultWith(files, 2);
    (touched.read as ReturnType<typeof vi.fn>).mockImplementation(vault.read);
    await searchWorkspaceNotes(touched, WS, "degenerate");
    expect((vault.read as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(
      afterFirst,
    );
  });

  it("survives a note that cannot be read", async () => {
    const vault: WorkspaceVaultPort = {
      list: () => [{ path: `${WS}/broken.md`, mtime: 1 }, { path: `${WS}/ok.md`, mtime: 1 }],
      read: async (path) => {
        if (path.endsWith("broken.md")) throw new Error("EACCES");
        return "readable content about baselines";
      },
    };
    const hits = await searchWorkspaceNotes(vault, WS, "baselines");
    expect(hits.map((h) => h.path)).toEqual([`${WS}/ok.md`]);
  });
});

describe("buildWorkspaceNotesBlock", () => {
  it("is empty when nothing matched, so no stray block reaches the prompt", () => {
    expect(buildWorkspaceNotesBlock([])).toBe("");
  });

  it("labels each note with its path and says whose words these are", () => {
    const block = buildWorkspaceNotesBlock([
      { path: `${WS}/Research Notes/a.md`, score: 1, snippet: "my earlier conclusion" },
    ]);
    expect(block).toContain('<note path="01_Workspaces/COLMAP free GS/Research Notes/a.md">');
    expect(block).toContain("my earlier conclusion");
    // The distinction that changes what a correct answer looks like.
    expect(block).toMatch(/wrote themselves|their working notes/i);
    expect(block).toMatch(/not established fact/i);
  });

  it("escapes a path that would otherwise break the attribute", () => {
    const block = buildWorkspaceNotesBlock([
      { path: `${WS}/a "quoted" & <odd>.md`, score: 1, snippet: "x" },
    ]);
    expect(block).toContain("&quot;quoted&quot;");
    expect(block).toContain("&amp;");
    expect(block).not.toMatch(/<odd>/);
  });
});
