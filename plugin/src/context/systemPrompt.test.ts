import { describe, it, expect } from "vitest";
import { buildBaseSystemPrompt } from "./systemPrompt";

describe("buildBaseSystemPrompt", () => {
  it("always includes the base Obsidian assistant instructions and edit-block format", () => {
    const text = buildBaseSystemPrompt({ hasIncuratorMcp: false, planMode: false });
    expect(text).toContain("AI assistant embedded in Obsidian");
    expect(text).toContain("ai-agent-edit");
    expect(text).toContain("Do not suggest note edits");
    expect(text).not.toContain("incurator' MCP server enabled");
    expect(text).not.toContain("Plan mode is enabled");
  });

  it("adds the incurator-MCP addendum only when enabled", () => {
    const on = buildBaseSystemPrompt({ hasIncuratorMcp: true, planMode: false });
    expect(on).toContain("incurator' MCP server enabled");
    expect(on).toContain("ordinary requests such as explaining selected text");
    expect(on).not.toContain("ALWAYS start");
  });

  it("adds the plan-mode addendum only when in plan mode", () => {
    const on = buildBaseSystemPrompt({ hasIncuratorMcp: false, planMode: true });
    expect(on).toContain("Plan mode is enabled");
  });

  it("includes both addenda when both flags are set", () => {
    const both = buildBaseSystemPrompt({ hasIncuratorMcp: true, planMode: true });
    expect(both).toContain("incurator' MCP server enabled");
    expect(both).toContain("Plan mode is enabled");
  });
});
