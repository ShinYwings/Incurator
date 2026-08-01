import { describe, expect, it } from "vitest";
import type { SessionData } from "../types";
import {
  SessionStoreBlockedError,
  readSessionStore,
  writeMergedSessionStore,
} from "./sessionStore";
import type { VaultTextAdapter } from "./durableJsonStore";

class MemoryAdapter implements VaultTextAdapter {
  readonly files = new Map<string, string>();
  readonly unreadable = new Set<string>();
  failRename = false;

  async exists(path: string): Promise<boolean> {
    return this.files.has(path);
  }

  async read(path: string): Promise<string> {
    if (this.unreadable.has(path)) throw new Error("permission denied");
    const value = this.files.get(path);
    if (value === undefined) throw new Error("missing");
    return value;
  }

  async write(path: string, data: string): Promise<void> {
    this.files.set(path, data);
  }

  async rename(source: string, target: string): Promise<void> {
    if (this.failRename) throw new Error("interrupted rename");
    const value = this.files.get(source);
    if (value === undefined) throw new Error("missing temp");
    this.files.set(target, value);
    this.files.delete(source);
  }

  async remove(path: string): Promise<void> {
    this.files.delete(path);
  }
}

function data(id: string, updatedAt: number): SessionData {
  return {
    chatSessions: [
      {
        id,
        title: id,
        createdAt: updatedAt,
        updatedAt,
        messages: [],
      },
    ],
    activeChatSessionId: id,
  };
}

describe("durable session store", () => {
  const path = ".curator/sessions.json";

  it("distinguishes missing, corrupt, and unreadable canonical state", async () => {
    const adapter = new MemoryAdapter();
    expect((await readSessionStore(adapter, path)).kind).toBe("missing");

    adapter.files.set(path, '{"chatSessions":');
    expect((await readSessionStore(adapter, path)).kind).toBe("corrupt");

    adapter.files.set(path, '{"chatSessions":[{"id":"damaged","messages":null}]}');
    expect((await readSessionStore(adapter, path)).kind).toBe("corrupt");

    adapter.unreadable.add(path);
    expect((await readSessionStore(adapter, path)).kind).toBe("unreadable");
  });

  it("preserves corrupt bytes and blocks ordinary saves", async () => {
    const adapter = new MemoryAdapter();
    const corrupt = '{"chatSessions":';
    adapter.files.set(path, corrupt);

    await expect(writeMergedSessionStore(adapter, path, data("local", 2)))
      .rejects.toBeInstanceOf(SessionStoreBlockedError);
    expect(adapter.files.get(path)).toBe(corrupt);
  });

  it("serializes concurrent merge-on-save operations", async () => {
    const adapter = new MemoryAdapter();
    adapter.files.set(path, JSON.stringify(data("remote", 1)));

    await Promise.all([
      writeMergedSessionStore(adapter, path, data("linux", 2)),
      writeMergedSessionStore(adapter, path, data("macos", 3)),
    ]);

    const stored = JSON.parse(adapter.files.get(path) || "{}") as SessionData;
    expect(stored.chatSessions.map((session) => session.id).sort())
      .toEqual(["linux", "macos", "remote"]);
  });

  it("leaves the previous file intact when atomic rename fails", async () => {
    const adapter = new MemoryAdapter();
    const original = JSON.stringify(data("existing", 1));
    adapter.files.set(path, original);
    adapter.failRename = true;

    await expect(writeMergedSessionStore(adapter, path, data("new", 2)))
      .rejects.toThrow("interrupted rename");
    expect(adapter.files.get(path)).toBe(original);
    expect([...adapter.files.keys()].filter((key) => key.includes(".tmp-"))).toEqual([]);
  });
});
