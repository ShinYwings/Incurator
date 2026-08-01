import { EventEmitter } from "events";
import { afterEach, describe, expect, it, vi } from "vitest";

const processMocks = vi.hoisted(() => ({ spawn: vi.fn() }));

vi.mock("child_process", () => ({
  spawn: processMocks.spawn,
}));

vi.mock("obsidian", () => ({
  Notice: class Notice {
    constructor(_message: string) {}
  },
}));

import { MCPClient } from "./mcpClient";

class FakeMcpProcess extends EventEmitter {
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  exitCode: number | null = null;
  killedSignals: string[] = [];
  respond = true;
  exitOnSignal: string | null = null;
  stdin = {
    writable: true,
    write: vi.fn((data: string) => {
      const message = JSON.parse(data.trim()) as {
        id?: number;
        method: string;
      };
      if (!this.respond || message.id === undefined) return true;
      const result = message.method === "tools/list"
        ? { tools: [] }
        : { serverInfo: { name: "fake", version: "1" } };
      queueMicrotask(() => {
        this.stdout.emit(
          "data",
          Buffer.from(`${JSON.stringify({ jsonrpc: "2.0", id: message.id, result })}\n`),
        );
      });
      return true;
    }),
  };
  kill = vi.fn((signal = "SIGTERM") => {
    this.killedSignals.push(signal);
    if (this.exitOnSignal === signal) {
      queueMicrotask(() => {
        this.exitCode = 0;
        this.emit("exit", 0);
      });
    }
    return true;
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

function client(): MCPClient {
  return new MCPClient({
    name: "test-server",
    command: "fake-server",
    args: [],
    enabled: true,
  });
}

describe("MCP process lifecycle", () => {
  it("rejects every pending request before shutdown clears runtime state", async () => {
    vi.useFakeTimers();
    const child = new FakeMcpProcess();
    child.respond = false;
    child.exitOnSignal = "SIGTERM";
    const mcp = client();
    (mcp as any).process = child;
    (mcp as any)._ready = true;
    let rejected = false;
    const pending = (mcp as any).sendRequest("tools/list", {}).catch((error: Error) => {
      rejected = true;
      return error;
    });

    const shutdown = mcp.shutdown();
    await vi.advanceTimersByTimeAsync(10_000);
    await shutdown;

    expect(rejected).toBe(true);
    await expect(pending).resolves.toMatchObject({ message: expect.stringContaining("shutting down") });
  });

  it("forces a kill and waits for bounded completion when graceful exit hangs", async () => {
    vi.useFakeTimers();
    const child = new FakeMcpProcess();
    child.exitOnSignal = "SIGKILL";
    const mcp = client();
    (mcp as any).process = child;
    (mcp as any)._ready = true;

    const shutdown = mcp.shutdown();
    await vi.advanceTimersByTimeAsync(10_000);
    await shutdown;

    expect(child.killedSignals).toEqual(["SIGTERM", "SIGKILL"]);
    expect(mcp.ready).toBe(false);
  });

  it("settles startup once when shutdown begins before initialization", async () => {
    vi.useFakeTimers();
    const child = new FakeMcpProcess();
    child.respond = false;
    child.exitOnSignal = "SIGTERM";
    processMocks.spawn.mockReturnValue(child);
    const mcp = client();

    const starting = mcp.start().catch((error: Error) => error);
    const shutdown = mcp.shutdown();
    await vi.advanceTimersByTimeAsync(10_000);

    await expect(starting).resolves.toMatchObject({
      message: expect.stringContaining("shutting down"),
    });
    await expect(shutdown).resolves.toBeUndefined();
    expect(child.killedSignals).toEqual(["SIGTERM"]);
  });

  it("ignores a late exit from a process generation that has been replaced", async () => {
    vi.useFakeTimers();
    const oldProcess = new FakeMcpProcess();
    processMocks.spawn.mockReturnValue(oldProcess);
    const mcp = client();
    const started = mcp.start();
    await vi.advanceTimersByTimeAsync(500);
    await started;
    expect(mcp.ready).toBe(true);

    const replacement = new FakeMcpProcess();
    (mcp as any).process = replacement;
    (mcp as any)._ready = true;
    oldProcess.emit("exit", 1);

    expect((mcp as any).process).toBe(replacement);
    expect(mcp.ready).toBe(true);
  });

  it("ignores late stdout from an old process generation during restart", async () => {
    vi.useFakeTimers();
    const oldProcess = new FakeMcpProcess();
    const replacement = new FakeMcpProcess();
    processMocks.spawn
      .mockReturnValueOnce(oldProcess)
      .mockReturnValueOnce(replacement);
    const mcp = client();

    const firstStart = mcp.start();
    await vi.advanceTimersByTimeAsync(500);
    await firstStart;
    oldProcess.exitOnSignal = "SIGTERM";

    const restartOutcome = mcp.start().then(
      () => "started",
      () => "failed",
    );
    await vi.advanceTimersByTimeAsync(500);
    expect((mcp as any).process).toBe(replacement);

    oldProcess.stdout.emit("data", Buffer.from('{"jsonrpc":"2.0",'));
    await vi.advanceTimersByTimeAsync(31_000);

    await expect(restartOutcome).resolves.toBe("started");
    expect(mcp.ready).toBe(true);
  });
});
