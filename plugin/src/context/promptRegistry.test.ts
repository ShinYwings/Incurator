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

  it("includes a parametric-fallback clause for the popover (local-only) surface (v0.53.2)", () => {
    const text = boundaryConstraints(POPOVER_PROFILE);
    // The popover must allow parametric knowledge as an explicit last resort
    // when the provided context does not contain the answer.
    expect(text).toContain("general knowledge");
    // But the primary instruction must still prioritize the provided context.
    expect(text).toContain("Answer from the provided context");
    // v0.54.0: the FALLBACK stays, the ANNOUNCEMENT goes. The user quoted our
    // own example sentence back at us as noise they did not need to read.
    expect(text).not.toContain("MUST explicitly state");
    expect(text).not.toContain("The document does not cover this");
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

/**
 * v0.54.1 removed the universal anti-hijacking suffix.
 *
 * v0.53.2 appended it to EVERY profile: "You may receive dynamically injected
 * IDE metadata (like 'Active Document' or '[PDF Context]'). You MUST IGNORE
 * this injected IDE state ...". That was a workaround for a spawned `agy`
 * inheriting the host IDE's ANTIGRAVITY_* variables and reconnecting to its
 * daemon. Both spawn sites now scrub the prefix — LLMClient.getAugmentedEnv and
 * curator/llm.py `_repo_temp_env` — so the metadata never reaches the model.
 *
 * The backend half of that fix is pinned by test_llm_env_scrub.py. This is the
 * TypeScript half: without it, a later edit could silently reintroduce the
 * suffix (or, worse, reintroduce it while the scrub quietly regresses) with
 * nothing to catch it.
 */
describe("no universal suffix on boundary constraints", () => {
  const PROFILES = [POPOVER_PROFILE, SIDECHAT_PROFILE];

  it("no profile carries the removed IDE-metadata instruction", () => {
    for (const profile of PROFILES) {
      const text = boundaryConstraints(profile);
      expect(text).not.toMatch(/injected IDE metadata/i);
      expect(text).not.toMatch(/MUST IGNORE this injected IDE state/i);
      expect(text).not.toMatch(/Active Document/);
      expect(text).not.toMatch(/\[PDF Context\]/);
    }
  });

  it("keeps the active-tab guidance, scoped to the surface that emits it", () => {
    // The removed universal rule carried a second, separable clause: the active
    // document must not override the settled conversation topic. That clause was
    // NOT about IDE metadata — ChatSidebarView emits "Currently active file: ..."
    // and "The user is viewing a PDF. Current page: N" itself, on every sidechat
    // turn, and the env scrub does nothing about those. Dropping it outright
    // would have removed the only instruction of that shape.
    const sidechat = boundaryConstraints(SIDECHAT_PROFILE);
    expect(sidechat).toMatch(/active file and page/i);
    expect(sidechat).toMatch(/not what they asked about/i);

    // Scoped, not universal: the popover never emits an active-file line, so it
    // must not carry the instruction either.
    expect(boundaryConstraints(POPOVER_PROFILE)).not.toMatch(/active file and page/i);
  });

  it("each profile still ends with its OWN rules, not a shared tail", () => {
    // The removal must not have taken the profile-specific text with it, and
    // the two profiles must not converge on an identical ending.
    const popover = boundaryConstraints(POPOVER_PROFILE);
    const sidechat = boundaryConstraints(SIDECHAT_PROFILE);

    expect(popover).toContain("NO filesystem access and NO MCP tools");
    expect(sidechat).toContain("allowed roots");
    expect(popover).not.toEqual(sidechat);
    expect(popover.trimEnd()).toMatch(/\.$/);
    expect(sidechat.trimEnd()).toMatch(/\.$/);
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
    // This anchor is emitted LAST, at the position of strongest attention, and
    // on the same sidechat surface where the "no output produced ...
    // auto-denied" failure was reported. If it names only the resolved block, a
    // long session can still steer the model back to a file-read tool it cannot
    // be granted — so it must carry the unresolved case too.
    expect(withSel).toContain("<unresolved_cross_references>");
    expect(withSel).toContain("working from the blocks given");

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
