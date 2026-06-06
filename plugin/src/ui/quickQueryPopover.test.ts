import { describe, it, expect } from "vitest";
import {
  buildQuickQueryMessages,
  computeFloatingPosition,
  stripThinkingForDisplay,
} from "./quickQueryPopover";

describe("quick query: message building", () => {
  it("includes the selected passage and question as separate roles", () => {
    const messages = buildQuickQueryMessages("E = mc^2", "What does this mean?");
    expect(messages).toHaveLength(2);
    expect(messages[0].role).toBe("system");
    expect(messages[1].role).toBe("user");
    expect(messages[1].content).toContain("E = mc^2");
    expect(messages[1].content).toContain("What does this mean?");
    expect(messages[1].content).toContain("<primary_focus_selection>");
  });

  it("treats the selection as primary context without chat-sidebar history", () => {
    const messages = buildQuickQueryMessages("Eq. (3)", "summarize");
    expect(String(messages[0].content)).toMatch(/primary selected passage/i);
    // Only the system + user temp query — no sidebar turns are appended.
    expect(messages.every((m) => m.role === "system" || m.role === "user")).toBe(
      true
    );
    expect(String(messages[1].content)).not.toContain("<quick_query_followups>");
  });
});

describe("quick query: floating position (item 5)", () => {
  const viewport = { width: 1000, height: 800 };
  const size = { width: 380, height: 320 };

  it("places the element below the selection when there is room", () => {
    const pos = computeFloatingPosition(
      { top: 100, bottom: 120, left: 200 },
      size,
      viewport
    );
    expect(pos.top).toBe(126); // bottom + gap
    expect(pos.left).toBe(200);
  });

  it("flips above the selection when it would overflow the bottom", () => {
    const pos = computeFloatingPosition(
      { top: 700, bottom: 720, left: 200 },
      size,
      viewport
    );
    // 720 + 6 + 320 = 1046 > 792 -> flip above: 700 - 6 - 320 = 374
    expect(pos.top).toBe(374);
  });

  it("clamps horizontally so the element stays inside the viewport", () => {
    const pos = computeFloatingPosition(
      { top: 100, bottom: 120, left: 950 },
      size,
      viewport
    );
    // 950 + 380 > 1000 -> 1000 - 380 - 8 = 612
    expect(pos.left).toBe(612);
  });

  it("never positions above the top margin", () => {
    const pos = computeFloatingPosition(
      { top: 5, bottom: 790, left: 10 },
      size,
      { width: 1000, height: 795 }
    );
    expect(pos.top).toBeGreaterThanOrEqual(8);
  });
});

describe("quick query: thinking strip", () => {
  it("removes closed thinking/think/thought blocks", () => {
    expect(
      stripThinkingForDisplay("<thinking>plan</thinking>Answer text")
    ).toBe("Answer text");
    expect(stripThinkingForDisplay("<think>x</think>Y")).toBe("Y");
    expect(stripThinkingForDisplay("<thought>z</thought>Done")).toBe("Done");
  });

  it("hides an unclosed thinking block still streaming in", () => {
    expect(stripThinkingForDisplay("<thinking>still planning")).toBe("");
    expect(stripThinkingForDisplay("Answer<think>mid")).toBe("Answer");
  });

  it("leaves plain answers untouched", () => {
    expect(stripThinkingForDisplay("Just a clean answer.")).toBe(
      "Just a clean answer."
    );
  });
});

describe("quick query: latex normalization (item 17)", () => {
  it("normalizes LaTeX delimiters before markdown rendering", async () => {
    const { readFileSync } = await import("fs");
    const { fileURLToPath } = await import("url");
    const { join } = await import("path");
    const dir = fileURLToPath(new URL(".", import.meta.url));
    const source = readFileSync(join(dir, "quickQueryPopover.ts"), "utf8");

    expect(source).toContain(
      'import { normalizeLatexDelimiters } from "../utils/textUtils"'
    );
    expect(source).toContain(
      "normalizeLatexDelimiters(stripThinkingForDisplay(raw))"
    );
  });
});
