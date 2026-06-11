import { describe, expect, it } from "vitest";
import { isSelectionRelevantKey } from "./selectionKeys";

describe("isSelectionRelevantKey", () => {
  it("matches extension keys (arrows, Home/End, PageUp/Down)", () => {
    for (const k of ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]) {
      expect(isSelectionRelevantKey(k)).toBe(true);
    }
  });

  it("matches collapse/edit keys so a lingering button is dismissed", () => {
    for (const k of ["Escape", "Backspace", "Delete", "Enter"]) {
      expect(isSelectionRelevantKey(k)).toBe(true);
    }
  });

  it("matches a/A for Ctrl/Cmd+A select-all", () => {
    expect(isSelectionRelevantKey("a")).toBe(true);
    expect(isSelectionRelevantKey("A")).toBe(true);
  });

  it("ignores ordinary typing keys", () => {
    for (const k of ["b", "1", " ", "Tab", "Shift", "Control", "Meta"]) {
      expect(isSelectionRelevantKey(k)).toBe(false);
    }
  });
});
