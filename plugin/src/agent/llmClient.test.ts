import { afterEach, describe, expect, it } from "vitest";
import { vi } from "vitest";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { fileURLToPath } from "url";
import {
  formatMcpToolResultForDisplay,
  formatQuotaErrorMessage,
  extractAntigravityAnswerFromStderr,
  isAntigravityStatusLine,
  isQuotaErrorMessage,
  sanitizeOpenAIMessages,
  normalizeOpenAIContent,
  isEphemeralToolPolicy,
  shouldInjectMcpTools,
  shouldInjectLocalTools,
  mapOpenAIFinishReason,
} from "./llm/messageUtils";
import { POPOVER_PROFILE, type ToolPolicy } from "../context/promptRegistry";
import {
  ADAPTERS,
  buildMcpToolExposure,
  LLMClient,
  syncAgyHeadlessReadPermission,
} from "./llm/LLMClient";
import { DEFAULT_SETTINGS } from "../types";
import type { LLMMessage, PluginSettings } from "../types";

const obsidianMocks = vi.hoisted(() => ({
  requestUrl: vi.fn(async () => ({ json: {} })),
}));

vi.mock("obsidian", () => ({
  Notice: class Notice {
    constructor(_message: string) {}
  },
  requestUrl: obsidianMocks.requestUrl,
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("LLM request lifecycle hardening", () => {
  const messages: LLMMessage[] = [{ role: "user", content: "hi" }];

  function httpClient(auth: { resolveCredential: () => Promise<{ type: "bearer"; token: string }> }): LLMClient {
    const client = new LLMClient(
      { ...DEFAULT_SETTINGS, provider: "openai", model: "test-model" },
      auth as never,
    );
    (client as any).shouldUseCli = () => false;
    return client;
  }

  function emptyStreamingResponse(): Response {
    return {
      ok: true,
      body: {
        getReader: () => ({ read: async () => ({ done: true, value: undefined }) }),
      },
    } as unknown as Response;
  }

  it("runs the active-bundle guard before authentication or provider startup", async () => {
    const resolveCredential = vi.fn();
    const client = new LLMClient(
      { ...DEFAULT_SETTINGS, provider: "openai", model: "test-model" },
      { resolveCredential } as never,
      "",
      undefined,
      undefined,
      () => {
        throw new Error("reload required");
      }
    );
    (client as any).shouldUseCli = () => false;

    await expect(client.streamChat(messages, vi.fn())).rejects.toThrow(
      "reload required"
    );
    expect(resolveCredential).not.toHaveBeenCalled();
  });

  it("does not launch a provider after cancellation during the async launch guard", async () => {
    let releaseGuard!: () => void;
    const guard = new Promise<void>((resolve) => {
      releaseGuard = resolve;
    });
    const client = new LLMClient(
      { ...DEFAULT_SETTINGS, provider: "openai", model: "test-model" },
      { resolveCredential: vi.fn(async () => ({ type: "bearer", token: "token" })) } as never,
      "",
      undefined,
      undefined,
      () => guard,
    );
    (client as any).shouldUseCli = () => false;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const owner = new AbortController();

    const request = client.streamChat(messages, vi.fn(), { signal: owner.signal });
    owner.abort();
    releaseGuard();

    await expect(request).resolves.toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the current request controller usable if abort runs during async authentication", async () => {
    let resolveCredential!: (value: { type: "bearer"; token: string }) => void;
    const credential = new Promise<{ type: "bearer"; token: string }>((resolve) => {
      resolveCredential = resolve;
    });
    const client = httpClient({ resolveCredential: () => credential });
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect((init.signal as AbortSignal).aborted).toBe(true);
      throw new DOMException("aborted", "AbortError");
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = (client as any)._streamChatSingleTurn(messages, vi.fn());
    client.abort();
    resolveCredential({ type: "bearer", token: "token" });

    await expect(request).resolves.toMatchObject({ text: "" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("does not let an older request clear a newer request controller", async () => {
    const client = httpClient({
      resolveCredential: async () => ({ type: "bearer", token: "token" }),
    });
    const pending: Array<(response: Response) => void> = [];
    const signals: AbortSignal[] = [];
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      signals.push(init.signal as AbortSignal);
      return new Promise<Response>((resolve) => pending.push(resolve));
    }));

    const first = (client as any)._streamChatSingleTurn(messages, vi.fn());
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    const second = (client as any)._streamChatSingleTurn(messages, vi.fn());
    await vi.waitFor(() => expect(pending).toHaveLength(2));

    pending[0](emptyStreamingResponse());
    await first;
    client.abort();

    expect(signals[1].aborted).toBe(true);
    pending[1](emptyStreamingResponse());
    await second;
  });

  it("keeps caller-owned overlapping requests independently cancelable", async () => {
    const client = httpClient({
      resolveCredential: async () => ({ type: "bearer", token: "token" }),
    });
    const pending: Array<(response: Response) => void> = [];
    const signals: AbortSignal[] = [];
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      signals.push(init.signal as AbortSignal);
      return new Promise<Response>((resolve) => pending.push(resolve));
    }));
    const firstOwner = new AbortController();
    const secondOwner = new AbortController();

    const first = client.streamChat(messages, vi.fn(), { signal: firstOwner.signal });
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    const second = client.streamChat(messages, vi.fn(), { signal: secondOwner.signal });
    await vi.waitFor(() => expect(pending).toHaveLength(2));

    firstOwner.abort();
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);

    pending[0](emptyStreamingResponse());
    pending[1](emptyStreamingResponse());
    await Promise.all([first, second]);
  });

  it("keeps caller-owned work out of the sidebar foreground abort target", async () => {
    const client = httpClient({
      resolveCredential: async () => ({ type: "bearer", token: "token" }),
    });
    const pending: Array<(response: Response) => void> = [];
    const signals: AbortSignal[] = [];
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      signals.push(init.signal as AbortSignal);
      return new Promise<Response>((resolve) => pending.push(resolve));
    }));
    const quickQueryOwner = new AbortController();

    const sidebar = client.streamChat(messages, vi.fn());
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    const quickQuery = client.streamChat(messages, vi.fn(), {
      signal: quickQueryOwner.signal,
    });
    await vi.waitFor(() => expect(pending).toHaveLength(2));

    client.abort();

    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
    pending[0](emptyStreamingResponse());
    await sidebar;

    client.abort();
    expect(signals[1].aborted).toBe(false);
    pending[1](emptyStreamingResponse());
    await quickQuery;
  });

  it("does not construct requestUrl for an already-aborted completion", async () => {
    const client = new LLMClient(
      {
        ...DEFAULT_SETTINGS,
        provider: "deepseek",
        model: "test-model",
        deepseekApiKey: "test-key",
      },
      {} as never,
    );
    const owner = new AbortController();
    owner.abort();

    await expect(client.complete(messages, { signal: owner.signal })).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(obsidianMocks.requestUrl).not.toHaveBeenCalled();
  });

  it("preserves streaming Ollama cancellation instead of reporting it offline", async () => {
    const client = new LLMClient(
      { ...DEFAULT_SETTINGS, provider: "ollama", model: "test-model" },
      {} as never,
    );
    const owner = new AbortController();
    const fetchMock = vi.fn((_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        }, { once: true });
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = client.streamChat(messages, vi.fn(), { signal: owner.signal });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    owner.abort();

    await expect(request).resolves.toBe("");
  });

  it("preserves non-streaming Ollama AbortError", async () => {
    const client = new LLMClient(
      { ...DEFAULT_SETTINGS, provider: "ollama", model: "test-model" },
      {} as never,
    );
    const owner = new AbortController();
    const fetchMock = vi.fn((_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        }, { once: true });
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = client.complete(messages, { signal: owner.signal });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    owner.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });

  it("restores an older active request as foreground after the newer request finishes", async () => {
    const client = httpClient({
      resolveCredential: async () => ({ type: "bearer", token: "token" }),
    });
    const pending: Array<(response: Response) => void> = [];
    const signals: AbortSignal[] = [];
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      signals.push(init.signal as AbortSignal);
      return new Promise<Response>((resolve) => pending.push(resolve));
    }));

    const first = client.streamChat(messages, vi.fn());
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    const second = client.streamChat(messages, vi.fn());
    await vi.waitFor(() => expect(pending).toHaveLength(2));

    pending[1](emptyStreamingResponse());
    await second;
    client.abort();

    expect(signals[0].aborted).toBe(true);
    pending[0](emptyStreamingResponse());
    await first;
  });

  it("accepts MCP server definitions without an args array", () => {
    const client = httpClient({
      resolveCredential: async () => ({ type: "bearer", token: "token" }),
    });

    expect((client as any).processMcpServer({ command: "server", env: {} })).toEqual({
      command: "server",
      args: [],
      env: {},
    });
  });
});

