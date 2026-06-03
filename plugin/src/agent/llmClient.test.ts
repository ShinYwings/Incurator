import { describe, expect, it } from "vitest";
import { vi } from "vitest";
import {
  formatMcpToolResultForDisplay,
  formatQuotaErrorMessage,
  isQuotaErrorMessage,
} from "./llmClient";

vi.mock("obsidian", () => ({
  Notice: class Notice {
    constructor(_message: string) {}
  },
  requestUrl: async () => ({ json: {} }),
}));

describe("LLM quota errors", () => {
  it("recognizes quota and capacity failures from CLI/API providers", () => {
    expect(isQuotaErrorMessage("RESOURCE_EXHAUSTED: quota exceeded")).toBe(true);
    expect(isQuotaErrorMessage("429 rate limit reached")).toBe(true);
    expect(isQuotaErrorMessage("No capacity available")).toBe(true);
    expect(isQuotaErrorMessage("plain auth error")).toBe(false);
  });

  it("formats a user-visible sidechat message", () => {
    const text = formatQuotaErrorMessage("antigravity", "Individual quota reached");
    expect(text).toContain("quota or capacity");
    expect(text).toContain("Switch provider/model");
  });
});

describe("MCP tool result display", () => {
  it("keeps curator_query trace parseable while dropping oversized answers", () => {
    const raw = JSON.stringify({
      ok: true,
      question: "What is result 19.4?",
      answer: "A".repeat(4000),
      exhibition_id: "EXH-1234abcd",
      cache_hit: false,
      trace: {
        matched_concepts: ["CON-1234abcd"],
        source_ids: [],
        source_paths: ["03_Concepts/CON-1234abcd.md"],
        latency_ms: 42,
        l3_complete: true,
      },
    });

    const display = formatMcpToolResultForDisplay("mcp_incurator_curator_query", raw);
    const parsed = JSON.parse(display);

    expect(parsed.exhibition_id).toBe("EXH-1234abcd");
    expect(parsed.trace.matched_concepts).toEqual(["CON-1234abcd"]);
    expect(parsed.answer).toBeUndefined();
    expect(display).not.toContain("AAAA");
  });

  it("still truncates non-curator tool results", () => {
    const display = formatMcpToolResultForDisplay("mcp_other_tool", "A".repeat(1000));

    expect(display.length).toBeLessThan(650);
    expect(display.endsWith("…")).toBe(true);
  });
});
