import { describe, expect, it } from "vitest";
import type { ChatSession } from "../types";
import {
  deriveChatSessionTitle,
  formatRelativeSessionTime,
} from "./chatSessionSummary";

function session(messages: ChatSession["messages"]): ChatSession {
  return {
    id: "session-1",
    title: "New chat",
    createdAt: 1_000,
    updatedAt: 1_000,
    messages,
  };
}

describe("chatSessionSummary", () => {
  it("derives the title from the first answer after the first question", () => {
    const title = deriveChatSessionTitle(
      session([
        {
          id: "u1",
          role: "user",
          content: "이 논문 뭐야?",
          timestamp: 1_000,
        },
        {
          id: "a1",
          role: "assistant",
          content: "This paper explains projective geometry constraints for multi-view reconstruction.",
          timestamp: 2_000,
        },
      ])
    );

    expect(title).toBe("This paper explains projective geometry...");
  });

  it("skips the reasoning block and titles from the real answer", () => {
    const title = deriveChatSessionTitle(
      session([
        { id: "u1", role: "user", content: "이 내용 설명해줘", timestamp: 1_000 },
        {
          id: "a1",
          role: "assistant",
          content:
            "<think>\nThe user selected a cross-reference, let me resolve it.\n</think>\n\nJacobi's algorithm computes eigenvalues by iterative rotation.",
          timestamp: 2_000,
        },
      ])
    );

    expect(title).toBe("Jacobi's algorithm computes eigenvalues...");
  });

  it("does not title from an unclosed reasoning block", () => {
    const title = deriveChatSessionTitle(
      session([
        { id: "u1", role: "user", content: "설명해줘", timestamp: 1_000 },
        {
          id: "a1",
          role: "assistant",
          content: "<think>\nStill reasoning, stream cut off here",
          timestamp: 2_000,
        },
      ])
    );

    // No real answer text → falls back to the question, never "<think>".
    expect(title).toBe("설명해줘");
  });

  it("falls back to the first question while the first answer is not available", () => {
    const title = deriveChatSessionTitle(
      session([
        {
          id: "u1",
          role: "user",
          content: "이 PDF에서 epipolar geometry 설명해줘",
          timestamp: 1_000,
        },
      ])
    );

    expect(title).toBe("이 PDF에서 epipolar geometry 설명해줘");
  });

  it("formats relative activity from the current time", () => {
    const now = Date.UTC(2026, 5, 2, 12, 0, 0);

    expect(formatRelativeSessionTime(now - 30_000, now)).toBe("Just now");
    expect(formatRelativeSessionTime(now - 12 * 60_000, now)).toBe("12m ago");
    expect(formatRelativeSessionTime(now - 3 * 60 * 60_000, now)).toBe("3h ago");
  });
});
