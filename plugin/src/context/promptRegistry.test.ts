import { describe, it, expect } from "vitest";
import {
  POPOVER_PROFILE,
  SIDECHAT_PROFILE,
  boundaryConstraints,
  buildRecencyAnchor,
} from "./promptRegistry";

describe("boundaryConstraints", () => {
  it("forbids all tools and filesystem access for tool-isolated (popover) surfaces", () => {
    const text = boundaryConstraints(POPOVER_PROFILE);
    expect(text).toContain("NO tools and NO filesystem access");
    expect(text).toContain("Never list, browse, create, or execute files");
    expect(text).toContain("scripts, or shell commands");
    expect(text).toContain("never invent folder, file, or directory names");
  });

  it("limits tool/file access to the allowed roots for the sidechat surface", () => {
    const text = boundaryConstraints(SIDECHAT_PROFILE);
    expect(text).toContain("allowed roots");
    expect(text).toContain("the vault");
    expect(text).toContain("Zotero folder");
    expect(text).toContain("Zotero library");
    expect(text).toContain("never run ad-hoc");
    // The sidechat keeps its tools, so it must NOT claim zero tool access.
    expect(text).not.toContain("NO tools and NO filesystem access");
  });
});

describe("buildRecencyAnchor", () => {
  it("wraps invariants in a critical_invariants block", () => {
    const text = buildRecencyAnchor(SIDECHAT_PROFILE, { hasPrimarySelection: false });
    expect(text.startsWith("<critical_invariants>")).toBe(true);
    expect(text.trimEnd().endsWith("</critical_invariants>")).toBe(true);
  });

  it("re-asserts primary-selection focus only when a primary selection is present", () => {
    const withSel = buildRecencyAnchor(SIDECHAT_PROFILE, { hasPrimarySelection: true });
    expect(withSel).toContain("Answer ONLY about the <primary_focus_selection>");
    expect(withSel).toContain("Do NOT explain, summarize, or modify the whole document");
    // Defers to the pointer rule rather than overriding it.
    expect(withSel).toContain("<resolved_cross_references>");

    const noSel = buildRecencyAnchor(SIDECHAT_PROFILE, { hasPrimarySelection: false });
    expect(noSel).not.toContain("Answer ONLY about the <primary_focus_selection>");
  });

  it("adds the read-only edit ban only for surfaces that disallow edits", () => {
    const popover = buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: true });
    expect(popover).toContain("read-only: do NOT output any ai-agent-edit blocks");

    const sidechat = buildRecencyAnchor(SIDECHAT_PROFILE, { hasPrimarySelection: true });
    // Sidechat allows edits → it must NOT suppress ai-agent-edit proposals.
    expect(sidechat).not.toContain("read-only");
  });

  it("embeds the surface boundary rule so the anchor is self-contained", () => {
    expect(buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: false })).toContain(
      boundaryConstraints(POPOVER_PROFILE)
    );
    expect(buildRecencyAnchor(SIDECHAT_PROFILE, { hasPrimarySelection: false })).toContain(
      boundaryConstraints(SIDECHAT_PROFILE)
    );
  });
});
