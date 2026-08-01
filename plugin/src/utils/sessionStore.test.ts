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
  failProcessAfterUpdate = false;
  failTempWriteAfterCreate = false;
  beforeProcess?: (path: string) => void;

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
    if (this.failTempWriteAfterCreate && path.includes(".tmp-")) {
      throw new Error("interrupted temp write");
    }
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

  async process(path: string, update: (raw: string) => string): Promise<string> {
    const beforeProcess = this.beforeProcess;
    this.beforeProcess = undefined;
    beforeProcess?.(path);
    const current = this.files.get(path);
    if (current === undefined) throw new Error("missing");
    const next = update(current);
    if (this.failProcessAfterUpdate) {
      this.failProcessAfterUpdate = false;
      throw new Error("interrupted process commit");
    }
    this.files.set(path, next);
    return next;
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

  it("merges a peer arrival visible at the atomic process boundary", async () => {
    const adapter = new MemoryAdapter();
    adapter.files.set(path, JSON.stringify(data("remote", 1)));
    adapter.beforeProcess = () => {
      adapter.files.set(
        path,
        JSON.stringify({
          chatSessions: [
            ...data("remote", 1).chatSessions,
            ...data("peer", 2).chatSessions,
          ],
          activeChatSessionId: "peer",
        })
      );
    };

    await writeMergedSessionStore(adapter, path, data("local", 3));

    const stored = JSON.parse(adapter.files.get(path) || "{}") as SessionData;
    expect(stored.chatSessions.map((session) => session.id).sort())
      .toEqual(["local", "peer", "remote"]);
  });

  it("honors a peer deletion tombstone arriving at commit time", async () => {
    const adapter = new MemoryAdapter();
    adapter.files.set(path, JSON.stringify(data("stale", 1)));
    adapter.beforeProcess = () => {
      adapter.files.set(
        path,
        JSON.stringify({
          ...data("stale", 1),
          deletedSessionIds: ["stale"],
        })
      );
    };

    await writeMergedSessionStore(adapter, path, data("stale", 2));

    const stored = JSON.parse(adapter.files.get(path) || "{}") as SessionData;
    expect(stored.chatSessions).toEqual([]);
    expect(stored.deletedSessionIds).toEqual(["stale"]);
  });

  it("preserves structural corruption injected at the process boundary", async () => {
    const adapter = new MemoryAdapter();
    adapter.files.set(path, JSON.stringify(data("existing", 1)));
    const corrupt = '{"chatSessions":';
    adapter.beforeProcess = () => adapter.files.set(path, corrupt);

    await expect(writeMergedSessionStore(adapter, path, data("new", 2)))
      .rejects.toBeInstanceOf(SessionStoreBlockedError);
    expect(adapter.files.get(path)).toBe(corrupt);
  });

  it("leaves the previous file intact when atomic process commit fails", async () => {
    const adapter = new MemoryAdapter();
    const original = JSON.stringify(data("existing", 1));
    adapter.files.set(path, original);
    adapter.failProcessAfterUpdate = true;

    await expect(writeMergedSessionStore(adapter, path, data("new", 2)))
      .rejects.toThrow("interrupted process commit");
    expect(adapter.files.get(path)).toBe(original);
    await expect(writeMergedSessionStore(adapter, path, data("recovered", 3)))
      .resolves.toBeDefined();
  });

  it("cleans a partially written temp sibling during initial creation", async () => {
    const adapter = new MemoryAdapter();
    adapter.failTempWriteAfterCreate = true;

    await expect(writeMergedSessionStore(adapter, path, data("new", 2)))
      .rejects.toThrow("interrupted temp write");
    expect(adapter.files.has(path)).toBe(false);
    expect([...adapter.files.keys()].filter((key) => key.includes(".tmp-"))).toEqual([]);
  });
});
