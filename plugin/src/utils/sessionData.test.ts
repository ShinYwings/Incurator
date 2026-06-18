import { describe, expect, it } from "vitest";
import type { ChatSession, SessionData } from "../types";
import { mergeSessionData, normalizeSessionData, sanitizeSessionDataForSync } from "./sessionData";

function session(id: string, updatedAt: number, messages = 1): ChatSession {
  return {
    id,
    title: id,
    createdAt: updatedAt - 10,
    updatedAt,
    messages: Array.from({ length: messages }, (_, index) => ({
      id: `${id}-${index}`,
      role: "user",
      content: `${id} ${index}`,
      timestamp: updatedAt + index,
    })),
  };
}

describe("sessionData", () => {
  it("normalizes missing session data", () => {
    expect(normalizeSessionData({})).toEqual({
      chatSessions: [],
      activeChatSessionId: undefined,
      deletedSessionIds: [],
    });
  });

  it("preserves remote sessions when saving local sessions", () => {
    const local: SessionData = {
      chatSessions: [session("linux", 200)],
      activeChatSessionId: "linux",
    };
    const remote: SessionData = {
      chatSessions: [session("macos", 100)],
      activeChatSessionId: "macos",
    };

    const merged = mergeSessionData(local, remote);

    expect(merged.chatSessions.map((s) => s.id)).toEqual(["linux", "macos"]);
    expect(merged.activeChatSessionId).toBe("linux");
  });

  it("does not resurrect sessions deleted on another synced device", () => {
    const merged = mergeSessionData(
      { chatSessions: [], deletedSessionIds: ["old"] },
      { chatSessions: [session("old", 100)], activeChatSessionId: "old" }
    );

    expect(merged.chatSessions).toEqual([]);
    expect(merged.activeChatSessionId).toBeUndefined();
    expect(merged.deletedSessionIds).toContain("old");
  });

  it("keeps the newer copy of the same session", () => {
    const merged = mergeSessionData(
      { chatSessions: [session("shared", 100, 1)] },
      { chatSessions: [session("shared", 200, 2)] }
    );

    expect(merged.chatSessions).toHaveLength(1);
    expect(merged.chatSessions[0].updatedAt).toBe(200);
    expect(merged.chatSessions[0].messages).toHaveLength(2);
  });

  it("strips device-local PDF paths from synced context refs", () => {
    const raw = sanitizeSessionDataForSync({
      chatSessions: [{
        ...session("shared", 100),
        messages: [{
          id: "m1",
          role: "user",
          content: "explain this pdf",
          timestamp: 100,
          contextRefs: [{
            type: "pdf-page",
            label: "Paper p.3",
            content: "text",
            filePath: "/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/Paper.pdf",
            fileHash: "abc123",
            zoteroAttachmentKey: "ZOTKEY",
            pageNum: 3,
            backendStatus: {
              state: "l3_ready",
              sourcePath: "/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/Paper.pdf",
              currentPath: "/Users/shin/old/Paper.pdf",
              candidatePath: "/home/shin/Documents/Zotero/Paper.pdf",
            },
          }],
        }],
      }],
      activeChatSessionId: "shared",
    });

    const ref = raw.chatSessions[0].messages[0].contextRefs?.[0];
    expect(ref?.filePath).toBeUndefined();
    expect(ref?.backendStatus).toBeUndefined();
    expect(ref?.fileHash).toBe("abc123");
    expect(ref?.zoteroAttachmentKey).toBe("ZOTKEY");
    expect(ref?.pageNum).toBe(3);
  });

  it("keeps vault-relative context paths in synced sessions", () => {
    const raw = normalizeSessionData({
      chatSessions: [{
        ...session("vault", 100),
        messages: [{
          id: "m1",
          role: "user",
          content: "use note",
          timestamp: 100,
          contextRefs: [{
            type: "file",
            label: "Note.md",
            content: "note",
            filePath: "03_Notes/Note.md",
          }],
        }],
      }],
    });

    expect(raw.chatSessions[0].messages[0].contextRefs?.[0].filePath).toBe("03_Notes/Note.md");
  });
});
