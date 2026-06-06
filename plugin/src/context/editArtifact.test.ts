import { describe, it, expect } from "vitest";
import {
  ARTIFACT_DIR,
  buildEditDiffBlock,
  buildEditArtifactMarkdown,
  buildEditArtifactFilename,
  type EditArtifactProposal,
} from "./editArtifact";

describe("editArtifact: ARTIFACT_DIR", () => {
  it("lives under 00_System so it is never ingested by raw_dirs", () => {
    expect(ARTIFACT_DIR).toBe("00_System/Agent Diffs");
    expect(ARTIFACT_DIR.startsWith("00_System/")).toBe(true);
  });
});

describe("editArtifact: buildEditDiffBlock", () => {
  it("prefixes search lines with - and replace lines with + inside a diff fence", () => {
    expect(buildEditDiffBlock("a\nb", "a\nc")).toBe(
      "```diff\n-a\n-b\n+a\n+c\n```"
    );
  });

  it("renders an empty search (new file) as all + lines", () => {
    expect(buildEditDiffBlock("", "x\ny")).toBe("```diff\n+x\n+y\n```");
  });

  it("treats an explicit NEW FILE marker as new content", () => {
    expect(buildEditDiffBlock("<<< NEW FILE >>>", "hello")).toBe(
      "```diff\n+hello\n```"
    );
  });
});

describe("editArtifact: buildEditArtifactMarkdown", () => {
  const meta = {
    title: "Tidy the intro",
    sessionId: "sess-123",
    created: new Date("2026-06-06T07:50:00Z"),
  };

  it("emits agent-diff-artifact frontmatter with a deduped file list", () => {
    const proposals: EditArtifactProposal[] = [
      { filepath: "a.md", search: "foo", replace: "bar" },
      { filepath: "b.md", search: "baz", replace: "qux" },
      { filepath: "a.md", search: "one", replace: "two" },
    ];
    const md = buildEditArtifactMarkdown(proposals, meta);

    expect(md.startsWith("---\n")).toBe(true);
    expect(md).toContain("type: agent-diff-artifact");
    expect(md).toContain("created: 2026-06-06T07:50:00.000Z");
    expect(md).toContain("session: sess-123");
    // Deduped, first-appearance order.
    expect(md).toContain("files:\n  - a.md\n  - b.md\n");
    expect(md).toContain("# Proposed edits — Tidy the intro");
    expect(md).toContain("**Review Diff**");
  });

  it("groups multiple proposals for the same file under one heading", () => {
    const proposals: EditArtifactProposal[] = [
      { filepath: "a.md", search: "foo", replace: "bar" },
      { filepath: "a.md", search: "one", replace: "two" },
    ];
    const md = buildEditArtifactMarkdown(proposals, meta);

    expect(md.match(/^## a\.md$/gm)?.length).toBe(1);
    expect(md).toContain("-foo\n+bar");
    expect(md).toContain("-one\n+two");
  });
});

describe("editArtifact: buildEditArtifactFilename", () => {
  const created = new Date("2026-06-06T07:50:00Z");

  it("uses date, time, and the first target's basename as the slug", () => {
    const name = buildEditArtifactFilename(
      [{ filepath: "03_Notes/Vision/Multiple_View.md", search: "a", replace: "b" }],
      created
    );
    expect(name).toBe("2026-06-06_0750_Multiple_View.md");
  });

  it("falls back to 'edits' when there is no usable target name", () => {
    const name = buildEditArtifactFilename([], created);
    expect(name).toBe("2026-06-06_0750_edits.md");
  });

  it("sanitizes unsafe characters in the slug", () => {
    const name = buildEditArtifactFilename(
      [{ filepath: "weird name?/a b:c.md", search: "x", replace: "y" }],
      created
    );
    expect(name).toBe("2026-06-06_0750_a-b-c.md");
  });
});
