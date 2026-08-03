import { describe, it, expect } from "vitest";
import {
  POPOVER_PROFILE,
  SIDECHAT_PROFILE,
  boundaryConstraints,
  buildRecencyAnchor,
  type ToolPolicy,
} from "./promptRegistry";

describe("boundaryConstraints", () => {
  it("forbids MCP tools and filesystem access for the popover surface", () => {
    const text = boundaryConstraints(POPOVER_PROFILE);
    expect(text).toContain("NO filesystem access and NO MCP tools");
    expect(text).toContain("Never list, browse, create, or execute files");
    expect(text).toContain("scripts, or shell commands");
    expect(text).toContain("never invent folder, file, or directory names");
    // v0.41.0: the popover may fetch pages of the already-open PDF.
    expect(text).toContain("PDF the user already has open");
  });

  it("still forbids every tool for a fully tool-free surface", () => {
    const text = boundaryConstraints({ ...POPOVER_PROFILE, toolPolicy: "none" });
    expect(text).toContain("NO tools and NO filesystem access");
    expect(text).not.toContain("PDF the user already has open");
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

  it("covers every ToolPolicy value with distinct boundary text", () => {
    const policies: ToolPolicy[] = ["auto", "none", "local-only"];
    const texts = policies.map((toolPolicy) =>
      boundaryConstraints({ ...POPOVER_PROFILE, toolPolicy })
    );
    // No policy may fall through to another policy's wording.
    expect(new Set(texts).size).toBe(policies.length);
    for (const text of texts) expect(text.length).toBeGreaterThan(0);
  });
});

describe("POPOVER_PROFILE tool policy", () => {
  it("is local-only so the popover keeps zero MCP tools but gains the PDF reader", () => {
    expect(POPOVER_PROFILE.toolPolicy).toBe("local-only");
    expect(POPOVER_PROFILE.allowEdits).toBe(false);
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