describe("MCP model-facing tool exposure", () => {
  it("keeps sanitized collisions unique and dispatches through original names", async () => {
    const rawTools = [
      {
        serverName: "alpha.beta",
        name: "read__item",
        description: "first",
        inputSchema: { type: "object" },
      },
      {
        serverName: "alpha_beta",
        name: "read__item",
        description: "second",
        inputSchema: { type: "object" },
      },
    ];
    const exposure = buildMcpToolExposure(rawTools);
    const names = exposure.tools.map((tool) => tool.function.name);

    expect(new Set(names).size).toBe(2);
    expect(exposure.routes.get(names[0])).toEqual({
      serverName: "alpha.beta",
      toolName: "read__item",
    });

    const callTool = vi.fn(async () => ({ content: [{ type: "text", text: "ok" }] }));
    const client = new LLMClient(
      { ...DEFAULT_SETTINGS, provider: "ollama", model: "test-model" },
      {} as never,
      "",
      undefined,
      {
        getAllTools: () => rawTools,
        callTool,
      } as never,
    );
    let turn = 0;
    (client as any).shouldUseCli = () => false;
    (client as any)._streamChatSingleTurn = vi.fn(async () => {
      turn += 1;
      return turn === 1
        ? {
            text: "",
            tool_calls: [{
              id: "call-1",
              function: { name: names[0], arguments: "{}" },
            }],
          }
        : { text: "done" };
    });

    await client.streamChat([{ role: "user", content: "use tool" }], vi.fn());

    expect(callTool).toHaveBeenCalledWith("alpha.beta", "read__item", {});
  });
});

