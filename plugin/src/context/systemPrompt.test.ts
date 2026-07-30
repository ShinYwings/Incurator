import { describe, it, expect } from "vitest";
import { buildBaseSystemPrompt, editableSelectionInstruction, getEditLoopContract, wrapLatestUserMessageForLanguageBridge } from "./systemPrompt";

describe("buildBaseSystemPrompt", () => {
  it("always includes the base Obsidian assistant instructions and edit-block format", () => {
    const text = buildBaseSystemPrompt({ hasExternalIncuratorMcp: false, planMode: false });
    expect(text).toContain("AI assistant embedded in Obsidian");
    expect(text).toContain("ai-agent-edit");
    expect(text).toContain("Do not suggest note edits");
    expect(text).toContain("use English only as the internal working language");
    expect(text).toContain("answer in that same language");
    expect(text).toContain("English latest requests must receive English final answers");
    expect(text).toContain("visible Korean Markdown context");
    expect(text).toContain("Preserve the user's syntax form");
    expect(text).toContain("First understand the user's edit intent");
    expect(text).toContain("selected PDF/text region as the example");
    expect(text).toContain("[[vault/relative/path|label]]");
    expect(text).toContain("Copy supplied vault_link_target values exactly");
    expect(text).toContain("Never invent a vault path");
    expect(text).toContain("uncertain plain-text page names");
    // Item 17: the math instruction must not model backtick-wrapped math and
    // must forbid it explicitly, so the LLM stops emitting `$x$`.
    expect(text).toContain("Never wrap a math expression in inline-code backticks");
    expect(text).not.toContain("(e.g., `$x = 2$`)");
    expect(text).not.toContain("external 'incurator' MCP server enabled");
    expect(text).not.toContain("Plan mode is enabled");
  });

  it("adds the external incurator-MCP addendum only when enabled", () => {
    const on = buildBaseSystemPrompt({ hasExternalIncuratorMcp: true, planMode: false });
    expect(on).toContain("external 'incurator' MCP server enabled");
    expect(on).toContain("ordinary requests such as explaining selected text");
    expect(on).toContain("workspace_path");
    expect(on).not.toContain("ALWAYS start");
  });

  it("adds the plan-mode addendum only when in plan mode", () => {
    const on = buildBaseSystemPrompt({ hasExternalIncuratorMcp: false, planMode: true });
    expect(on).toContain("Plan mode is enabled");
  });

  it("includes both addenda when both flags are set", () => {
    const both = buildBaseSystemPrompt({ hasExternalIncuratorMcp: true, planMode: true });
    expect(both).toContain("external 'incurator' MCP server enabled");
    expect(both).toContain("Plan mode is enabled");
  });

  it("wraps the latest user message with an explicit detected-language bridge", () => {
    const text = wrapLatestUserMessageForLanguageBridge("이 논문의 핵심이 뭐야?", "Korean");
    expect(text).toContain("input language is Korean");
    expect(text).toContain("write the final answer in Korean");
    expect(text).toContain("internally in English");
    expect(text).toContain("Detect it fresh from this request");
    expect(text).toContain("<original_user_request>");
    expect(text).toContain("이 논문의 핵심이 뭐야?");
  });

  it("falls back to generic original-language wording when no language is given", () => {
    const text = wrapLatestUserMessageForLanguageBridge("What is this?");
    expect(text).toContain("original input language");
    expect(text).toContain("<original_user_request>");
    expect(text).toContain("What is this?");
  });

  it("adds an edit intent instruction only for editable selections", () => {
    expect(editableSelectionInstruction(false)).toBe("");
    const text = editableSelectionInstruction(true);
    expect(text).toContain("editable Markdown line-range context");
    expect(text).toContain("ai-agent-edit");
    expect(text).toContain("all similar occurrences");
    expect(text).toContain("<open_markdown_edit_targets>");
    expect(text).toContain("HTML as HTML");
    expect(text).toContain("If the latest request is only asking a question");
  });

  it("adds edit instructions for open Markdown targets even without a Markdown line selection", () => {
    const text = editableSelectionInstruction(false, true);
    expect(text).toContain("open Markdown file as the edit target");
    expect(text).toContain("ai-agent-edit");
  });
});

describe("getEditLoopContract", () => {
  it("instructs the agent to emit the four canonical phase markers in order", () => {
    const text = getEditLoopContract();
    expect(text).toContain("[[PHASE:ANALYSED]]");
    expect(text).toContain("[[PHASE:REVIEWED]]");
    expect(text).toContain("[[PHASE:UPDATED]]");
    // The contract must name the loop and tie it to ai-agent-edit proposals.
    expect(text).toContain("Analysed");
    expect(text).toContain("Reviewed");
    expect(text).toContain("Updated");
    expect(text).toContain("ai-agent-edit");
  });

  it("places the first REVIEWED before UPDATED and a second REVIEWED after it", () => {
    const text = getEditLoopContract();
    const firstReviewed = text.indexOf("[[PHASE:REVIEWED]]");
    const updated = text.indexOf("[[PHASE:UPDATED]]");
    const lastReviewed = text.lastIndexOf("[[PHASE:REVIEWED]]");
    expect(firstReviewed).toBeGreaterThanOrEqual(0);
    expect(firstReviewed).toBeLessThan(updated);
    expect(updated).toBeLessThan(lastReviewed);
  });

  it("does not require the loop for pure question answering", () => {
    const text = getEditLoopContract();
    expect(text.toLowerCase()).toContain("only when you propose");
  });

  it("instructs the agent that edits are proposed, not applied (Bug 4 framing)", () => {
    const text = getEditLoopContract();
    expect(text).toContain("PROPOSED");
    expect(text.toLowerCase()).toContain("pending the user's review");
    expect(text.toLowerCase()).toContain("do not claim they are already applied");
  });
});
