import { describe, expect, it } from "vitest";
import { buildQuickQueryMessages } from "./quickQueryContext";

/**
 * The measured worst case, rebuilt through the real assembly.
 *
 * The budget audit stacked every optional block at or near its independent cap
 * and measured the reader's own selection at 102 characters inside a 53,032
 * character turn — 0.19% — with the vault evidence alone outweighing it about
 * 206x. Nothing summed the caps and nothing reserved a share for the selection.
 *
 * This runs the same shape through `buildQuickQueryMessages` so the number
 * cannot drift back without a test failing.
 */
const SELECTION = "As shown in Section 3.2 [12], the result follows.";

function huge(tag: string, n: number): string {
  return `<${tag}>\n${"supporting material. ".repeat(n)}\n</${tag}>`;
}

describe("the worst case the budget audit measured", () => {
  const messages = buildQuickQueryMessages({
    selectedText: SELECTION,
    question: "이게 뭐야?",
    resolvedReferencesBlock: huge("resolved_citations", 500),
    resolvedWikilinksBlock: huge("resolved_wikilinks", 400),
    vaultEvidenceBlock: huge("incurator_evidence_pack", 1000),
    pinnedContextRefs: [],
  });
  const user = String(messages[1].content);

  it("keeps the selection the reader pointed at", () => {
    expect(user).toContain(SELECTION);
  });

  it("keeps the question", () => {
    expect(user).toContain("이게 뭐야?");
  });

  it("keeps the invariants that must survive any budget", () => {
    expect(user).toContain("<critical_invariants>");
  });

  it("no longer lets the turn grow without a ceiling", () => {
    // 53,032 chars before this existed, from the same shape.
    expect(user.length).toBeLessThan(40_000);
  });

  it("spends the budget on what the reader pointed at first", () => {
    // Citations and linked notes are what the selection points AT, so they
    // survive whole; the vault's volunteered evidence is what gives way.
    expect(user).toContain("resolved_citations");
    expect(user).toContain("resolved_wikilinks");
    expect(user).toContain("truncated to fit this turn");
  });

  it("names the cut rather than leaving a silent gap", () => {
    // A block that stops mid-sentence with no marker reads as a complete one
    // that happens to be wrong.
    expect(user).toMatch(/vault evidence truncated to fit this turn/);
  });

  it("drops a block whole when only a fragment of it would fit", () => {
    const tight = buildQuickQueryMessages({
      selectedText: SELECTION,
      question: "이게 뭐야?",
      resolvedReferencesBlock: huge("resolved_citations", 1700),
      vaultEvidenceBlock: huge("incurator_evidence_pack", 1000),
      pinnedContextRefs: [],
    });
    const text = String(tight[1].content);
    expect(text).toContain(SELECTION);
    expect(text).toContain("Omitted to fit this turn");
    expect(text).toContain("vault evidence");
  });
});
