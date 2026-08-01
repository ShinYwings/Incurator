import { EventEmitter } from "events";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { afterEach, describe, expect, it, vi } from "vitest";

const processMocks = vi.hoisted(() => ({
  execFile: vi.fn(),
  spawn: vi.fn(),
}));

vi.mock("child_process", () => ({
  execFile: processMocks.execFile,
  spawn: processMocks.spawn,
}));

vi.mock("obsidian", () => ({
  Notice: class Notice {
    constructor(_message: string) {}
  },
  requestUrl: async () => ({ json: {} }),
}));

import { LLMClient } from "./llm/LLMClient";
import { DEFAULT_SETTINGS } from "../types";

class FakeCliProcess extends EventEmitter {
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  stdin = { end: vi.fn() };
  kill = vi.fn(() => true);
}

const testRoots: string[] = [];

afterEach(() => {
  vi.clearAllMocks();
  for (const root of testRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function cliClient(): LLMClient {
  const root = mkdtempSync(join(tmpdir(), "incurator-cli-lifecycle-"));
  testRoots.push(root);
  const client = new LLMClient(
    {
      ...DEFAULT_SETTINGS,
      provider: "antigravity",
      model: "configured-model",
      incuratorRepoPath: root,
    },
    {} as never,
  );
  (client as any).getCliCwd = () => root;
  (client as any).cliTempDir = () => join(root, "tmp");
  (client as any).syncAgyMcpConfig = () => undefined;
  (client as any).wrapWithOsSandbox = (command: unknown) => command;
  return client;
}

describe("CLI request ownership", () => {
  it("does not spawn a streaming CLI for an already-aborted request", async () => {
    const client = cliClient();
    (client as any).buildCliCommand = () => ({ command: "agy", args: [], env: {} });
    const owner = new AbortController();
    owner.abort();

    await expect(client.streamChat(
      [{ role: "user", content: "cancelled" }],
      vi.fn(),
      { signal: owner.signal },
    )).resolves.toBe("");
    expect(processMocks.spawn).not.toHaveBeenCalled();
  });

  it("binds each overlapping CLI child to its caller-owned signal", async () => {
    const children = [new FakeCliProcess(), new FakeCliProcess()];
    processMocks.spawn
      .mockReturnValueOnce(children[0])
      .mockReturnValueOnce(children[1]);
    const client = cliClient();
    (client as any).buildCliCommand = () => ({ command: "agy", args: [], env: {} });
    const firstOwner = new AbortController();
    const secondOwner = new AbortController();

    const first = client.streamChat([{ role: "user", content: "first" }], vi.fn(), {
      signal: firstOwner.signal,
    });
    const second = client.streamChat([{ role: "user", content: "second" }], vi.fn(), {
      signal: secondOwner.signal,
    });
    await vi.waitFor(() => expect(processMocks.spawn).toHaveBeenCalledTimes(2));

    firstOwner.abort();
    children[0].stdout.emit("data", Buffer.from("first answer"));
    children[1].stdout.emit("data", Buffer.from("second answer"));
    children[0].emit("close", 0);
    children[1].emit("close", 0);
    await Promise.all([first, second]);

    expect(children[0].kill).toHaveBeenCalledOnce();
    expect(children[1].kill).not.toHaveBeenCalled();
  });

  it("passes the per-call model and augmented GUI environment to non-streaming CLI", async () => {
    let capturedArgs: string[] = [];
    let capturedEnv: NodeJS.ProcessEnv | undefined;
    processMocks.execFile.mockImplementation(
      (_command: string, args: string[], options: { env?: NodeJS.ProcessEnv }, callback: Function) => {
        capturedArgs = args;
        capturedEnv = options.env;
        callback(null, { stdout: "answer", stderr: "" });
      },
    );
    const client = cliClient();

    await client.complete([{ role: "user", content: "hi" }], {
      model: "per-call-model",
      toolPolicy: "none",
    });

    expect(capturedArgs).toContain("per-call-model");
    expect(capturedEnv?.PATH).not.toBe(process.env.PATH);
    expect(capturedEnv?.PATH).toContain(process.env.PATH || "");
    expect(capturedEnv?.TMPDIR).toMatch(/incurator-cli-lifecycle-.*\/tmp$/);
  });

  it("does not execute a non-streaming CLI for an already-aborted request", async () => {
    const client = cliClient();
    const owner = new AbortController();
    owner.abort();

    await expect(client.complete(
      [{ role: "user", content: "cancelled" }],
      { signal: owner.signal },
    )).rejects.toMatchObject({ name: "AbortError" });
    expect(processMocks.execFile).not.toHaveBeenCalled();
  });
});
