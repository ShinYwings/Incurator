import { describe, expect, it } from "vitest";

import { mergeSessionData } from "./sessionData";
import type { ChatSession, SessionData } from "../types";

/**
 * The 30-session cap never bounded anything, and could not have.
 *
 * `ChatSidebarView` trimmed `chatSessions` with `.slice(0, 30)` WITHOUT adding
 * the dropped ids to `deletedSessionIds`. `mergeSessionData` seeds its map from
 * the on-disk canonical first and skips only tombstoned ids — so every trimmed
 * session came straight back on the very next save, which happens immediately
 * after the trim.
 *
 * This test pins the mechanism, so that nobody "fixes" the cap by tombstoning
 * on trim. Tombstoning is not a bug fix, it is **deleting the user's chat
 * history on every device** — a retention decision that needs their consent, and
 * that is what the GC work exists for.
 */
const session = (id: string, updatedAt: number): ChatSession =>
  ({ id, title: id, createdAt: 1, updatedAt, messages: [] }) as unknown as ChatSession;

describe("the 30-session cap is not a retention mechanism", () => {
  it("a trimmed-but-not-tombstoned session is resurrected by the next merge", () => {
    const onDisk: SessionData = {
      chatSessions: [session("keep", 2), session("trimmed", 1)],
      deletedSessionIds: [],
    } as unknown as SessionData;

    // What `.slice(0, 30)` produced: "trimmed" simply absent, no tombstone.
    const afterTrim: SessionData = {
      chatSessions: [session("keep", 2)],
      deletedSessionIds: [],
    } as unknown as SessionData;

    const merged = mergeSessionData(afterTrim, onDisk);

    expect(merged.chatSessions.map((s) => s.id).sort()).toEqual(["keep", "trimmed"]);
  });

  it("tombstoning WOULD delete it — which is why trimming must not tombstone", () => {
    const onDisk: SessionData = {
      chatSessions: [session("keep", 2), session("trimmed", 1)],
      deletedSessionIds: [],
    } as unknown as SessionData;
    const afterTombstone: SessionData = {
      chatSessions: [session("keep", 2)],
      deletedSessionIds: ["trimmed"],
    } as unknown as SessionData;

    const merged = mergeSessionData(afterTombstone, onDisk);

    // Gone from every device. Correct for an explicit delete; catastrophic as a
    // side effect of a display cap.
    expect(merged.chatSessions.map((s) => s.id)).toEqual(["keep"]);
  });
});