describe("Antigravity headless read permission sync", () => {
  const generatedPolicyHeader = "# Auto-generated by Incurator plugin — do not edit manually.";
  let testRoot = "";

  afterEach(() => {
    if (testRoot) rmSync(testRoot, { recursive: true, force: true });
    testRoot = "";
  });

  function freshGeminiDir(): string {
    testRoot = mkdtempSync(join(tmpdir(), "incurator-agy-settings-"));
    return join(testRoot, ".gemini");
  }

  it("creates the live Antigravity CLI settings with the narrow read + scoped command rules", () => {
    const geminiDir = freshGeminiDir();

    syncAgyHeadlessReadPermission(geminiDir);

    const settingsPath = join(geminiDir, "antigravity-cli", "settings.json");
    expect(JSON.parse(readFileSync(settingsPath, "utf-8"))).toEqual({
      permissions: { allow: ["read_file(*)", "command(wiki)"] },
    });
  });

  it("never writes a rule Antigravity would prune", () => {
    // THE REGRESSION THIS FILE MISSED FOR ~20 RELEASES. Antigravity validates
    // permissions.allow, silently drops entries it does not recognise, and then
    // removes an emptied `permissions` object entirely. The shipped rule was
    // `$read_file$()`, which is not a recognised form, so the grant survived
    // exactly zero CLI invocations and every tool call was auto-denied
    // ("jetski: no output produced"). The old assertions here passed the whole
    // time because they only proved we WROTE a string, never that it was valid.
    //
    // Measured against the real CLI:
    //   $read_file$()        -> permissions key deleted
    //   read_file()          -> survives
    //   command(wiki)        -> survives
    //   $command$()          -> pruned
    //   run_shell_command()  -> pruned
    //
    // v0.56.1: surviving is NOT granting, and this test could not tell the
    // difference — it asserted the rule persisted, which `read_file()` does
    // while authorizing nothing. Re-measured against agy 1.1.13 by writing each
    // rule and then asking the model to read a real PNG:
    //   read_file(*)                 -> the model read the file
    //   read_file(/tmp/exact.png)    -> auto-denied (an EXACT path is refused)
    //   read_file(/tmp/*)            -> auto-denied
    //   read_file()                  -> auto-denied
    // Only the wildcard is honoured for reads. `command(wiki)` DOES work
    // scoped, so the narrow command grant stays.
    const geminiDir = freshGeminiDir();
    syncAgyHeadlessReadPermission(geminiDir);

    const written = JSON.parse(
      readFileSync(join(geminiDir, "antigravity-cli", "settings.json"), "utf-8"),
    ) as { permissions: { allow: string[] } };

    for (const rule of written.permissions.allow) {
      expect(rule, `"${rule}" uses the $-wrapped form Antigravity prunes`)
        .not.toMatch(/^\$.*\$\(/);
      expect(rule).toMatch(/^[a-z_]+\([^)]*\)$/);
    }
  });

  it("scopes the command rule instead of granting a blanket bypass", () => {
    // v0.23.0 posture: NO blanket permission-skip. `command()` would allow the
    // model to run anything; `command(wiki)` allows only spawning the MCP
    // server the plugin itself configured.
    const geminiDir = freshGeminiDir();
    syncAgyHeadlessReadPermission(geminiDir);

    const { permissions } = JSON.parse(
      readFileSync(join(geminiDir, "antigravity-cli", "settings.json"), "utf-8"),
    ) as { permissions: { allow: string[] } };

    expect(permissions.allow).toContain("command(wiki)");
    expect(permissions.allow).not.toContain("command()");
  });

  it("preserves unknown settings and permission rules while deduplicating its own", () => {
    const geminiDir = freshGeminiDir();
    const cliDir = join(geminiDir, "antigravity-cli");
    mkdirSync(cliDir, { recursive: true });
    writeFileSync(join(cliDir, "settings.json"), JSON.stringify({
      model: "Gemini 3.6 Flash",
      custom: { future: true },
      permissions: {
        allow: ["command(git status)", "read_file()", "command(wiki)"],
        ask: ["write_file()"],
      },
    }));

    syncAgyHeadlessReadPermission(geminiDir);

    expect(JSON.parse(readFileSync(join(cliDir, "settings.json"), "utf-8"))).toEqual({
      model: "Gemini 3.6 Flash",
      custom: { future: true },
      permissions: {
        // `command(git status)` is the user's rule and survives untouched.
        // `read_file()` is OUR retired rule and is replaced, not kept beside
        // its successor — a dead grant next to a live one reads as configured
        // read access when it is not.
        allow: ["command(git status)", "command(wiki)", "read_file(*)"],
        ask: ["write_file()"],
      },
    });
  });

  it.each([
    ["malformed JSON", "{broken"],
    ["non-array permissions.allow", JSON.stringify({ permissions: { allow: "all" } })],
  ])("refuses to overwrite %s", (_label, original) => {
    const geminiDir = freshGeminiDir();
    const cliDir = join(geminiDir, "antigravity-cli");
    const settingsPath = join(cliDir, "settings.json");
    mkdirSync(cliDir, { recursive: true });
    writeFileSync(settingsPath, original);

    expect(() => syncAgyHeadlessReadPermission(geminiDir)).toThrow(/Antigravity CLI settings/);
    expect(readFileSync(settingsPath, "utf-8")).toBe(original);
  });

  it("removes only the obsolete policy generated by Incurator", () => {
    const geminiDir = freshGeminiDir();
    const policyDir = join(geminiDir, "policies");
    const policyPath = join(policyDir, "incurator-read.toml");
    mkdirSync(policyDir, { recursive: true });
    writeFileSync(policyPath, `${generatedPolicyHeader}\n[[rule]]\ntoolName = "read_file"\n`);

    syncAgyHeadlessReadPermission(geminiDir);

    expect(existsSync(policyPath)).toBe(false);
  });

  it("preserves a same-named user policy", () => {
    const geminiDir = freshGeminiDir();
    const policyDir = join(geminiDir, "policies");
    const policyPath = join(policyDir, "incurator-read.toml");
    mkdirSync(policyDir, { recursive: true });
    writeFileSync(policyPath, "# user policy\n[[rule]]\ntoolName = \"read_file\"\n");

    syncAgyHeadlessReadPermission(geminiDir);

    expect(readFileSync(policyPath, "utf-8")).toContain("# user policy");
  });

  it("leaves no temporary settings file after replacement", () => {
    const geminiDir = freshGeminiDir();

    syncAgyHeadlessReadPermission(geminiDir);

    const cliDir = join(geminiDir, "antigravity-cli");
    expect(readdirSync(cliDir).filter((name) => name.includes(".incurator-")).length).toBe(0);
  });
});

