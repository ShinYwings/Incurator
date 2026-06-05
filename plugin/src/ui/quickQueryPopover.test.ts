import { describe, it, expect } from "vitest";
import {
  buildQuickQueryMessages,
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
  });

  it("treats the selection as the primary context, not chat history", () => {
    const messages = buildQuickQueryMessages("Eq. (3)", "summarize");
    expect(String(messages[0].content)).toMatch(/selected/i);
    // Only the system + user temp query — no prior turns are appended.
    expect(messages.every((m) => m.role === "system" || m.role === "user")).toBe(
      true
    );
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
