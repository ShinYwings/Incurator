import { describe, expect, it } from "vitest";
import {
  contextPriorityInstruction,
  contextPromptLabel,
  hasPrimaryUserContext,
  includedContextRefs,
  isPrimaryUserContext,
  shouldIncludeContext,
} from "./chatContextPriority";
import type { ContextRef } from "../types";

describe("chat context priority", () => {
  it("treats non-pinned user-added context as the primary focus", () => {
    const selected: ContextRef = {
      type: "image",
      label: "PDF snip",
      content: "",
      imageBase64: "abc",
    };
    const pinned: ContextRef = {
      type: "pdf-page",
      label: "Paper p.4",
      content: "background",
      isPinned: true,
    };

    expect(isPrimaryUserContext(selected)).toBe(true);
    expect(isPrimaryUserContext(pinned)).toBe(false);
    expect(hasPrimaryUserContext([pinned, selected])).toBe(true);
    expect(contextPromptLabel(selected)).toBe("Primary user-selected context: PDF snip");
    expect(contextPromptLabel(pinned)).toBe("Pinned background context: Paper p.4");
  });

  it("labels visible auto context as background and emits matching instructions", () => {
    const auto: ContextRef = {
      type: "file",
      label: "curate.yml",
      content: "background",
      sourceViewType: "auto",
    };

    expect(contextPromptLabel(auto)).toBe("Visible background context: curate.yml");
    expect(contextPriorityInstruction(true)).toContain("Primary user-selected context is the focus");
    expect(contextPriorityInstruction(false)).toContain("Pinned and visible Obsidian context are background");
  });

  it("excludes invisible pinned context from prompt priority", () => {
    const hidden: ContextRef = {
      type: "pdf-page",
      label: "Hidden paper p.4",
      content: "background",
      isPinned: true,
      includeInPrompt: false,
    };
    const selected: ContextRef = {
      type: "selection",
      label: "Selected text",
      content: "focus",
    };

    expect(shouldIncludeContext(hidden)).toBe(false);
    expect(isPrimaryUserContext(hidden)).toBe(false);
    expect(includedContextRefs([hidden, selected])).toEqual([selected]);
    expect(hasPrimaryUserContext([hidden])).toBe(false);
    expect(contextPromptLabel(hidden)).toBe("Excluded context: Hidden paper p.4");
  });
});