describe("LLM quota errors", () => {
  it("recognizes quota and capacity failures from CLI/API providers", () => {
    expect(isQuotaErrorMessage("RESOURCE_EXHAUSTED: quota exceeded")).toBe(true);
    expect(isQuotaErrorMessage("429 rate limit reached")).toBe(true);
    expect(isQuotaErrorMessage("No capacity available")).toBe(true);
    expect(isQuotaErrorMessage("plain auth error")).toBe(false);
  });

  it("formats a user-visible sidechat message", () => {
    const text = formatQuotaErrorMessage("antigravity", "Individual quota reached");
    expect(text).toContain("quota or capacity");
    expect(text).toContain("Switch provider/model");
  });
});

describe("MCP tool result display", () => {
  it("keeps curator_query trace parseable while dropping oversized answers", () => {
    const raw = JSON.stringify({
      ok: true,
      question: "What is result 19.4?",
      answer: "A".repeat(4000),
      route: "global",
      trace_id: "QTR-1234abcd",
      trace: {
        matched_concepts: ["CON-1234abcd"],
        source_ids: [],
        source_paths: ["03_Concepts/CON-1234abcd.md"],
        latency_ms: 42,
        l3_complete: true,
      },
    });

    const display = formatMcpToolResultForDisplay("mcp_incurator_curator_query", raw);
    const parsed = JSON.parse(display);

    expect(parsed.trace_id).toBe("QTR-1234abcd");
    expect(parsed.trace.matched_concepts).toEqual(["CON-1234abcd"]);
    expect(parsed.answer).toBeUndefined();
    expect(display).not.toContain("AAAA");
  });

  it("keeps curator_query failure diagnostics and top-level trace lists", () => {
    const raw = JSON.stringify({
      ok: false,
      question: "Why did synthesis fail?",
      route: "local",
      trace_id: "QTR-failed01",
      error: "Antigravity CLI returned no output.",
      prompt_trace_ids: ["PTR-failed01"],
      warnings: ["retrieval evidence retained"],
      trace: {
        trace_id: "QTR-failed01",
        prompt_trace_ids: ["PTR-failed01"],
        source_span_ids: ["SPAN-failed01"],
        latency_ms: 12,
        l3_complete: true,
      },
    });

    const display = formatMcpToolResultForDisplay(
      "mcp_incurator_curator_query",
      raw
    );
    const parsed = JSON.parse(display);

    expect(parsed.error).toBe("Antigravity CLI returned no output.");
    expect(parsed.prompt_trace_ids).toEqual(["PTR-failed01"]);
    expect(parsed.warnings).toEqual(["retrieval evidence retained"]);
    expect(parsed.trace.prompt_trace_ids).toEqual(["PTR-failed01"]);
  });

  it("still truncates non-curator tool results", () => {
    const display = formatMcpToolResultForDisplay("mcp_other_tool", "A".repeat(1000));

    expect(display.length).toBeLessThan(650);
    expect(display.endsWith("…")).toBe(true);
  });
});

describe("shouldInjectMcpTools (popover tool isolation, v0.19.0)", () => {
  it("never injects tools when the surface declares toolPolicy 'none'", () => {
    // Even with an MCP manager present and an OpenAI-compat provider (not CLI),
    // an ephemeral surface (popover) gets ZERO tools.
    expect(shouldInjectMcpTools("none", true, false)).toBe(false);
    expect(shouldInjectMcpTools("none", true, true)).toBe(false);
    expect(shouldInjectMcpTools("none", false, false)).toBe(false);
  });

  it("injects tools for the auto sidechat path only when an MCP manager exists and not on CLI", () => {
    expect(shouldInjectMcpTools("auto", true, false)).toBe(true);
    // No MCP manager → no tools.
    expect(shouldInjectMcpTools("auto", false, false)).toBe(false);
    // CLI providers route tools through the CLI, not the request body.
    expect(shouldInjectMcpTools("auto", true, true)).toBe(false);
  });

  it("never injects MCP tools for the popover's local-only policy (v0.41.0)", () => {
    // Behavioral guarantee, not a prompt-string one: the popover keeps zero MCP
    // tools under EVERY combination of manager presence and CLI routing.
    for (const hasManager of [true, false]) {
      for (const useCli of [true, false]) {
        expect(shouldInjectMcpTools("local-only", hasManager, useCli)).toBe(false);
      }
    }
  });

  it("maps the popover profile policy to a refused MCP injection", () => {
    for (const hasManager of [true, false]) {
      for (const useCli of [true, false]) {
        expect(shouldInjectMcpTools(POPOVER_PROFILE.toolPolicy, hasManager, useCli)).toBe(false);
      }
    }
  });
});

