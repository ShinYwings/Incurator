import { describe, expect, it } from "vitest";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

/** A substring matcher was used as an intent router in the sidechat, and it
 *  hijacked ordinary questions. Reported live: "수식 9가 어떻게 10으로 바뀌었는지"
 *  was answered with "No Git history found" for a PDF that is not in any repo,
 *  because `isHistoryRequest` matched the bare substring "바뀌".
 *
 *  These tests pin the removal by source, because the defect was the EXISTENCE
 *  of the router, not a wrong branch inside it. */
const VIEW = join(__dirname, "ChatSidebarView.ts");
const source = readFileSync(VIEW, "utf8");

describe("the sidechat does not guess git intent from prose", () => {
  it("has no prose git router at all", () => {
    expect(source).not.toContain("detectGitSidechatCommand");
    expect(source).not.toContain("runGitSidechatCommand");
    expect(existsSync(join(__dirname, "..", "gitSidechatCommands.ts"))).toBe(false);
  });

  it("cannot reach a git action from a chat message at all", () => {
    // The dangerous one: `/\bpush\b/` matched "push-broom", ordinary vocabulary
    // in light-field camera geometry, and reached `git push` on the vault with
    // no confirmation. Assert on the CALLS, not on prose: the comment left in
    // the source deliberately names `isPushRequest` so nobody rebuilds it.
    const code = source
      .split("\n")
      .filter((line) => !line.trim().startsWith("//"))
      .join("\n");
    for (const call of ["pushGitChanges(", "getGitStatus(", "getGitHistory("]) {
      expect(code).not.toContain(call);
    }
  });

  it("keeps the reason in the code so the router is not reinvented", () => {
    expect(source).toContain("No prose git router here, deliberately");
    expect(source).toContain("push-broom");
  });
});
