import { describe, expect, it } from "vitest";
import {
  PROMPT_HISTORY_CHAR_LIMIT,
  PROMPT_HISTORY_MESSAGE_LIMIT,
  selectPromptHistory,
} from "./promptHistory";

function message(role: "user" | "assistant" | "system", content: string) {
  return { role, content } as const;
}

describe("selectPromptHistory", () => {
  it("keeps the latest four non-system messages in order", () => {
    const input = [
      message("system", "system instructions"),
      message("user", "old question"),
      message("assistant", "old answer"),
      message("user", "recent question"),
      message("assistant", "recent answer"),
      message("user", "latest question"),
      message("assistant", "latest answer"),
    ];

    expect(selectPromptHistory(input)).toEqual([
      message("user", "recent question"),
      message("assistant", "recent answer"),
      message("user", "latest question"),
      message("assistant", "latest answer"),
    ]);
  });

  it("stops at the character budget without dropping the newest message", () => {
    const input = [
      message("user", "old question"),
      message("assistant", "previous answer"),
      message("user", "latest question"),
    ];

    expect(selectPromptHistory(input, 4, 30)).toEqual([
      message("assistant", "previous answer"),
      message("user", "latest question"),
    ]);
  });

  it("keeps an oversized latest message because it contains the question", () => {
    const input = [message("user", "x".repeat(PROMPT_HISTORY_CHAR_LIMIT + 1))];

    expect(selectPromptHistory(input)).toEqual(input);
  });

  it("does not mutate a short input transcript", () => {
    const input = [message("user", "question"), message("assistant", "answer")];
    const selected = selectPromptHistory(input);

    expect(selected).toEqual(input);
    expect(selected).not.toBe(input);
  });

  it("uses explicit limits when a caller needs a smaller prompt", () => {
    const input = [
      message("user", "one"),
      message("assistant", "two"),
      message("user", "three"),
    ];

    expect(selectPromptHistory(input, 2, 100)).toEqual([
      message("assistant", "two"),
      message("user", "three"),
    ]);
    expect(PROMPT_HISTORY_MESSAGE_LIMIT).toBe(4);
  });
});