describe("shouldInjectLocalTools (v0.41.0 local PDF reader)", () => {
  it("injects local tools for the popover when a runner exists", () => {
    expect(shouldInjectLocalTools("local-only", true, false)).toBe(true);
  });

  it("injects local tools for the sidechat auto path too", () => {
    expect(shouldInjectLocalTools("auto", true, false)).toBe(true);
  });

  it("never injects local tools for a fully tool-free surface", () => {
    expect(shouldInjectLocalTools("none", true, false)).toBe(false);
  });

  it("never injects local tools on CLI providers (locked decision)", () => {
    expect(shouldInjectLocalTools("local-only", true, true)).toBe(false);
    expect(shouldInjectLocalTools("auto", true, true)).toBe(false);
  });

  it("injects nothing without a runner", () => {
    expect(shouldInjectLocalTools("local-only", false, false)).toBe(false);
    expect(shouldInjectLocalTools("auto", false, false)).toBe(false);
  });

  it("resolves an explicit decision for every ToolPolicy value", () => {
    const policies: ToolPolicy[] = ["auto", "none", "local-only"];
    for (const policy of policies) {
      expect(typeof shouldInjectMcpTools(policy, true, false)).toBe("boolean");
      expect(typeof shouldInjectLocalTools(policy, true, false)).toBe("boolean");
      expect(typeof isEphemeralToolPolicy(policy)).toBe("boolean");
    }
  });
});

describe("isEphemeralToolPolicy (CLI sandbox gate, v0.23.0 + v0.41.0)", () => {
  it("treats local-only as ephemeral so the CLI sandbox is never relaxed", () => {
    // The local PDF reader is plugin-executed and hands the CLI agent no native
    // tools and no filesystem roots. Were "local-only" treated as non-ephemeral,
    // buildCliCommand would attach --add-dir vault/Zotero roots, swap Claude's
    // `--tools ""` for a disallowed-tools list, and give Codex workspace-write.
    expect(isEphemeralToolPolicy("local-only")).toBe(true);
    expect(isEphemeralToolPolicy("none")).toBe(true);
    expect(isEphemeralToolPolicy("auto")).toBe(false);
  });

  it("keeps the popover profile ephemeral", () => {
    expect(isEphemeralToolPolicy(POPOVER_PROFILE.toolPolicy)).toBe(true);
  });

  it("is the only thing buildCliCommand uses to decide ephemerality", () => {
    // Regression guard for the fail-open this PR's review found: a raw
    // `toolPolicy === "none"` comparison silently mishandles any third value.
    const clientSource = readFileSync(
      join(fileURLToPath(new URL(".", import.meta.url)), "llm/LLMClient.ts"),
      "utf8"
    );
    expect(clientSource).toContain("const ephemeral = isEphemeralToolPolicy(toolPolicy)");
    expect(clientSource).not.toContain('toolPolicy === "none"');
  });
});

describe("sanitizeOpenAIMessages", () => {
  it("drops assistant turns with neither content nor tool_calls", () => {
    const messages: LLMMessage[] = [
      { role: "system", content: "sys" },
      { role: "user", content: "hi" },
      { role: "assistant", content: "" }, // degenerate turn → 400 culprit
      { role: "user", content: "again" },
    ];
    const out = sanitizeOpenAIMessages(messages);
    expect(out).toHaveLength(3);
    expect(out.some((m) => m.role === "assistant")).toBe(false);
  });

  it("keeps assistant tool-call turns even with empty content", () => {
    const messages: LLMMessage[] = [
      { role: "user", content: "do it" },
      {
        role: "assistant",
        content: "",
        tool_calls: [
          { id: "c1", type: "function", function: { name: "f", arguments: "{}" } },
        ],
      },
      { role: "tool", tool_call_id: "c1", content: "result" },
    ];
    const out = sanitizeOpenAIMessages(messages);
    expect(out).toHaveLength(3);
  });

  it("keeps normal assistant turns and non-assistant roles untouched", () => {
    const messages: LLMMessage[] = [
      { role: "user", content: "q" },
      { role: "assistant", content: "real answer" },
    ];
    expect(sanitizeOpenAIMessages(messages)).toEqual(messages);
  });

  it("treats whitespace-only assistant content as empty", () => {
    const messages: LLMMessage[] = [
      { role: "assistant", content: "   \n  " },
    ];
    expect(sanitizeOpenAIMessages(messages)).toHaveLength(0);
  });
});

describe("normalizeOpenAIContent", () => {
  const identity = (c: any) => c;

  it("emits empty string (not null) for an assistant tool-call turn", () => {
    const msg: LLMMessage = {
      role: "assistant",
      content: "",
      tool_calls: [
        { id: "c1", type: "function", function: { name: "f", arguments: "{}" } },
      ],
    };
    expect(normalizeOpenAIContent(msg, identity)).toBe("");
  });

  it("emits empty string for an empty tool result turn", () => {
    const msg: LLMMessage = { role: "tool", tool_call_id: "c1", content: "" };
    expect(normalizeOpenAIContent(msg, identity)).toBe("");
  });

  it("passes real content through the mapper", () => {
    const msg: LLMMessage = { role: "assistant", content: "hello" };
    expect(normalizeOpenAIContent(msg, identity)).toBe("hello");
  });

  it("keeps null for empty user/system turns", () => {
    expect(normalizeOpenAIContent({ role: "user", content: "" }, identity)).toBe(
      null
    );
  });
});

describe("Antigravity CLI stderr recovery", () => {
  it("classifies agy progress lines as status, not answer text", () => {
    expect(isAntigravityStatusLine("Thinking...")).toBe(true);
    expect(isAntigravityStatusLine("- MCP servers available: incurator")).toBe(true);
    expect(isAntigravityStatusLine("The dual absolute quadric is a 4x4 symmetric matrix.")).toBe(false);
  });

  it("recovers answer-like stderr text while dropping progress lines", () => {
    const stderr = [
      "Thinking...",
      "Generating response",
      "The answer is 42.",
      "It follows from the selected passage.",
    ].join("\n");

    expect(extractAntigravityAnswerFromStderr(stderr)).toBe(
      "The answer is 42.\nIt follows from the selected passage."
    );
  });

  it("does not convert pure progress stderr into an answer", () => {
    expect(
      extractAntigravityAnswerFromStderr("Thinking...\nProcessing request\n")
    ).toBe("");
  });
});

