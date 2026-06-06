import { describe, expect, it } from "vitest";
import { detectGitSidechatCommand } from "./gitSidechatCommands";

describe("git sidechat command detection", () => {
  it("routes Korean push requests to push", () => {
    expect(detectGitSidechatCommand("push해줘")?.kind).toBe("push");
    expect(detectGitSidechatCommand("이 vault GitHub에 올려줘")?.kind).toBe("push");
  });

  it("routes GitHub status questions to status", () => {
    expect(detectGitSidechatCommand("GitHub 상태 어때?")?.kind).toBe("status");
    expect(detectGitSidechatCommand("Any unpushed changes?")?.kind).toBe("status");
  });

  it("uses selected Markdown text for history lookup", () => {
    const command = detectGitSidechatCommand(
      "이 내용 예전에 어떻게 바뀌었는지 히스토리 찾아줘",
      [
        {
          type: "line-range",
          label: "note.md lines 3-4",
          filePath: "/vault/note.md",
          content: "selected\nphrase",
        },
      ],
      { viewType: "markdown", absolutePath: "/vault/note.md" }
    );

    expect(command).toEqual({
      kind: "history",
      filePath: "/vault/note.md",
      queryText: "selected phrase",
    });
  });
});
