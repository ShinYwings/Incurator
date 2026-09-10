import { EventEmitter } from "events";
import { appendFileSync, existsSync, mkdtempSync, rmSync, writeFileSync } from "fs";
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
const agyResult = (response: string) => JSON.stringify({ event: "result", result: { status: "SUCCESS", response } });

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
    children[0].stdout.emit("data", Buffer.from(agyResult("first answer")));
    children[1].stdout.emit("data", Buffer.from(agyResult("second answer")));
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
        callback(null, { stdout: agyResult("answer"), stderr: "" });
      },
    );
    const client = cliClient();

    await client.complete([{ role: "user", content: "hi" }], {
      model: "per-call-model",
      toolPolicy: "none",
    });

    expect(capturedArgs).toContain("per-call-model");
    const prompt = capturedArgs[capturedArgs.indexOf("-p") + 1];
    expect(prompt).toContain("Do not run shell commands");
    expect(prompt).toContain("ai-agent-edit");
    expect(prompt).toContain("Use only the supplied context");
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

  it("preserves an intact Codex final edit across independent items and EOF", async () => {
    const client = cliClient();
    (client as any).settings.provider = "openai";
    let outputFile = "";
    (client as any).buildCliCommand = (_prompt: string, output: string) => {
      outputFile = output;
      return { command: "codex", args: [], env: {} };
    };
    const child = new FakeCliProcess();
    processMocks.spawn.mockReturnValue(child);
    const chunks: string[] = [];
    const pending = client.streamChat([{ role: "user", content: "edit" }], chunk => chunks.push(chunk.text));
    await vi.waitFor(() => expect(processMocks.spawn).toHaveBeenCalledOnce());
    const progress = "I will inspect and edit the note. ".repeat(10);
    const edit = '```ai-agent-edit filepath="note.md"\n<<<< SEARCH\nold\n==== REPLACE\nnew\n>>>>\n```';
    child.stdout.emit("data", Buffer.from(JSON.stringify({ type: "item.completed", item: { id: "one", type: "agent_message", text: progress } }) + "\n"));
    const final = JSON.stringify({ type: "item.completed", item: { id: "two", type: "agent_message", text: edit } });
    child.stdout.emit("data", Buffer.from(final.slice(0, 25)));
    child.stdout.emit("data", Buffer.from(final.slice(25)));
    writeFileSync(outputFile, edit);
    child.emit("close", 0);
    await expect(pending).resolves.toBe(`${progress}\n\n${edit}`);
    expect(chunks.join("").split(edit)).toHaveLength(2);
  });

  it("delivers agy response before process close and preserves partial output on timeout", async () => {
    const client = cliClient();
    (client as any).buildCliCommand = () => ({ command: "agy", args: [], env: {} });
    const child = new FakeCliProcess();
    processMocks.spawn.mockReturnValue(child);
    const chunks: string[] = [];
    const pending = client.streamChat([{ role: "user", content: "explain" }], chunk => chunks.push(chunk.text));
    const rejected = expect(pending).rejects.toThrow("timed out");
    await vi.waitFor(() => expect(processMocks.spawn).toHaveBeenCalledOnce());
    const line = JSON.stringify({ event: "step_update", step_update: { step_index: 1, step_type: "agent_response", text_delta: "The equation is" } });
    child.stdout.emit("data", Buffer.from(line + "\n"));
    expect(chunks.join("")).toContain("The equation is");
    child.stderr.emit("data", Buffer.from("[agy] print timeout after 5m0s with turn in progress; returning partial output"));
    child.emit("close", 0);
    await rejected;
    expect(chunks.join("")).not.toContain('"step_update"');
  });

  it("rejects timed-out non-streaming agy output instead of accepting a partial edit", async () => {
    processMocks.execFile.mockImplementation((_command: string, _args: string[], _options: unknown, callback: Function) => {
      callback(null, { stdout: agyResult("unfinished replacement"), stderr: "[agy] print timeout after 5m0s; returning partial output" });
    });
    await expect(cliClient().complete([{ role: "user", content: "edit" }])).rejects.toThrow("timed out");
  });

  it("rejects an abnormal native CLI exit even after visible answer text", async () => {
    const client = cliClient();
    const child = new FakeCliProcess();
    processMocks.spawn.mockReturnValue(child);
    const pending = client.streamChat([{ role: "user", content: "explain" }], vi.fn());
    const rejected = expect(pending).rejects.toThrow("CLI failed");
    await vi.waitFor(() => expect(processMocks.spawn).toHaveBeenCalledOnce());
    child.stdout.emit("data", Buffer.from(JSON.stringify({ event: "step_update", step_update: { step_index: 1, step_type: "agent_response", text_delta: "An unfinished answer" } }) + "\n"));
    child.emit("close", 1);
    await rejected;
  });

  it("stops an exhausted streaming invocation from its own runtime log", async () => {
    const client = cliClient();
    const child = new FakeCliProcess();
    processMocks.spawn.mockReturnValue(child);
    const pending = client.streamChat([{ role: "user", content: "explain" }], vi.fn());
    const rejected = expect(pending).rejects.toThrow("Individual quota reached");
    await vi.waitFor(() => expect(processMocks.spawn).toHaveBeenCalledOnce());
    const args: string[] = processMocks.spawn.mock.calls[0][1];
    const log = args[args.indexOf("--log-file") + 1];
    expect(existsSync(log)).toBe(true);
    appendFileSync(log, "I0910 13:37:18.256298     327 run.go:387] Run: attempt 1 failed (RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 144h.), retrying in 4s\n");
    await rejected;
    expect(child.kill).toHaveBeenCalledOnce();
    child.emit("close", null);
    expect(existsSync(log)).toBe(false);
  });

  it("preserves native successful answers despite quota text in stderr or prose", async () => {
    const client = cliClient();
    const child = new FakeCliProcess();
    processMocks.spawn.mockReturnValue(child);
    const pending = client.streamChat([{ role: "user", content: "explain the error" }], vi.fn());
    const answer = 'The error says "Individual quota reached"; this does not measure account usage.';
    // Attach rejection handling before emitting events to avoid an unhandled
    // rejection in the broken implementation this regression characterizes.
    const observed = pending.then(value => ({ value }), error => ({ error }));
    await vi.waitFor(() => expect(processMocks.spawn).toHaveBeenCalledOnce());
    child.stderr.emit("data", Buffer.from('Diagnostic example: HTTP 429 Individual quota reached\n'));
    child.stdout.emit("data", Buffer.from(agyResult(answer)));
    child.emit("close", 0);
    expect(await observed).toEqual({ value: answer });
    expect(child.kill).not.toHaveBeenCalled();
  });

  it("aborts an exhausted completion promptly and disposes its log", async () => {
    let log = "";
    processMocks.execFile.mockImplementation((_cmd: string, args: string[], options: { signal: AbortSignal }, callback: Function) => {
      log = args[args.indexOf("--log-file") + 1];
      options.signal.addEventListener("abort", () => callback(new DOMException("aborted", "AbortError")));
      appendFileSync(log, "I0910 13:37:18.256298     327 run.go:387] Run: attempt 1 failed (RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 144h.), retrying in 4s\n");
    });
    await expect(cliClient().complete([{ role: "user", content: "explain" }])).rejects.toThrow("Individual quota reached");
    expect(existsSync(log)).toBe(false);
  });
});
