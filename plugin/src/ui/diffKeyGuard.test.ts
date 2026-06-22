import { describe, expect, it } from "vitest";
import { shouldHandleDiffShortcut } from "./diffKeyGuard";

// Minimal fake elements with just the `.contains` used by the predicate.
const node = (children: unknown[]) => ({
  contains: (other: unknown) => children.includes(other),
});

describe("shouldHandleDiffShortcut", () => {
  const focusInEditor = {};
  const focusInToolbar = {};
  const focusInChat = {};
  const cmEditor = node([focusInEditor]);
  const toolbar = node([focusInToolbar]);

  it("fires when focus is inside the diff editor", () => {
    expect(shouldHandleDiffShortcut(focusInEditor, cmEditor, toolbar)).toBe(true);
  });

  it("fires when focus is inside the toolbar", () => {
    expect(shouldHandleDiffShortcut(focusInToolbar, cmEditor, toolbar)).toBe(true);
  });

  it("does NOT fire when focus is in the chat input (the core bug)", () => {
    expect(shouldHandleDiffShortcut(focusInChat, cmEditor, toolbar)).toBe(false);
  });

  it("does NOT fire when there is no focused element", () => {
    expect(shouldHandleDiffShortcut(null, cmEditor, toolbar)).toBe(false);
  });

  it("is safe when editor/toolbar refs are missing", () => {
    expect(shouldHandleDiffShortcut(focusInEditor, null, null)).toBe(false);
  });
});
