import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * The assistant answers about the DOCUMENT, never about its own context.
 *
 * User report (2026-08-09), verbatim from the popover:
 *
 *   "Sec. C의 보충자료 전문(p.12–13)은 지금 제 현재 컨텍스트에 로드되지
 *    않았어요. 대신 본문 3.3절(p.5)과 문서 아웃라인을 기준으로…"
 *
 * That was not the model being chatty — three prompt sites instructed it, in so
 * many words, to "say you could not retrieve the referenced item". This suite
 * pins the two rules that replaced them:
 *
 *   1. No prompt tells the model to announce a retrieval gap. Established RAG
 *      guidance is that the assistant should not mention the retrieved context
 *      at all; it is a cheatsheet, not a subject.
 *   2. Constraints are phrased as the behaviour we want, not as prohibitions.
 *      Negative instructions prime the behaviour they forbid (the "pink
 *      elephant" effect), which is why "do NOT open the source file" sat
 *      directly beside a model that kept narrating what it could not open.
 */

const CONTEXT_DIR = __dirname;

const PROMPT_SOURCES = [
  "chatContextPriority.ts",
  "crossReferenceResolver.ts",
  "promptRegistry.ts",
] as const;

function promptSource(file: string): string {
  return readFileSync(join(CONTEXT_DIR, file), "utf-8");
}

/** Only the string literals — comments explaining the rule are not prompt text. */
function promptLiterals(source: string): string {
  return (source.match(/"(?:[^"\\]|\\.)*"/g) ?? []).join("\n");
}

describe("prompts never instruct the model to narrate its retrieval state", () => {
  it.each(PROMPT_SOURCES)("%s does not tell the model to announce a gap", (file) => {
    const text = promptLiterals(promptSource(file));
    for (const phrase of [
      "say you could not",
      "say plainly that you could not",
      "could not retrieve the",
      "could not locate the referenced",
      "state that you do not have",
    ]) {
      expect(text.toLowerCase(), `${file} instructs the narration: "${phrase}"`)
        .not.toContain(phrase.toLowerCase());
    }
  });

  it.each(PROMPT_SOURCES)("%s states the rule positively", (file) => {
    const text = promptLiterals(promptSource(file));
    // "do NOT open/read/search the file" primed the very narration it sat next
    // to. The replacement says where to work FROM instead.
    expect(text).not.toMatch(/do NOT attempt to open/i);
    expect(text).not.toMatch(/never try\s+"?\s*\+?\s*"?to open, read, or search/i);
  });

  it("the unresolved-reference note is addressed to the model, not the reader", () => {
    const text = promptSource("crossReferenceResolver.ts");
    const start = text.indexOf("const UNRESOLVED_NOTE");
    const note = text.slice(start, text.indexOf(";", start));
    expect(note).toContain("addressed to you, not");
    expect(note).toContain("describes the document");
    expect(note.toLowerCase()).not.toContain("say plainly");
  });

  it("at least one prompt states the write-for-the-reader rule explicitly", () => {
    const all = PROMPT_SOURCES.map((f) => promptLiterals(promptSource(f))).join("\n");
    expect(all).toMatch(/never the retrieval|not about the\s*"?\s*\+?\s*"?context/i);
  });
});
