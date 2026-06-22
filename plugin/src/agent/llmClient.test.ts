import { describe, expect, it } from "vitest";
import { vi } from "vitest";
import {
  formatMcpToolResultForDisplay,
  formatQuotaErrorMessage,
  extractAntigravityAnswerFromStderr,
  isAntigravityStatusLine,
  isQuotaErrorMessage,
  sanitizeOpenAIMessages,
  normalizeOpenAIContent,
  shouldInjectMcpTools,
  LLMClient,
  ADAPTERS,
  mapOpenAIFinishReason,
} from "./llmClient";
import { DEFAULT_SETTINGS } from "../types";
import type { LLMMessage, PluginSettings } from "../types";

vi.mock("obsidian", () => ({
  Notice: class Notice {
    constructor(_message: string) {}
  },
  requestUrl: async () => ({ json: {} }),
}));

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

import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";

describe("CLI tool-scope sandbox source contract (v0.23.0)", () => {
  const source = readFileSync(
    join(fileURLToPath(new URL(".", import.meta.url)), "llmClient.ts"),
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
    expect(source).toContain('from "../utils/deviceRegistry"');
    expect(source).not.toContain("replace(/^~");
  });

  it("warns (not silently) when a non-agy CLI runs without the OS sandbox", () => {
    expect(source).toContain("OS sandbox unavailable");
    expect(source).toContain("console.warn");
  });

  it("resolves --add-dir lazily — skipped on the tool-free ephemeral path", () => {
    expect(source).toContain("ephemeral ? [] : this.allowedRoots().flatMap");
  });

  it("realpaths sandbox paths so macOS firmlink (/var→/private/var) rules match", () => {
    // Seatbelt (subpath ...) only matches the REAL resolved path; an unresolved
    // /var/folders rule would NOT match the kernel's /private/var/folders write, so a
    // tmpdir-based getCliCwd (the default when incuratorRepoPath is unset) would have
    // its output-file/mcp-config writes silently denied.
    expect(source).toContain("realOr(homedir())");
    expect(source).toContain("realOr(tmpdir())");
    // getCliCwd() returns the canonical (realpath'd) path at the source, so cwd,
    // output files, and the sandbox rule all agree without per-call-site resolving.
    expect(source).toContain("realpathSync(dir)");
  });

  it("stores device-local CLI caches in the project .cache/, not ~/.incurator", () => {
    // getCliCwd() now resolves to <repo>/.cache/cli (or the OS tmpdir), never ~/.
    expect(source).toContain('join(repo, ".cache", "cli")');
    expect(source).toContain('join(tmpdir(), "incurator-cli")');
    expect(source).not.toContain('join(homedir(), ".incurator-obsidian-agent-cli")');
    expect(source).not.toContain('join(homedir(), ".incurator", "tmp_images")');
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
