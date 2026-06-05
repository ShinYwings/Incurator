import { describe, expect, it } from "vitest";
import { vi } from "vitest";
import {
  formatMcpToolResultForDisplay,
  formatQuotaErrorMessage,
  isQuotaErrorMessage,
  sanitizeOpenAIMessages,
  normalizeOpenAIContent,
} from "./llmClient";
import type { LLMMessage } from "../types";

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
      route: "global",
      trace_id: "QTR-1234abcd",
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

    expect(parsed.trace_id).toBe("QTR-1234abcd");
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

describe("sanitizeOpenAIMessages", () => {
  it("drops assistant turns with neither content nor tool_calls", () => {
    const messages: LLMMessage[] = [
      { role: "system", content: "sys" },
      { role: "user", content: "hi" },
      { role: "assistant", content: "" }, // degenerate turn → 400 culprit
      { role: "user", content: "again" },
    ];
    const out = sanitizeOpenAIMessages(messages);
    expect(out).toHaveLength(3);
    expect(out.some((m) => m.role === "assistant")).toBe(false);
  });

  it("keeps assistant tool-call turns even with empty content", () => {
    const messages: LLMMessage[] = [
      { role: "user", content: "do it" },
      {
        role: "assistant",
        content: "",
        tool_calls: [
          { id: "c1", type: "function", function: { name: "f", arguments: "{}" } },
        ],
      },
      { role: "tool", tool_call_id: "c1", content: "result" },
    ];
    const out = sanitizeOpenAIMessages(messages);
    expect(out).toHaveLength(3);
  });

  it("keeps normal assistant turns and non-assistant roles untouched", () => {
    const messages: LLMMessage[] = [
      { role: "user", content: "q" },
      { role: "assistant", content: "real answer" },
    ];
    expect(sanitizeOpenAIMessages(messages)).toEqual(messages);
  });

  it("treats whitespace-only assistant content as empty", () => {
    const messages: LLMMessage[] = [
      { role: "assistant", content: "   \n  " },
    ];
    expect(sanitizeOpenAIMessages(messages)).toHaveLength(0);
  });
});

describe("normalizeOpenAIContent", () => {
  const identity = (c: any) => c;

  it("emits empty string (not null) for an assistant tool-call turn", () => {
    const msg: LLMMessage = {
      role: "assistant",
      content: "",
      tool_calls: [
        { id: "c1", type: "function", function: { name: "f", arguments: "{}" } },
      ],
    };
    expect(normalizeOpenAIContent(msg, identity)).toBe("");
  });

  it("emits empty string for an empty tool result turn", () => {
    const msg: LLMMessage = { role: "tool", tool_call_id: "c1", content: "" };
    expect(normalizeOpenAIContent(msg, identity)).toBe("");
  });

  it("passes real content through the mapper", () => {
    const msg: LLMMessage = { role: "assistant", content: "hello" };
    expect(normalizeOpenAIContent(msg, identity)).toBe("hello");
  });

  it("keeps null for empty user/system turns", () => {
    expect(normalizeOpenAIContent({ role: "user", content: "" }, identity)).toBe(
      null
    );
  });
});
