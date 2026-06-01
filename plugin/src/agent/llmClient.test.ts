import { describe, expect, it } from "vitest";
import { vi } from "vitest";
import { formatQuotaErrorMessage, isQuotaErrorMessage } from "./llmClient";

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
