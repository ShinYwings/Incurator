import { describe, expect, it } from "vitest";
import { formatCuratorContextPack } from "./providerContextFormat";
import type { CuratorContextPack } from "../types";

/**
 * The backend adding a field to the pack changes nothing on its own. This
 * formatter is the only thing the model ever sees, and v0.75.0's first pass put
 * `policy` and `persona` in the backend response while leaving this untouched —
 * so the release claimed "the assistant knows the voice the vault was set up
 * for" and the assistant saw neither. Backend tests asserting the dict shape
 * could not catch that, because the gap was one layer up.
 */

const base: CuratorContextPack = { ok: true, items: [] };

describe("what the model is actually shown about the curation lens", () => {
  it("renders the persona into the prompt", () => {
    const out = formatCuratorContextPack(
      { ...base, persona: { text: "Scientific and technical research vault.",
                            output_intent: "knowledge-worker",
                            verification_philosophy: "citation-based evidence" } },
      "q"
    );
    expect(out).toContain("vault_persona:");
    expect(out).toContain("Scientific and technical research vault.");
    expect(out).toContain("knowledge-worker");
  });

  it("states an inert lens as inert rather than staying silent", () => {
    const out = formatCuratorContextPack(
      { ...base, policy: { workspace_id: "default", applied_filters: [], excluded: [] } },
      "q"
    );
    expect(out).toContain("no filters applied");
    expect(out).toContain("was not narrowed");
  });

  it("names the filters that were applied, and what they excluded", () => {
    const out = formatCuratorContextPack(
      { ...base, policy: {
          workspace_id: "proj",
          applied_filters: [{ filter: "source_include", value: ["03_Notes/**"] }],
          excluded: ["explore"],
      } },
      "q"
    );
    expect(out).toContain("source_include=03_Notes/**");
    expect(out).toContain("lens_excluded: explore");
  });

  it("marks requested-but-unenforced distinctions as such", () => {
    // `avoid_merges` reaches no production caller. Presenting it as applied
    // would tell the model a guarantee holds that does not.
    const out = formatCuratorContextPack(
      { ...base, policy: {
          workspace_id: "proj",
          applied_filters: [{ filter: "source_include", value: ["03_Notes/**"] }],
          declared: { avoid_merges: ["A != B"] },
      } },
      "q"
    );
    expect(out).toContain("keep_distinct (requested, not enforced): A != B");
  });

  it("says nothing about a lens the backend did not report", () => {
    const out = formatCuratorContextPack(base, "q");
    expect(out).not.toContain("curation_lens");
    expect(out).not.toContain("vault_persona");
  });
});
