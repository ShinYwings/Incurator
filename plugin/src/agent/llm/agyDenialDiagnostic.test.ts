import { describe, expect, it } from "vitest";
import { extractAntigravityAnswerFromStderr } from "./messageUtils";

/**
 * A permission denial is a failure, not a reply.
 *
 * When agy's stdout is empty the client recovers stderr and promotes it to the
 * answer. The status-line filter did not recognise the auto-deny diagnostic, so
 * it survived, and the empty-answer check downstream never fired because the
 * recovered string was non-empty. The user was shown the CLI's internal
 * plumbing — including advice to pass `--dangerously-skip-permissions`, which
 * this repo forbids — rendered exactly like an answer to their question.
 *
 * Reported 2026-08-31: asking the popover for a reference title returned the
 * jetski denial text verbatim.
 */
describe("agy permission diagnostics are not answers", () => {
  const DENIAL = [
    'jetski: no output produced — a tool required the "read_url" permission that',
    "headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under",
    "permissions.allow in settings.json (e.g. $read_url$()). Alternatively, re-run",
    "with --dangerously-skip-permissions to auto-approve all tools.",
  ].join("\n");

  it("does not promote a denial diagnostic into an answer", () => {
    expect(extractAntigravityAnswerFromStderr(DENIAL)).toBe("");
  });

  it("recognises the denial whichever tool was denied", () => {
    for (const tool of ["read_url", "read_file", "command", "mcp"]) {
      const text = `jetski: no output produced — a tool required the "${tool}" permission that headless mode cannot prompt for, so it was auto-denied.`;
      expect(extractAntigravityAnswerFromStderr(text)).toBe("");
    }
  });

  it("still returns a real answer that merely talks about permissions", () => {
    const answer =
      "The paper's threat model assumes the attacker has read permission on the " +
      "cache directory, which is why section 4 proposes per-tenant keys.";
    expect(extractAntigravityAnswerFromStderr(answer)).toBe(answer);
  });

  it("keeps a real answer that follows noise on earlier lines", () => {
    const mixed = "Loading model...\nReference [12] is “Neural Radiance Fields”.";
    expect(extractAntigravityAnswerFromStderr(mixed)).toContain(
      "Neural Radiance Fields"
    );
  });
});
