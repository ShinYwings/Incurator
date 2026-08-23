import { describe, expect, it } from "vitest";

import { mergeSessionData, normalizeSessionData } from "./sessionData";
import type { ContextRef, SessionData } from "../types";

/**
 * Auto context refs carry the bulk of `sessions.json` and none of it is ever
 * read back.
 *
 * Measured on the reference vault (14.52 MB file, 338 auto refs of 369):
 *
 * | field on an auto ref | size | read from history? |
 * |---|---|---|
 * | `content`      | 5.29 MB | no |
 * | `outline`      | 1.90 MB | no |
 * | `windowPages`  | 0.60 MB | no |
 * | `imageBase64`  | 4.07 MB | YES — the transcript renders a chip thumbnail |
 *
 * `buildLLMMessages` skips auto refs entirely (`ChatSidebarView.ts`,
 * `if (ref.sourceViewType === "auto") continue;`) BEFORE reading any payload,
 * and the next turn rebuilds auto refs fresh from the live context
 * (`buildAutoContextRefs`). So the first three are written to disk, synced to
 * every device, and never looked at again.
 *
 * `imageBase64` is deliberately kept: the transcript renders it as an inline
 * thumbnail, so dropping it would remove something the user can see. That is a
 * visible trade and belongs to the retention work, not here.
 */
const auto = (over: Partial<ContextRef> = {}): ContextRef =>
  ({
    type: "file",
    label: "paper.pdf",
    sourceViewType: "auto",
    includeInPrompt: true,
    content: "x".repeat(5000),
    outline: [{ title: "1 Intro", pageNum: 1 }],
    windowPages: [{ pageNum: 1, text: "y".repeat(3000) }],
    imageBase64: "AAAA",
    ...over,
  }) as unknown as ContextRef;

const wrap = (refs: ContextRef[]): SessionData =>
  ({
    chatSessions: [
      {
        id: "s1",
        title: "t",
        createdAt: 1,
        updatedAt: 2,
        messages: [{ id: "m1", role: "user", content: "hi", contextRefs: refs }],
      },
    ],
    deletedSessionIds: [],
  }) as unknown as SessionData;

const firstRef = (d: SessionData): ContextRef =>
  d.chatSessions[0].messages[0].contextRefs![0];

describe("auto context ref payloads are not persisted", () => {
  it("drops content, outline and windowPages from an auto ref", () => {
    const ref = firstRef(normalizeSessionData(wrap([auto()])));
    // Emptied, not deleted: `content` is required on ContextRef, and every
    // reader gates on truthiness, so "" is equivalent at 14 bytes.
    expect(ref.content).toBe("");
    expect(ref.outline).toBeUndefined();
    expect(ref.windowPages).toBeUndefined();
  });

  it("keeps imageBase64, which the transcript renders as a chip thumbnail", () => {
    expect(firstRef(normalizeSessionData(wrap([auto()]))).imageBase64).toBe("AAAA");
  });

  it("keeps the ref's identity so the chip still renders", () => {
    const ref = firstRef(normalizeSessionData(wrap([auto({ label: "x.pdf" })])));
    expect(ref.label).toBe("x.pdf");
    expect(ref.type).toBe("file");
    expect(ref.sourceViewType).toBe("auto");
  });

  it("leaves NON-auto refs untouched — those payloads are re-sent to the model", () => {
    const pinned = auto({ sourceViewType: undefined });
    const ref = firstRef(normalizeSessionData(wrap([pinned])));
    expect(ref.content).toHaveLength(5000);
    expect(ref.outline).toBeDefined();
    expect(ref.windowPages).toBeDefined();
  });

  it("survives a merge round-trip without resurrecting the payloads", () => {
    const a = normalizeSessionData(wrap([auto()]));
    const b = normalizeSessionData(wrap([auto()]));
    expect(firstRef(mergeSessionData(a, b)).content).toBe("");
  });
});