describe("complete() per-call model override (v0.21.0 Convert-to-LaTeX fast model)", () => {
  function ollamaClient(model: string): LLMClient {
    const settings: PluginSettings = {
      ...DEFAULT_SETTINGS,
      provider: "ollama",
      model,
      ollamaHost: "http://localhost:11434",
    };
    // The Ollama non-streaming path uses global fetch and never touches `auth`.
    return new LLMClient(settings, {} as never);
  }

  function mockOllamaFetch(): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ choices: [{ message: { content: "x" } }] }),
    }));
    globalThis.fetch = fetchMock as never;
    return fetchMock;
  }

  const messages: LLMMessage[] = [{ role: "user", content: "hi" }];

  it("sends the override model when opts.model is provided", async () => {
    const fetchMock = mockOllamaFetch();
    await ollamaClient("main-model").complete(messages, { model: "qwen2.5:0.5b" });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body);
    expect(body.model).toBe("qwen2.5:0.5b");
  });

  it("falls back to the main model when no opts are given (backward compatible)", async () => {
    const fetchMock = mockOllamaFetch();
    await ollamaClient("main-model").complete(messages);
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body);
    expect(body.model).toBe("main-model");
  });

  it("falls back to the main model when the override is blank/whitespace", async () => {
    const fetchMock = mockOllamaFetch();
    await ollamaClient("main-model").complete(messages, { model: "   " });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body);
    expect(body.model).toBe("main-model");
  });
});

