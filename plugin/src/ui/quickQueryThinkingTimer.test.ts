import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

/**
 * v0.42.0 perceived-latency contract for the Quick Query popover.
 *
 * Measured on this repo's own machine: a CLI-backed provider round-trip costs
 * 8.2-12.2s even for a one-word answer, while the CLI binary itself starts in
 * 0.29s and an Incurator backend round-trip is 0.20s. The wait is the provider
 * service handshake, not inference and not Incurator overhead — and
 * `agy --print` delivers nothing until the whole answer is ready, so the
 * popover's static "Thinking…" was indistinguishable from a hang for the entire
 * wait. (That ambiguity actively caused a misdiagnosis: a real crash was first
 * read as "just slow".) The sidebar already ticks elapsed seconds; the popover
 * must too.
 */
const source = () =>
  readFileSync(join(__dirname, "quickQueryPopover.ts"), "utf8");

describe("Quick Query popover elapsed-time feedback", () => {
  it("ticks elapsed seconds while waiting on the provider", () => {
    const src = source();
    expect(src).toContain("private thinkingTimer");
    expect(src).toContain("startThinkingTimer");
    expect(src).toContain("Thinking… (${elapsed}s)");
  });

  it("starts the readout before the request begins", () => {
    const src = source();
    expect(src).toContain("this.startThinkingTimer(loadingEl)");
  });

  it("does not overwrite the ticking readout with a frozen label", () => {
    const src = source();
    // The old streaming callback rendered `display || "⏳ Thinking…"` on every
    // chunk, replacing the live readout with static text.
    expect(src).not.toContain('text: display || "⏳ Thinking…"');
    expect(src).toContain("if (!display) return;");
  });

  it("stops the timer on success, error, and teardown", () => {
    const src = source();
    const stops = src.match(/this\.stopThinkingTimer\(\)/g) ?? [];
    // startThinkingTimer's own reset, the stream's first-text path, the catch,
    // the success path, the tick self-guard, and removePopover.
    expect(stops.length).toBeGreaterThanOrEqual(5);
    expect(src).toMatch(/private removePopover\(\): void \{[\s\S]{0,200}stopThinkingTimer/);
  });

  it("stops ticking once the popover is gone", () => {
    const src = source();
    expect(src).toMatch(/if \(!this\.popoverEl\) \{\s*\n\s*this\.stopThinkingTimer\(\);/);
  });
});
