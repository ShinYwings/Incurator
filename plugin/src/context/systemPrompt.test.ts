import { describe, it, expect } from "vitest";
import { buildBaseSystemPrompt, editableSelectionInstruction, wrapLatestUserMessageForLanguageBridge } from "./systemPrompt";

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