describe("CLI tool-scope sandbox source contract (v0.23.0)", () => {
  const source = readFileSync(
    join(fileURLToPath(new URL(".", import.meta.url)), "llm", "LLMClient.ts"),
    "utf8",
  );

  it("drops the dangerous agy blanket-skip + trust-workspace bypass", () => {
    expect(source).not.toContain("--dangerously-skip-permissions");
    expect(source).not.toContain('GEMINI_CLI_TRUST_WORKSPACE: "true"');
    expect(source).not.toContain('ANTIGRAVITY_TRUST_WORKSPACE: "true"');
  });

  it("keeps agy --sandbox so -p mode never hangs on a permission prompt", () => {
    // agy --sandbox auto-proceeds (no prompt → no hang); the OS sandbox does the
    // actual containment. Dropping both would reintroduce the original hang.
    expect(source).toContain('"--sandbox",');
    // bwrap availability is an in-process PATH lookup, NOT a synchronous sh spawn.
    expect(source).not.toContain('execFileSync("sh"');
    expect(source).toContain('existsSync(candidate)');
  });

  it("controls claude via the tool surface (--tools '' popover / --disallowedTools sidechat)", () => {
    expect(source).toContain('["--tools", ""]');
    expect(source).toContain('"--disallowedTools", "Bash", "Read", "Write", "Edit", "WebFetch"');
  });

  it("scopes codex by toolPolicy (read-only popover / workspace-write sidechat)", () => {
    expect(source).toContain('ephemeral ? "read-only" : "workspace-write"');
  });

  it("threads toolPolicy and OS-sandbox-wraps every CLI command", () => {
    expect(source).toContain("toolPolicy: ToolPolicy = \"auto\"");
    expect(source).toContain("return this.wrapWithOsSandbox(base, p);");
    expect(source).toContain("buildSandboxPlan({");
  });

  it("filters empty allowed roots before use (never --add-dir \"\")", () => {
    expect(source).toContain("if (!p) continue;");
    expect(source).toContain("realpathSync");
  });

  it("excludes the Zotero library from the sandbox WRITE roots (read-only reference)", () => {
    // Writable set = vault + getCliCwd only; Zotero is never writable (corruption risk).
    expect(source).toContain("private sandboxWriteRoots()");
    expect(source).toContain("this.resolveRoots([this.vaultRoot])");
    // The sandbox write-roots are built from sandboxWriteRoots() (vault-only), NOT
    // allowedRoots() (which still includes Zotero, for --add-dir read visibility).
    expect(source).toContain("const roots = [...this.sandboxWriteRoots(),");
    expect(source).not.toMatch(/const roots = \[\.\.\.this\.allowedRoots\(\)/);
  });

  it("reuses the shared expandPath helper (no duplicated ~-expansion regex)", () => {
    expect(source).toContain('from "../../utils/deviceRegistry"');
    expect(source).not.toContain("replace(/^~");
  });

  it("warns (not silently) when a non-agy CLI runs without the OS sandbox", () => {
    expect(source).toContain("OS sandbox unavailable");
    expect(source).toContain("logger.warn");
    // logger.warn already prepends [Incurator]; the legacy prefix must be gone
    // (no double-prefixing).
    expect(source).not.toContain("[incurator]");
  });

  it("writes the MCP initialize message only when child stdin is available", () => {
    expect(source).toContain('child.stdin?.write(JSON.stringify(initMessage) + "\\n")');
  });

  it("resolves --add-dir lazily — skipped on the tool-free ephemeral path", () => {
    expect(source).toContain("ephemeral ? [] : this.allowedRoots().flatMap");
  });

  it("realpaths sandbox paths so macOS firmlink (/var→/private/var) rules match", () => {
    // Seatbelt (subpath ...) only matches the REAL resolved path; an unresolved
    // path would not match the kernel's resolved write target, so cwd/output
    // files/sandbox rules must all use the canonical path.
    expect(source).toContain("realOr(homedir())");
    expect(source).toContain("realOr(this.cliTempDir())");
    // getCliCwd() returns the canonical (realpath'd) path at the source, so cwd,
    // output files, and the sandbox rule all agree without per-call-site resolving.
    expect(source).toContain("realpathSync(dir)");
  });

  it("stores device-local CLI caches in the project .cache/, not ~/.incurator", () => {
    // getCliCwd() resolves only to <repo>/.cache/cli, never the vault, ~/,
    // or OS tmp.
    expect(source).toContain('join(configured, ".cache", "cli")');
    expect(source).not.toContain('join(this.vaultRoot, ".curator", "runtime", "cli")');
    expect(source).toContain('const dir = join(this.cliCacheBase(), "tmp")');
    expect(source).toContain("tempEnv = { TMPDIR: tempDir, TEMP: tempDir, TMP: tempDir };");
    expect(source).toContain("Incurator CLI cache requires incuratorRepoPath.");
    expect(source).not.toContain('join(tmpdir(), "incurator-cli")');
    expect(source).not.toContain('join(homedir(), ".incurator-obsidian-agent-cli")');
    expect(source).not.toContain('join(homedir(), ".incurator", "tmp_images")');
  });

  it("syncAgyMcpConfig configures the live CLI permission without a blanket bypass", () => {
    expect(source).toContain("syncAgyHeadlessReadPermission(geminiDir)");
    expect(source).not.toContain("this.syncAgyReadPolicy()");
    expect(source).not.toContain("--dangerously-skip-permissions");
  });
});

describe("CLI model effort arguments", () => {
  function commandFor(settings: PluginSettings): { args: string[] } {
    const client = new LLMClient(settings, {} as never) as any;
    client.syncClaudeMcpConfig = () => "/tmp/claude-mcp.json";
    client.syncCodexMcpConfig = () => undefined;
    client.syncAgyMcpConfig = () => undefined;
    client.allowedRoots = () => [];
    client.wrapWithOsSandbox = (base: unknown) => base;
    client._chatImagePaths = [];
    client._chatImageRunDir = null;
    return client.buildCliCommand("hello", undefined, settings.provider, false, "auto");
  }

  it("omits Claude --effort for a no-effort model", () => {
    const command = commandFor({
      ...DEFAULT_SETTINGS,
      provider: "claude",
      model: "claude-haiku-4-5",
      claudeEffort: "",
    });
    expect(command.args).not.toContain("--effort");
  });

  it("passes Codex ultra through the CLI config override", () => {
    const command = commandFor({
      ...DEFAULT_SETTINGS,
      provider: "openai",
      model: "gpt-5.6-sol",
      codexReasoningEffort: "ultra",
    });
    expect(command.args).toContain('model_reasoning_effort="ultra"');
  });

  it("passes Antigravity effort for base model slugs that require it", () => {
    const command = commandFor({
      ...DEFAULT_SETTINGS,
      provider: "antigravity",
      model: "gemini-3.6-flash",
      agentEffort: "medium",
    });
    expect(command.args).toContain("--model");
    expect(command.args[command.args.indexOf("--model") + 1]).toBe(
      "gemini-3.6-flash"
    );
    expect(command.args).toContain("--effort");
    expect(command.args).toContain("medium");
  });

  it("omits Antigravity effort when the selected model has no effort dimension", () => {
    const command = commandFor({
      ...DEFAULT_SETTINGS,
      provider: "antigravity",
      model: "claude-sonnet-4-6",
      agentEffort: "",
    });
    expect(command.args).not.toContain("--effort");
  });
});

describe("chat image channel (v0.28.0)", () => {
  const source = readFileSync(
    join(fileURLToPath(new URL(".", import.meta.url)), "llm", "LLMClient.ts"),
    "utf8",
  );

  it("writes chat images to a per-run .cache/chat_images dir (not tmp_images) referenced by path", () => {
    expect(source).toContain('"chat_images"');
    expect(source).not.toContain('"tmp_images"');
    // Path reference + Read instruction mirrors the backend describe_image_via_cli.
    expect(source).toContain("Read the image file at ");
  });

  it("enables scoped Read for image turns only; text turns keep the hardened denylist", () => {
    // text-only / default claude denylist still lists Read (unchanged v0.23.0 contract)
    expect(source).toContain('"--disallowedTools", "Bash", "Read", "Write", "Edit", "WebFetch"');
    // image-turn claude denylist DROPS Read (Read allowed); others stay denied
    expect(source).toContain('"--disallowedTools", "Bash", "Write", "Edit", "WebFetch"');
    // gated on whether the assembled payload carried an image
    expect(source).toContain("hasImage");
    expect(source).toContain("this._chatImagePaths");
  });

  it("adds the image dir to --add-dir without dropping the existing allowed roots (agentic CLIs)", () => {
    expect(source).toContain("ephemeral ? [] : this.allowedRoots().flatMap");
    expect(source).toContain('addDirs.push("--add-dir"');
  });

  it("confines claude's image-turn --add-dir to the scoped image dir (no broad vault Read)", () => {
    // claude is the only provider that denies Read by default, so it is the only
    // one that re-enables Read for image turns. That Read MUST be scoped to the
    // image dir, not the broad allowed roots (vault + Zotero) — otherwise an
    // image turn could Read any vault file (defeats the v0.23.0 hardening).
    const start = source.indexOf('case "claude": {');
    expect(start).toBeGreaterThanOrEqual(0);
    const block = source.slice(start, source.indexOf('case "openai":', start));
    expect(block).toContain("const claudeAddDirs =");
    expect(block).toContain("hasImage && imageRunDir");
    expect(block).toContain('["--add-dir", imageRunDir]');
    expect(block).toContain("...claudeAddDirs");
    // The broad allowed-roots spread must NOT be what the claude branch emits.
    expect(block).not.toContain("...addDirs,");
  });

  it("cleans up the per-call image dir if streaming setup throws before spawn", () => {
    // getCliCwd()/buildCliCommand() can throw synchronously (e.g. no repo/vault
    // root). No child spawns, so neither close nor error fires — the setup must
    // be guarded so the image dir never leaks.
    expect(source).toContain("this.cleanupChatImageDir(imageRunDir);\n        reject(");
  });

  it("cleans up the per-call image dir and sweeps stale dirs on startup", () => {
    expect(source).toContain("private cleanupChatImageDir(");
    expect(source).toContain("rmSync");
    expect(source).toContain("sweepStaleChatImages");
  });

  it("resets per-call image state when (re)building the CLI prompt", () => {
    const start = source.indexOf("private messagesToCliPrompt(");
    expect(start).toBeGreaterThanOrEqual(0);
    const block = source.slice(start, start + 420);
    expect(block).toContain("this._chatImageRunDir = null");
    expect(block).toContain("this._chatImagePaths = []");
  });

  it("strips null bytes from the assembled CLI prompt (v0.42.2)", () => {
    // PDF text extraction can embed \0 which is valid in JS strings but fatal
    // in C-strings passed to OS execve via child_process.spawn(). The prompt
    // assembler must strip them at the single CLI funnel point.
    const start = source.indexOf("private messagesToCliPrompt(");
    expect(start).toBeGreaterThanOrEqual(0);
    const end = source.indexOf("private contentToCliText(", start);
    const block = source.slice(start, end);
    expect(block).toContain('.replace(/\\0/g, "")');
  });
});

describe("output-token truncation detection (v0.24.0)", () => {
  const sse = (obj: unknown) => `data: ${JSON.stringify(obj)}`;

  describe("mapOpenAIFinishReason", () => {
    it("maps `length` to a truncated terminal chunk", () => {
      expect(mapOpenAIFinishReason("length")).toEqual({
        done: true,
        finishReason: "length",
        truncated: true,
      });
    });

    it("maps `stop` / `tool_calls` to a clean (non-truncated) end", () => {
      expect(mapOpenAIFinishReason("stop")).toEqual({ done: true, finishReason: "stop" });
      expect(mapOpenAIFinishReason("tool_calls")).toEqual({ done: true, finishReason: "tool_calls" });
    });

    it("treats `content_filter` as a terminal but non-truncation reason", () => {
      const r = mapOpenAIFinishReason("content_filter");
      expect(r.done).toBe(true);
      expect(r.truncated).toBeUndefined();
    });

    it("keeps mid-stream deltas open (null finish_reason)", () => {
      expect(mapOpenAIFinishReason(null)).toEqual({ done: false });
      expect(mapOpenAIFinishReason(undefined)).toEqual({ done: false });
    });

    it("ends the stream on any other truthy finish_reason (no hang)", () => {
      expect(mapOpenAIFinishReason("function_call")).toEqual({ done: true, finishReason: "stop" });
      expect(mapOpenAIFinishReason("")).toEqual({ done: false });
    });
  });

  describe("Antigravity (Gemini) adapter", () => {
    it("flags MAX_TOKENS as truncated while still keeping the partial text", () => {
      const chunk = ADAPTERS.antigravity.parseStreamChunk(
        sse({ candidates: [{ content: { parts: [{ text: "partial" }] }, finishReason: "MAX_TOKENS" }] })
      );
      expect(chunk).toMatchObject({ text: "partial", done: true, finishReason: "length", truncated: true });
    });

    it("treats STOP as a clean finish (not truncated)", () => {
      const chunk = ADAPTERS.antigravity.parseStreamChunk(
        sse({ candidates: [{ content: { parts: [{ text: "done" }] }, finishReason: "STOP" }] })
      );
      expect(chunk).toMatchObject({ done: true, finishReason: "stop" });
      expect(chunk?.truncated).toBeUndefined();
    });

    it("maps a SAFETY/RECITATION block to content_filter, never truncated", () => {
      for (const reason of ["SAFETY", "RECITATION"]) {
        const chunk = ADAPTERS.antigravity.parseStreamChunk(
          sse({ candidates: [{ content: { parts: [{ text: "" }] }, finishReason: reason }] })
        );
        expect(chunk, reason).toMatchObject({ done: true, finishReason: "content_filter" });
        expect(chunk?.truncated).toBeUndefined();
      }
    });
  });

  describe("OpenAI / Ollama adapters", () => {
    it("flag finish_reason `length` as truncated", () => {
      for (const provider of ["openai", "ollama", "deepseek"] as const) {
        const chunk = ADAPTERS[provider].parseStreamChunk(
          sse({ choices: [{ delta: { content: "x" }, finish_reason: "length" }] })
        );
        expect(chunk, provider).toMatchObject({ done: true, finishReason: "length", truncated: true });
      }
    });
  });

  describe("Claude adapter", () => {
    it("flags message_delta stop_reason max_tokens as truncated", () => {
      const chunk = ADAPTERS.claude.parseStreamChunk(
        sse({ type: "message_delta", delta: { stop_reason: "max_tokens" } })
      );
      expect(chunk).toMatchObject({ finishReason: "length", truncated: true });
    });
  });
});
