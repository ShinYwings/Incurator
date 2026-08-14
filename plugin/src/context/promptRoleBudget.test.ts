import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * The prompt must describe the assistant's ROLE, and must stay small.
 *
 * Measured audit (2026-08-09) that motivated this gate. Sentences in the prompt
 * stack, classified by which of the user's three stated duties they serve:
 *
 *   duty                          enabling  limiting
 *   1 read/explain the document      32        13
 *   2 remind me of my own notes       6         3
 *   3 find new value                  4         0
 *
 * Duty 3's four hits were MCP *tool descriptions* — no sentence anywhere said
 * that finding new value is the job. And both sentences mentioning the user's
 * notes cancelled themselves in the same breath ("…connect it to the user's
 * existing notes, **but avoid**…"), while three unhedged prohibitions elsewhere
 * said answer ONLY about the selection. The model complied with the
 * prohibitions, which is exactly what the user complained about.
 *
 * These assertions are budgets and floors, not exact matches, so ordinary
 * wording changes pass and only a drift back toward "wall of prohibitions"
 * fails.
 */

const CONTEXT_DIR = __dirname;
const PROMPT_FILES = [
  "systemPrompt.ts",
  "chatContextPriority.ts",
  "promptRegistry.ts",
  "crossReferenceResolver.ts",
] as const;

/** Prompt prose only: long string literals, not identifiers or short fragments. */
function promptProse(): string {
  return PROMPT_FILES.map((f) => {
    const src = readFileSync(join(CONTEXT_DIR, f), "utf-8");
    const lits = src.match(/"(?:[^"\\]|\\.)*"/g) ?? [];
    return lits.filter((l) => l.length > 60).map((l) => l.slice(1, -1)).join("");
  }).join("\n");
}

const NEGATIVE =
  /\b(do not|do NOT|don't|never|must not|MUST NOT|avoid|only about|ONLY about)\b/g;

describe("prompt budget", () => {
  it("stays under the size ceiling", () => {
    // Was 20,156 chars before the v0.54.0 re-pose; 15,292 after. The ceiling
    // leaves room for real capability text without room for another wall.
    expect(promptProse().length).toBeLessThanOrEqual(17_000);
  });

  it("stays under the prohibition ceiling", () => {
    // Instruction-following degrades as `do NOT` rules accumulate, and the
    // narration bug was a model complying perfectly with one of them. Was 24
    // before the v0.54.0 re-pose; 23 by this static count.
    //
    // The static count is one HIGHER than what any single prompt actually
    // carries: `wrapLatestUserMessageForLanguageBridge` has two ternary
    // branches that each end with the same "Detect it fresh from this request;
    // do not infer the output language" sentence, and exactly one of them
    // reaches a given turn. Scanning source text cannot tell them apart, so the
    // ceiling is set against the measurable number rather than an estimate of
    // the runtime one.
    expect((promptProse().match(NEGATIVE) ?? []).length).toBeLessThanOrEqual(23);
  });
});

describe("the prompt states the assistant's role", () => {
  it("names reading alongside the user", () => {
    expect(promptProse()).toMatch(/read alongside|pages and figures they have not opened/i);
  });

  it("names reminding the user of their own notes", () => {
    const prose = promptProse();
    expect(prose).toMatch(/remind them what they have already written|their own notes/i);
    // The duty must not be handed back with the other hand in the same clause.
    expect(prose).not.toMatch(/existing notes[^.]{0,80}\bbut avoid\b/i);
    expect(prose).not.toMatch(/existing notes[^.]{0,80}\bbut you MUST NOT\b/i);
  });

  it("names finding new value — the duty that had no instruction at all", () => {
    expect(promptProse()).toMatch(
      /somewhere new|implication, a tension, or a connection/i,
    );
  });

  it("guards the insight from being manufactured", () => {
    // A role instruction to "find connections" without this reads as licence to
    // invent one every turn.
    expect(promptProse()).toMatch(/manufactured insight is worse than none/i);
  });
});

describe("no provenance narration is mandated", () => {
  it("does not order the model to label general knowledge", () => {
    const prose = promptProse();
    // The user quoted our own example sentence back at us:
    //   "The document does not cover this, but based on general knowledge…"
    expect(prose).not.toContain("comes from general knowledge");
    expect(prose).not.toContain("The document does not cover this");
    expect(prose).not.toMatch(/MUST explicitly state that the information/i);
  });
});
