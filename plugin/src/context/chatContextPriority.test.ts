import { describe, expect, it } from "vitest";
import {
  contextPriorityInstruction,
  contextPromptLabel,
  hasPrimaryUserContext,
  includedContextRefs,
  isPrimaryUserContext,
  shouldIncludeContext,
  shouldSuppressEditAffordances,
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
      filePath: "Research/config/curate.yml",
    };

    expect(contextPromptLabel(auto)).toBe(
      "Visible background context: curate.yml (file path: Research/config/curate.yml)"
    );
    expect(contextPriorityInstruction(true)).toContain("Primary user-selected context is the MAIN FOCUS");
    expect(contextPriorityInstruction(false)).toContain("Pinned and visible Obsidian contexts");
  });

  it("preserves exact vault paths for every prompt-included context priority", () => {
    const selected: ContextRef = {
      type: "selection",
      label: "Selected paragraph",
      content: "focus",
      filePath: "02_Wiki/Optimization/Auto Calibration.md",
    };
    const pinned: ContextRef = {
      type: "file",
      label: "Pinned note",
      content: "background",
      filePath: "03_Notes/Related Work.md",
      isPinned: true,
    };

    expect(contextPromptLabel(selected)).toBe(
      "Primary user-selected context: Selected paragraph (vault_link_target: [[02_Wiki/Optimization/Auto Calibration]])"
    );
    expect(contextPromptLabel(pinned)).toBe(
      "Pinned background context: Pinned note (vault_link_target: [[03_Notes/Related Work]])"
    );
  });

  it("preserves PDF suffixes and pages in explicit vault link targets", () => {
    const pdf: ContextRef = {
      type: "pdf-page",
      label: "Residual Learning p.7",
      content: "page context",
      filePath: "04_Resources/Residual Learning.pdf",
      pageNum: 7,
      isPinned: true,
    };

    expect(contextPromptLabel(pdf)).toBe(
      "Pinned background context: Residual Learning p.7 (vault_link_target: [[04_Resources/Residual Learning.pdf#page=7]])"
    );
  });

  it("does not present an external file path as a vault link target", () => {
    const external: ContextRef = {
      type: "image",
      label: "External diagram",
      content: "",
      filePath: "/Users/example/Desktop/diagram.png",
    };

    expect(contextPromptLabel(external)).toBe(
      "Primary user-selected context: External diagram (file path: /Users/example/Desktop/diagram.png)"
    );
    expect(contextPromptLabel(external)).not.toContain("vault_link_target");
  });

  it("treats pinned explicit snippets as primary while whole pinned docs stay background", () => {
    const pinnedSnippet: ContextRef = {
      type: "text",
      label: "Pinned selection from paper",
      content: "focus this exact passage",
      isPinned: true,
    };
    const pinnedWholePdf: ContextRef = {
      type: "pdf-page",
      label: "Paper p.4",
      content: "whole page background",
      isPinned: true,
    };
    const visibleMarkdown: ContextRef = {
      type: "file",
      label: "active.md",
      content: "visible file background",
      sourceViewType: "auto",
    };

    expect(isPrimaryUserContext(pinnedSnippet)).toBe(true);
    expect(isPrimaryUserContext(pinnedWholePdf)).toBe(false);
    expect(isPrimaryUserContext(visibleMarkdown)).toBe(false);
    expect(hasPrimaryUserContext([visibleMarkdown, pinnedWholePdf, pinnedSnippet])).toBe(true);
    expect(contextPromptLabel(pinnedSnippet)).toBe("Primary user-selected context: Pinned selection from paper");
    expect(contextPromptLabel(pinnedWholePdf)).toBe("Pinned background context: Paper p.4");
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

describe("shouldSuppressEditAffordances (v0.21.0 localized-question suppression)", () => {
  it("suppresses when a primary selection is present and the turn is not an edit request", () => {
    expect(
      shouldSuppressEditAffordances({ hasPrimarySelection: true, isEditRequest: false })
    ).toBe(true);
  });

  it("does NOT suppress when the latest turn is itself an edit request", () => {
    expect(
      shouldSuppressEditAffordances({ hasPrimarySelection: true, isEditRequest: true })
    ).toBe(false);
  });

  it("does NOT suppress when there is no primary selection", () => {
    expect(
      shouldSuppressEditAffordances({ hasPrimarySelection: false, isEditRequest: false })
    ).toBe(false);
    expect(
      shouldSuppressEditAffordances({ hasPrimarySelection: false, isEditRequest: true })
    ).toBe(false);
  });

  it("is unconditional w.r.t. prior turns — a fresh localized question after an edit still suppresses", () => {
    // The reported failure: an earlier whole-document edit set priorAnswerOpenedEditLoop
    // true, but the predicate intentionally does not consider it, so a later
    // Cmd+Shift+L question still suppresses edit affordances.
    expect(
      shouldSuppressEditAffordances({ hasPrimarySelection: true, isEditRequest: false })
    ).toBe(true);
  });
});
