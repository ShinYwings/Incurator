import { requestUrl, Notice } from "obsidian";
import { execFile, spawn } from "child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "fs";
import { homedir } from "os";
import { join } from "path";
import { promisify, TextDecoder } from "util";
import { buildGuiCliSearchPaths, type CLICredential, type CLIAuthResolver } from "../auth/cliAuth";
import type {
  LLMProvider,
  PluginSettings,
  LLMMessage,
  LLMContentPart,
  StreamChunk,
  ProviderUsage,
} from "../types";

// ─── Provider-specific request builders ─────────────────────────

interface ProviderAdapter {
  buildUrl(model: string): string;
  buildHeaders(credential: CLICredential): Record<string, string>;
  buildBody(
    messages: LLMMessage[],
    stream: boolean
  ): Record<string, unknown>;
  parseStreamChunk(raw: string): StreamChunk | null;
  parseFullResponse(json: unknown): string;
}

// ─── Base Adapter (shared SSE envelope + default headers) ────────

/**
 * Common behaviour shared by all provider adapters:
 *  - default Bearer + Content-Type headers (Claude adds anthropic-version)
 *  - SSE envelope parsing (`data: ` prefix, `[DONE]`, JSON.parse + try/catch)
 *
 * Subclasses implement the genuinely provider-specific bits: buildUrl,
 * buildBody, parseFullResponse, and extractDelta (pulling text/done out of a
 * parsed SSE data object).
 */
abstract class BaseProviderAdapter implements ProviderAdapter {
  abstract buildUrl(model: string): string;
  abstract buildBody(
    messages: LLMMessage[],
    stream: boolean
  ): Record<string, unknown>;
  abstract parseFullResponse(json: unknown): string;

  buildHeaders(credential: CLICredential): Record<string, string> {
    return {
      Authorization: `Bearer ${credential.token}`,
      "Content-Type": "application/json",
    };
  }

  parseStreamChunk(raw: string): StreamChunk | null {
    const line = raw.trim();
    if (!line.startsWith("data: ")) return null;
    const json = line.slice(6);
    if (json === "[DONE]") return { text: "", done: true };
    let parsed: any;
    try {
      parsed = JSON.parse(json);
    } catch {
      return null;
    }
    return this.extractDelta(parsed);
  }

  /** Extract {text, done} from one parsed SSE data object (provider-specific). */
  protected abstract extractDelta(parsed: any): StreamChunk | null;
}

// ─── Antigravity Adapter ────────────────────────────────────────

class AntigravityAdapter extends BaseProviderAdapter {
  buildUrl(model: string): string {
    return `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?alt=sse`;
  }

  buildBody(messages: LLMMessage[]): Record<string, unknown> {
    const contents = messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role === "assistant" ? "model" : "user",
        parts: this.toParts(m.content),
      }));

    const systemMsg = messages.find((m) => m.role === "system");
    const body: Record<string, unknown> = { contents };
    if (systemMsg) {
      body.systemInstruction = {
        parts: [
          {
            text:
              typeof systemMsg.content === "string"
                ? systemMsg.content
                : systemMsg.content
                    .filter((p) => p.type === "text")
                    .map((p) => (p as { type: "text"; text: string }).text)
                    .join("\n"),
          },
        ],
      };
    }
    return body;
  }

  private toParts(
    content: string | LLMContentPart[]
  ): Array<Record<string, unknown>> {
    if (typeof content === "string") {
      return [{ text: content }];
    }
    return content.map((part) => {
      if (part.type === "text") return { text: part.text };
      return {
        inlineData: { mimeType: part.mimeType, data: part.data },
      };
    });
  }

  protected extractDelta(parsed: any): StreamChunk | null {
    const text = parsed?.candidates?.[0]?.content?.parts?.[0]?.text || "";
    const done = parsed?.candidates?.[0]?.finishReason === "STOP" || false;
    return { text, done };
  }

  parseFullResponse(json: unknown): string {
    const data = json as {
      candidates?: Array<{
        content?: { parts?: Array<{ text?: string }> };
      }>;
    };
    return data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
  }
}

// ─── Claude Adapter ─────────────────────────────────────────────

class ClaudeAdapter extends BaseProviderAdapter {
  buildUrl(): string {
    return "https://api.anthropic.com/v1/messages";
  }

  buildHeaders(credential: CLICredential): Record<string, string> {
    return {
      Authorization: `Bearer ${credential.token}`,
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    };
  }

  buildBody(
    messages: LLMMessage[],
    stream: boolean
  ): Record<string, unknown> {
    const systemMsg = messages.find((m) => m.role === "system");
    const chatMessages = messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role,
        content: this.toContent(m.content),
      }));

    return {
      model: "", // Will be overridden
      max_tokens: 8192,
      stream,
      ...(systemMsg
        ? {
            system:
              typeof systemMsg.content === "string"
                ? systemMsg.content
                : systemMsg.content
                    .filter((p) => p.type === "text")
                    .map(
                      (p) => (p as { type: "text"; text: string }).text
                    )
                    .join("\n"),
          }
        : {}),
      messages: chatMessages,
    };
  }

  private toContent(
    content: string | LLMContentPart[]
  ): string | Array<Record<string, unknown>> {
    if (typeof content === "string") return content;
    return content.map((part) => {
      if (part.type === "text") return { type: "text", text: part.text };
      return {
        type: "image",
        source: {
          type: "base64",
          media_type: part.mimeType,
          data: part.data,
        },
      };
    });
  }

  protected extractDelta(parsed: any): StreamChunk | null {
    if (parsed.type === "content_block_delta") {
      return { text: parsed.delta?.text || "", done: false };
    }
    if (parsed.type === "message_stop") {
      return { text: "", done: true };
    }
    return null;
  }

  parseFullResponse(json: unknown): string {
    const data = json as {
      content?: Array<{ type: string; text?: string }>;
    };
    return (
      data?.content
        ?.filter((b) => b.type === "text")
        .map((b) => b.text || "")
        .join("") || ""
    );
  }
}

// ─── OpenAI Adapter ─────────────────────────────────────────────

class OpenAIAdapter extends BaseProviderAdapter {
  buildUrl(): string {
    return "https://api.openai.com/v1/chat/completions";
  }

  buildBody(
    messages: LLMMessage[],
    stream: boolean
  ): Record<string, unknown> {
    return {
      model: "", // Will be overridden
      stream,
      messages: messages.map((m) => ({
        role: m.role,
        content: this.toContent(m.content),
      })),
    };
  }

  private toContent(
    content: string | LLMContentPart[]
  ): string | Array<Record<string, unknown>> {
    if (typeof content === "string") return content;
    return content.map((part) => {
      if (part.type === "text") return { type: "text", text: part.text };
      return {
        type: "image_url",
        image_url: {
          url: `data:${part.mimeType};base64,${part.data}`,
        },
      };
    });
  }

  protected extractDelta(parsed: any): StreamChunk | null {
    const delta = parsed.choices?.[0]?.delta;
    const done = parsed.choices?.[0]?.finish_reason === "stop";
    return { text: delta?.content || "", done };
  }

  parseFullResponse(json: unknown): string {
    const data = json as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    return data?.choices?.[0]?.message?.content || "";
  }
}

class DeepSeekAdapter extends OpenAIAdapter {
  buildUrl(): string {
    return "https://api.deepseek.com/chat/completions";
  }
}

// ─── Ollama Adapter (OpenAI-compatible /v1/chat/completions) ────

class OllamaAdapter extends BaseProviderAdapter {
  constructor(private host: string) {
    super();
  }

  buildUrl(): string {
    return `${this.host.replace(/\/$/, "")}/v1/chat/completions`;
  }

  buildHeaders(): Record<string, string> {
    return { "Content-Type": "application/json" };
  }

  buildBody(messages: LLMMessage[], stream: boolean): Record<string, unknown> {
    return {
      model: "", // overridden by caller
      stream,
      messages: messages.map((m) => ({
        role: m.role,
        content: this.toContent(m.content),
      })),
    };
  }

  private toContent(content: string | LLMContentPart[]): string | Array<Record<string, unknown>> {
    if (typeof content === "string") return content;
    return content.map((part) => {
      if (part.type === "text") return { type: "text", text: part.text };
      return { type: "image_url", image_url: { url: `data:${part.mimeType};base64,${part.data}` } };
    });
  }

  protected extractDelta(parsed: any): StreamChunk | null {
    const delta = parsed.choices?.[0]?.delta;
    const done = parsed.choices?.[0]?.finish_reason === "stop";
    return { text: delta?.content || "", done };
  }

  parseFullResponse(json: unknown): string {
    const data = json as { choices?: Array<{ message?: { content?: string } }> };
    return data?.choices?.[0]?.message?.content || "";
  }
}

// ─── Main LLM Client ────────────────────────────────────────────

const ADAPTERS: Record<LLMProvider, ProviderAdapter> = {
  antigravity: new AntigravityAdapter(),
  claude: new ClaudeAdapter(),
  openai: new OpenAIAdapter(),
  ollama: new OllamaAdapter("http://localhost:11434"), // host updated at runtime
  deepseek: new DeepSeekAdapter(),
};

export function isQuotaErrorMessage(message: string): boolean {
  const value = message.toLowerCase();
  return (
    value.includes("429") ||
    value.includes("quota") ||
    value.includes("capacity") ||
    value.includes("resource_exhausted") ||
    value.includes("rate limit") ||
    value.includes("rate_limit") ||
    value.includes("insufficient balance") ||
    value.includes("insufficient_quota")
  );
}

export function formatQuotaErrorMessage(provider: LLMProvider, message: string): string {
  const label = provider === "openai" ? "Codex/OpenAI" : provider;
  return (
    `${label} quota or capacity is currently unavailable.\n\n` +
    `${message.slice(0, 700)}\n\n` +
    "Switch provider/model, configure a fallback, or retry after quota resets."
  );
}

export function formatMcpToolResultForDisplay(toolName: string, raw: string): string {
  if (!toolName.includes("curator_query")) {
    return raw.length > 600 ? raw.slice(0, 600) + "\n…" : raw;
  }
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return raw.length > 600 ? raw.slice(0, 600) + "\n…" : raw;
    }
    const compact = {
      ok: parsed.ok,
      question: parsed.question,
      route: parsed.route,
      trace_id: parsed.trace_id,
      fallback: parsed.fallback,
      error: parsed.error,
      trace: parsed.trace,
    };
    return JSON.stringify(compact, null, 2);
  } catch {
    return raw.length > 600 ? raw.slice(0, 600) + "\n…" : raw;
  }
}

const execFileAsync = promisify(execFile);
const CLI_TIMEOUT_MS = 5 * 60 * 1000;

export class LLMClient {
  private getAugmentedEnv(extraEnv?: Record<string, string | undefined>): NodeJS.ProcessEnv {
    const home = process.env.HOME || process.env.USERPROFILE || "";
    const customPaths = buildGuiCliSearchPaths(home).join(":");

    const currentPath = process.env.PATH || "";
    const newPath = currentPath ? `${customPaths}:${currentPath}` : customPaths;

    return {
      ...process.env,
      ...extraEnv,
      PATH: newPath,
    };
  }
  private settings: PluginSettings;
  private auth: CLIAuthResolver;
  private abortController: AbortController | null = null;
  private vaultRoot: string;
  private persistSettings?: () => Promise<void>;

  constructor(
    settings: PluginSettings,
    auth: CLIAuthResolver,
    vaultRoot: string = "",
    persistSettings?: () => Promise<void>
  ) {
    this.settings = settings;
    this.auth = auth;
    this.vaultRoot = vaultRoot;
    this.persistSettings = persistSettings;
  }

  updateSettings(settings: PluginSettings): void {
    this.settings = settings;
  }

  /** Abort any in-flight request */
  abort(): void {
    this.abortController?.abort();
    this.abortController = null;
  }

  /** Test MCP Connection */
  async testMcpConnection(serverName: string): Promise<{ name: string; version: string }> {
    return new Promise((resolve, reject) => {
      const rawServer = this.settings.mcpServers.find((s) => s.name === serverName);
      if (!rawServer) {
        return reject(new Error(`Server ${serverName} not found in settings.`));
      }

      if (!rawServer.command) {
        return reject(new Error("Command is empty."));
      }

      const serverConfig = this.processMcpServer(rawServer);
      const env = this.getAugmentedEnv(serverConfig.env);

      const child = spawn(serverConfig.command, serverConfig.args, { env });

      let stdoutBuffer = "";
      let stderrBuffer = "";
      let resolved = false;

      const timeout = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          child.kill();
          reject(new Error("Connection timed out after 5 seconds."));
        }
      }, 5000);

      child.stdout.on("data", (data) => {
        if (resolved) return;
        stdoutBuffer += data.toString();
        
        // Try to parse out the first complete JSON object (MCP initialize response)
        const lines = stdoutBuffer.split("\n");
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const parsed = JSON.parse(line);
            if (parsed.jsonrpc === "2.0" && parsed.id === 1) {
              resolved = true;
              clearTimeout(timeout);
              child.kill();
              
              const info = parsed.result?.serverInfo || { name: "Unknown", version: "Unknown" };
              resolve({ name: info.name, version: info.version });
              return;
            }
          } catch (e) {
            // Incomplete JSON line or non-JSON output, keep buffering
          }
        }
      });

      child.stderr.on("data", (data) => {
        stderrBuffer += data.toString();
      });

      child.on("error", (err) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timeout);
          reject(new Error(`Failed to start process: ${err.message}`));
        }
      });

      child.on("close", (code) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timeout);
          reject(new Error(`Process exited with code ${code}. Stderr: ${stderrBuffer.substring(0, 200)}`));
        }
      });

      const initMessage = {
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2024-11-05",
          capabilities: {},
          clientInfo: {
            name: "incurator-obsidian-agent-test",
            version: "1.0.0"
          }
        }
      };
      
      child.stdin.write(JSON.stringify(initMessage) + "\n");
    });
  }

  /**
   * Stream a chat completion, calling onChunk for each token.
   * Returns the full assembled response text.
   */
  async streamChat(
    messages: LLMMessage[],
    onChunk: (chunk: StreamChunk) => void
  ): Promise<string> {
    this.abortController = new AbortController();
    const provider = this.settings.provider;

    if (this.shouldUseCli(messages)) {
      return this.streamChatViaCli(messages, onChunk);
    }

    // For Ollama, refresh the adapter host from current settings
    if (provider === "ollama") {
      ADAPTERS.ollama = new OllamaAdapter(this.settings.ollamaHost || "http://localhost:11434");
    }

    const adapter = ADAPTERS[provider];
    const credential = provider === "ollama"
      ? { type: "bearer" as const, token: "" }
      : provider === "deepseek"
        ? { type: "bearer" as const, token: this.settings.deepseekApiKey || process.env.DEEPSEEK_API_KEY || "" }
      : await this.auth.resolveCredential(provider);

    const url = adapter.buildUrl(this.settings.model);
    const headers = adapter.buildHeaders(credential);
    const body = adapter.buildBody(messages, true);

    // Always inject the model into the body for HTTP providers
    (body as Record<string, unknown>).model = this.settings.model;

    // Use fetch for streaming (Obsidian's requestUrl doesn't support streaming)
    let fullText = "";

    try {
      let response: Response;
      try {
        response = await fetch(url, {
          method: "POST",
          headers,
          body: JSON.stringify(body),
          signal: this.abortController.signal,
        });
      } catch (fetchErr) {
        if (provider === "ollama") {
          throw new Error(
            `Ollama is not reachable at ${this.settings.ollamaHost || "http://localhost:11434"}.\n` +
            `Start it with: ollama serve`
          );
        }
        throw fetchErr;
      }

      if (!response.ok) {
        const errorText = await response.text();
        if (response.status === 401 || response.status === 403) {
          if (provider === "ollama") {
            throw new Error(`Ollama returned auth error ${response.status} — check your Ollama server config.`);
          }
          if (provider === "deepseek") {
            this.auth.invalidate(provider);
            throw new Error(`DeepSeek API authentication failed (${response.status}). Check DEEPSEEK_API_KEY.`);
          }
          this.auth.invalidate(provider);
          new Notice(`${provider} HTTP auth failed. Retrying through the provider CLI login session.`);
          return this.streamChatViaCli(messages, onChunk);
        }
        throw new Error(`LLM API error ${response.status}: ${errorText.slice(0, 200)}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body is not readable");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete lines
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          const chunk = adapter.parseStreamChunk(line);
          if (chunk) {
            fullText += chunk.text;
            onChunk(chunk);
            if (chunk.done) break;
          }
        }
      }

      // Process any remaining buffer
      if (buffer.trim()) {
        const chunk = adapter.parseStreamChunk(buffer);
        if (chunk) {
          fullText += chunk.text;
          onChunk(chunk);
        }
      }

      // Ensure we send a done signal
      onChunk({ text: "", done: true });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        onChunk({ text: "", done: true });
        return fullText;
      }
      const msg = err instanceof Error ? err.message : String(err);
      if (isQuotaErrorMessage(msg)) {
        throw new Error(formatQuotaErrorMessage(provider, msg));
      }
      throw err;
    } finally {
      this.abortController = null;
    }

    return fullText;
  }

  /**
   * Non-streaming request (for inline edits where we need the full result).
   */
  async complete(messages: LLMMessage[]): Promise<string> {
    const provider = this.settings.provider;

    if (this.shouldUseCli(messages)) {
      return this.completeViaCli(messages);
    }

    // Ollama uses fetch for non-streaming too (requestUrl may not reach localhost in all envs)
    if (provider === "ollama") {
      ADAPTERS.ollama = new OllamaAdapter(this.settings.ollamaHost || "http://localhost:11434");
      const adapter = ADAPTERS.ollama;
      const body = adapter.buildBody(messages, false);
      (body as Record<string, unknown>).model = this.settings.model;
      try {
        const res = await fetch(adapter.buildUrl(this.settings.model), {
          method: "POST",
          headers: adapter.buildHeaders({ type: "bearer", token: "" }),
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`Ollama error ${res.status}: ${await res.text()}`);
        return adapter.parseFullResponse(await res.json());
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("Failed to fetch") || msg.includes("ECONNREFUSED")) {
          throw new Error(`Ollama not reachable at ${this.settings.ollamaHost || "http://localhost:11434"}. Run: ollama serve`);
        }
        throw new Error(`Ollama request failed: ${msg}`);
      }
    }

    const adapter = ADAPTERS[provider];
    const credential = provider === "deepseek"
      ? { type: "bearer" as const, token: this.settings.deepseekApiKey || process.env.DEEPSEEK_API_KEY || "" }
      : await this.auth.resolveCredential(provider);

    let url = adapter.buildUrl(this.settings.model);
    const headers = adapter.buildHeaders(credential);
    const body = adapter.buildBody(messages, false);

    // For Antigravity non-streaming, use generateContent instead of streamGenerateContent
    if (provider === "antigravity") {
      url = `https://generativelanguage.googleapis.com/v1beta/models/${this.settings.model}:generateContent`;
    }

    (body as Record<string, unknown>).model = this.settings.model;

    try {
      const response = await requestUrl({
        url,
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      return adapter.parseFullResponse(response.json);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("401") || msg.includes("403")) {
        if (provider === "deepseek") {
          this.auth.invalidate(provider);
          throw new Error("DeepSeek API authentication failed. Check DEEPSEEK_API_KEY.");
        }
        this.auth.invalidate(provider);
        new Notice(`${provider} HTTP auth failed. Retrying through the provider CLI login session.`);
        return this.completeViaCli(messages);
      }
      if (isQuotaErrorMessage(msg)) {
        throw new Error(formatQuotaErrorMessage(provider, msg));
      }
      throw new Error(`LLM request failed: ${msg}`);
    }
  }

  private shouldUseCli(_messages: LLMMessage[]): boolean {
    // Ollama and DeepSeek are direct HTTP providers.
    if (this.settings.provider === "ollama" || this.settings.provider === "deepseek") return false;
    // All other providers route through their respective CLIs.
    return true;
  }

  private streamChatViaCli(
    messages: LLMMessage[],
    onChunk: (chunk: StreamChunk) => void
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      const provider = this.settings.provider;
      const prompt = this.messagesToCliPrompt(messages);
      const cwd = this.getCliCwd();
      const outputFile =
        provider === "openai"
          ? join(
              cwd,
              `codex-output-${Date.now()}-${Math.random().toString(36).slice(2)}.txt`
            )
          : undefined;
      const { command, args, env, stdin } = this.buildCliCommand(
        prompt,
        outputFile,
        provider,
        true
      );

      let fullOutput = "";
      let fullStdout = "";
      let fullStderr = "";

      // State for CLI JSON/event parsing
      let jsonBuffer = "";
      let codexJsonBuffer = "";
      let inThinking = false;
      let prevThinkingLen = 0;
      let prevTextLen = 0;
      const seenToolIds = new Map<string, string>();
      let claudeResult = "";
      let claudeIsError = false;
      let statusBlockOpen = false;
      let lastCodexStatus = "";
      let codexAnswerText = "";
      let observedUsage: Partial<ProviderUsage> | undefined;

      const emitCodexStatus = (status: string) => {
        if (!status || status === lastCodexStatus) return;
        lastCodexStatus = status;
        if (!statusBlockOpen) {
          onChunk({ text: "<thinking>\n", done: false });
          statusBlockOpen = true;
        }
        onChunk({ text: `\n- ${status}`, done: false });
      };

      const closeStatusBlock = () => {
        if (statusBlockOpen) {
          onChunk({ text: "\n</thinking>\n\n", done: false });
          statusBlockOpen = false;
          inThinking = false;
        }
      };

      const emitMcpAvailability = () => {
        const enabledServers = this.settings.mcpServers
          .filter((server) => server.enabled && server.name.trim())
          .map((server) => server.name.trim());
        if (enabledServers.length === 0) return;
        emitCodexStatus(`MCP servers available: ${enabledServers.join(", ")}`);
      };

      const processClaudeJsonLine = (line: string) => {
        if (!line.trim()) return;
        let event: Record<string, unknown>;
        try {
          event = JSON.parse(line);
        } catch {
          return;
        }

        if (event.type === "assistant") {
          const content = (event.message as Record<string, unknown>)?.content as Array<Record<string, unknown>> || [];
          for (const block of content) {
            if (block.type === "thinking") {
              const thinking = (block.thinking as string) || "";
              if (thinking.length > prevThinkingLen) {
                if (!inThinking) {
                  if (!statusBlockOpen) {
                    onChunk({ text: "<thinking>\n", done: false });
                    statusBlockOpen = true;
                  } else {
                    onChunk({ text: "\n\n", done: false });
                  }
                  inThinking = true;
                }
                onChunk({ text: thinking.slice(prevThinkingLen), done: false });
                prevThinkingLen = thinking.length;
              }
            } else if (block.type === "tool_use") {
              const toolId = (block.id as string) || "";
              if (!seenToolIds.has(toolId)) {
                const toolName = (block.name as string) || "tool";
                seenToolIds.set(toolId, toolName);
                if (inThinking) {
                  inThinking = false;
                }
                if (!statusBlockOpen) {
                  onChunk({ text: "<thinking>\n", done: false });
                  statusBlockOpen = true;
                }
                const input = block.input as Record<string, unknown> || {};
                // Format args as compact JSON, capped to avoid huge blocks
                const argsJson = JSON.stringify(input, null, 2);
                const argsDisplay = argsJson.length > 800 ? argsJson.slice(0, 800) + "\n  ..." : argsJson;
                onChunk({ text: `\n\n🔧 **${toolName}**\n\`\`\`json\n${argsDisplay}\n\`\`\``, done: false });
              }
            } else if (block.type === "text") {
              const text = (block.text as string) || "";
              if (text.length > prevTextLen) {
                if (inThinking || statusBlockOpen) {
                  onChunk({ text: "\n</thinking>\n\n", done: false });
                  inThinking = false;
                  statusBlockOpen = false;
                }
                onChunk({ text: text.slice(prevTextLen), done: false });
                prevTextLen = text.length;
              }
            }
          }
        } else if (event.type === "user") {
          const content = (event.message as Record<string, unknown>)?.content as Array<Record<string, unknown>> || [];
          for (const block of content) {
            if (block.type === "tool_result") {
              const toolId = (block.tool_use_id as string) || "tool";
              const toolName = seenToolIds.get(toolId) || "tool";
              let resultText = "";
              if (typeof block.content === "string") {
                resultText = block.content;
              } else if (Array.isArray(block.content)) {
                resultText = JSON.stringify(block.content, null, 2);
              } else if (event.tool_use_result) {
                resultText = JSON.stringify(event.tool_use_result, null, 2);
              }
              
              resultText = formatMcpToolResultForDisplay(toolName, resultText);
              if (!statusBlockOpen) {
                onChunk({ text: "<thinking>\n", done: false });
                statusBlockOpen = true;
              }
              onChunk({ text: `\n\n✅ **${toolName}** result:\n\`\`\`\n${resultText}\n\`\`\``, done: false });
            }
          }
        } else if (event.type === "result") {
          if (statusBlockOpen || inThinking) {
            onChunk({ text: "\n</thinking>\n\n", done: false });
            inThinking = false;
            statusBlockOpen = false;
          }
          claudeResult = (event.result as string) || "";
          claudeIsError = (event.is_error as boolean) || false;
          observedUsage = this.mergeUsage(observedUsage, this.extractUsage(event));
        }
      };

      if (provider === "openai") {
        emitCodexStatus(`Preparing context for ${this.settings.model}`);
        emitCodexStatus("Starting Codex CLI");
      } else if (provider === "antigravity") {
        emitCodexStatus("Thinking... (Antigravity is generating the full response)");
      }
      emitMcpAvailability();

      const child = spawn(command, args, {
        cwd,
        env: this.getAugmentedEnv(env),
        stdio: [stdin === undefined ? "ignore" : "pipe", "pipe", "pipe"],
        windowsHide: true,
      });

      if (stdin !== undefined) {
        child.stdin?.end(stdin);
      }

      if (this.abortController) {
        this.abortController.signal.addEventListener("abort", () => {
          child.kill();
        });
      }

      const stdoutDecoder = new TextDecoder("utf-8");
      const stderrDecoder = new TextDecoder("utf-8");

      const processStdoutText = (text: string) => {
        if (!text) return;
        fullOutput += text;

        if (provider === "claude") {
          jsonBuffer += text;
          const lines = jsonBuffer.split("\n");
          jsonBuffer = lines.pop() || "";
          for (const line of lines) {
            processClaudeJsonLine(line);
          }
        } else if (provider === "openai") {
          codexJsonBuffer += text;
          const lines = codexJsonBuffer.split("\n");
          codexJsonBuffer = lines.pop() || "";
          for (const line of lines) {
            observedUsage = this.mergeUsage(observedUsage, this.extractUsageFromJsonLine(line));
            const status = this.summarizeCodexJsonLine(line);
            if (status && !codexAnswerText) emitCodexStatus(status);
            const answerText = this.extractCodexAnswerTextFromJsonLine(line);
            if (answerText && answerText.length > codexAnswerText.length) {
              closeStatusBlock();
              onChunk({
                text: answerText.slice(codexAnswerText.length),
                done: false,
              });
              codexAnswerText = answerText;
            }
          }
        } else {
          closeStatusBlock();
          onChunk({ text, done: false });
        }
      };

      child.stdout?.on("data", (data) => {
        const text = stdoutDecoder.decode(data, { stream: true });
        
        fullStdout += text;
        const authKeywords = [
          "Authentication required",
          "paste the authorization code",
          "You must login",
          "claude login",
          "codex login",
          "Session expired"
        ];
        if (authKeywords.some(kw => fullStdout.includes(kw))) {
          child.kill();
          reject(new Error(`CLI authentication required. Please go to Settings -> Incurator -> ${provider} and click 'Login' to authenticate interactively.`));
          return;
        }

        processStdoutText(text);
      });

      child.stderr?.on("data", (data) => {
        const text = stderrDecoder.decode(data, { stream: true });
        
        fullStderr += text;
        const authKeywords = [
          "Authentication required",
          "paste the authorization code",
          "You must login",
          "claude login",
          "codex login",
          "Session expired"
        ];
        if (authKeywords.some(kw => fullStderr.includes(kw))) {
          child.kill();
          reject(new Error(`CLI authentication required. Please go to Settings -> Incurator -> ${provider} and click 'Login' to authenticate interactively.`));
          return;
        }
        
        // For non-JSON stdout providers, intercept stderr as thinking updates
        if (provider !== "claude" && provider !== "openai") {
          const lines = text.split("\n");
          for (const line of lines) {
            const cleanLine = line.trim();
            if (cleanLine) {
              emitCodexStatus(cleanLine);
            }
          }
        }
      });

      child.on("close", (code) => {
        processStdoutText(stdoutDecoder.decode());
        fullStderr += stderrDecoder.decode();

        if (provider === "claude") {
          // Flush remaining buffer
          if (jsonBuffer.trim()) processClaudeJsonLine(jsonBuffer);
          if (inThinking || statusBlockOpen) onChunk({ text: "</thinking>\n\n", done: false });
          onChunk({ text: "", done: true });
          if (claudeIsError) {
            reject(new Error(`claude CLI error: ${claudeResult}`));
          } else {
            this.recordUsage(provider, observedUsage);
            resolve(claudeResult || fullOutput);
          }
          return;
        }

        if (provider === "openai" && codexJsonBuffer.trim()) {
          observedUsage = this.mergeUsage(
            observedUsage,
            this.extractUsageFromJsonLine(codexJsonBuffer)
          );
          const answerText = this.extractCodexAnswerTextFromJsonLine(codexJsonBuffer);
          if (answerText && answerText.length > codexAnswerText.length) {
            closeStatusBlock();
            onChunk({
              text: answerText.slice(codexAnswerText.length),
              done: false,
            });
            codexAnswerText = answerText;
          }
          const status = this.summarizeCodexJsonLine(codexJsonBuffer);
          if (status && !codexAnswerText) emitCodexStatus(status);
        }

        if (outputFile && existsSync(outputFile)) {
          try {
            fullOutput = readFileSync(outputFile, "utf-8").trim();
            unlinkSync(outputFile);
          } catch (e) {
            // ignore
          }
        } else {
          fullOutput = this.cleanCliOutput(provider, fullOutput);
        }

        if (provider === "openai") {
          closeStatusBlock();
          if (!codexAnswerText) {
            onChunk({ text: fullOutput, done: false });
          }
        } else {
          // antigravity: ensure thinking block is closed before done
          closeStatusBlock();
        }

        onChunk({ text: "", done: true });

        if (code !== 0 && !this.abortController?.signal.aborted && fullOutput.trim().length === 0) {
          const errText = fullStderr.trim();
          reject(new Error(`${provider} CLI failed: ${errText.slice(0, 500)}`));
        } else {
          this.recordUsage(provider, observedUsage);
          resolve(fullOutput);
        }
      });

      child.on("error", (err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("ENOENT")) {
          reject(
            new Error(
              `${provider} CLI "${command}" is not installed or not found on PATH.\n\nInstall the CLI first, then retry.`
            )
          );
        } else {
          reject(
            new Error(
              `${provider} CLI request failed: ${msg}\n\nRun the provider CLI login again, then retry.`
            )
          );
        }
      });
    });
  }

  private summarizeToolInput(toolName: string, input: Record<string, unknown>): string {
    const lower = toolName.toLowerCase();
    if (lower === "bash") return `\`${String(input.command || "").slice(0, 120)}\``;
    if (lower === "read") return String(input.file_path || "").split("/").pop() || "";
    if (lower === "write" || lower === "edit") return String(input.file_path || "").split("/").pop() || "";
    if (lower === "websearch") return `"${String(input.query || "").slice(0, 80)}"`;
    if (lower === "webfetch") return String(input.url || "").slice(0, 80);
    // MCP tools: mcp_<server>_<method> → show method + first value
    const keys = Object.keys(input);
    if (keys.length === 0) return "";
    const first = String(input[keys[0]] || "").slice(0, 80);
    return first ? `${keys[0]}="${first}"` : "";
  }

  private summarizeCodexJsonLine(line: string): string | null {
    if (!line.trim()) return null;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return null;
    }

    const msg =
      event.msg && typeof event.msg === "object"
        ? (event.msg as Record<string, unknown>)
        : undefined;
    const type = String(event.type || msg?.type || "");
    const item = (event.item || msg || event) as Record<string, unknown>;
    const itemType = String(item.type || "");
    const toolName = this.findNestedString(item, ["name", "tool_name", "command"]);

    if (type.includes("turn.started")) return "Planning the answer";
    if (type.includes("turn.completed")) return "Composing final response";
    if (type.includes("error")) return "Codex reported an error";
    if (type.includes("item.started") || type.includes("item.completed")) {
      if (itemType.includes("reasoning")) return "Reasoning over the supplied context";
      if (itemType.includes("tool") || toolName) {
        // Show actual tool name and arguments for MCP tool calls
        const isMcp = toolName && toolName.startsWith("mcp_");
        const callArgs = this.findNestedString(item, ["arguments", "input", "params"]);
        if (isMcp && callArgs) {
          return `🔧 **${toolName}** \`${callArgs.slice(0, 120)}\``;
        }
        return `Using tool: **${toolName || "unknown"}**`;
      }
      if (itemType.includes("message")) return "Drafting response text";
    }
    // Tool output / result events
    if (type.includes("tool_result") || type.includes("tool_output")) {
      const outputVal = this.findNestedString(item, ["output", "result", "content"]);
      const name = toolName || "tool";
      return outputVal ? `✅ **${name}** → \`${outputVal.slice(0, 120)}\`` : `✅ **${name}** returned`;
    }

    return null;
  }

  private extractCodexAnswerTextFromJsonLine(line: string): string | null {
    if (!line.trim()) return null;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return null;
    }

    const msg =
      event.msg && typeof event.msg === "object"
        ? (event.msg as Record<string, unknown>)
        : undefined;
    const item = (event.item ||
      msg?.item ||
      msg ||
      event) as Record<string, unknown>;

    return this.extractAssistantMessageText(item);
  }

  private extractAssistantMessageText(item: Record<string, unknown>): string | null {
    const itemType = String(item.type || "").toLowerCase();
    if (
      itemType.includes("reasoning") ||
      itemType.includes("tool") ||
      itemType.includes("function") ||
      itemType.includes("command")
    ) {
      return null;
    }

    const directText = item.text;
    if (typeof directText === "string" && directText.trim()) return directText;

    const directContent = item.content;
    if (typeof directContent === "string" && directContent.trim()) return directContent;
    if (Array.isArray(directContent)) {
      const text = directContent
        .map((block) => {
          if (!block || typeof block !== "object") return "";
          const record = block as Record<string, unknown>;
          const blockType = String(record.type || "").toLowerCase();
          if (
            blockType &&
            !blockType.includes("text") &&
            !blockType.includes("message") &&
            !blockType.includes("output")
          ) {
            return "";
          }
          return typeof record.text === "string"
            ? record.text
            : typeof record.content === "string"
              ? record.content
              : "";
        })
        .join("");
      if (text.trim()) return text;
    }

    const message = item.message;
    if (message && typeof message === "object") {
      return this.extractAssistantMessageText(message as Record<string, unknown>);
    }

    return null;
  }

  private findNestedString(value: unknown, keys: string[]): string | null {
    if (!value || typeof value !== "object") return null;
    const record = value as Record<string, unknown>;
    for (const key of keys) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate.trim().slice(0, 120);
      }
    }
    for (const child of Object.values(record)) {
      const found = this.findNestedString(child, keys);
      if (found) return found;
    }
    return null;
  }

  private async completeViaCli(messages: LLMMessage[]): Promise<string> {
    const provider = this.settings.provider;
    const prompt = this.messagesToCliPrompt(messages);
    const cwd = this.getCliCwd();
    const outputFile =
      provider === "openai"
        ? join(
            cwd,
            `codex-output-${Date.now()}-${Math.random().toString(36).slice(2)}.txt`
          )
        : undefined;
    const { command, args, env } = this.buildCliCommand(prompt, outputFile, provider);

    try {
      const { stdout, stderr } = await execFileAsync(command, args, {
        cwd,
        env: { ...process.env, ...env },
        timeout: CLI_TIMEOUT_MS,
        maxBuffer: 10 * 1024 * 1024,
        windowsHide: true,
      });

      if (provider === "claude") {
        const result = this.extractClaudeJsonResult(stdout);
        if (result !== null) {
          this.recordUsage(provider, this.extractUsageFromJsonLines(stdout));
          return result;
        }
        throw new Error("claude CLI returned no result event.");
      }

      const output =
        outputFile && existsSync(outputFile)
          ? readFileSync(outputFile, "utf-8").trim()
          : this.cleanCliOutput(provider, stdout);
      if (output.length > 0) {
        this.recordUsage(provider, this.extractUsageFromJsonLines(stdout));
        return output;
      }

      const err = stderr.trim();
      if (err.length > 0) {
        throw new Error(err.slice(0, 500));
      }
      throw new Error(`${provider} CLI returned an empty response.`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("ENOENT")) {
        throw new Error(
          `${provider} CLI is not installed or not found on PATH.\n\nInstall the CLI first, then retry.`
        );
      }
      throw new Error(
        `${provider} CLI request failed: ${msg}\n\nRun the provider CLI login again, then retry.`
      );
    } finally {
      if (outputFile && existsSync(outputFile)) {
        unlinkSync(outputFile);
      }
    }
  }

  private extractClaudeJsonResult(stdout: string): string | null {
    for (const line of stdout.trim().split("\n").reverse()) {
      try {
        const event = JSON.parse(line) as Record<string, unknown>;
        if (event.type === "result") {
          if (event.is_error) throw new Error(String(event.result || "claude error"));
          return String(event.result || "");
        }
      } catch (e) {
        if (e instanceof Error && e.message.startsWith("claude error")) throw e;
      }
    }
    return null;
  }

  private extractUsageFromJsonLines(stdout: string): Partial<ProviderUsage> | undefined {
    let usage: Partial<ProviderUsage> | undefined;
    for (const line of stdout.split("\n")) {
      usage = this.mergeUsage(usage, this.extractUsageFromJsonLine(line));
    }
    return usage;
  }

  private extractUsageFromJsonLine(line: string): Partial<ProviderUsage> | undefined {
    if (!line.trim()) return undefined;
    try {
      return this.extractUsage(JSON.parse(line) as Record<string, unknown>);
    } catch {
      return undefined;
    }
  }

  private extractUsage(event: Record<string, unknown>): Partial<ProviderUsage> | undefined {
    const usageCandidate =
      event.usage ||
      (event.message as Record<string, unknown> | undefined)?.usage ||
      (event.msg as Record<string, unknown> | undefined)?.usage ||
      (event.msg as Record<string, unknown> | undefined)?.usage_info;
    if (!usageCandidate || typeof usageCandidate !== "object") return undefined;

    const usage = usageCandidate as Record<string, unknown>;
    const inputTokens = this.readUsageNumber(usage, [
      "input_tokens",
      "inputTokens",
      "prompt_tokens",
      "promptTokens",
    ]);
    const cachedInputTokens = this.readUsageNumber(usage, [
      "cached_input_tokens",
      "cachedInputTokens",
      "cache_read_input_tokens",
      "cacheReadInputTokens",
    ]);
    const outputTokens = this.readUsageNumber(usage, [
      "output_tokens",
      "outputTokens",
      "completion_tokens",
      "completionTokens",
    ]);
    const reasoningOutputTokens = this.readUsageNumber(usage, [
      "reasoning_output_tokens",
      "reasoningOutputTokens",
      "reasoning_tokens",
      "reasoningTokens",
    ]);

    if (
      inputTokens === 0 &&
      cachedInputTokens === 0 &&
      outputTokens === 0 &&
      reasoningOutputTokens === 0
    ) {
      return undefined;
    }

    return {
      inputTokens,
      cachedInputTokens,
      outputTokens,
      reasoningOutputTokens,
    };
  }

  private readUsageNumber(usage: Record<string, unknown>, keys: string[]): number {
    for (const key of keys) {
      const value = usage[key];
      if (typeof value === "number" && Number.isFinite(value)) return value;
      if (typeof value === "string") {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
      }
    }
    return 0;
  }

  private mergeUsage(
    current: Partial<ProviderUsage> | undefined,
    next: Partial<ProviderUsage> | undefined
  ): Partial<ProviderUsage> | undefined {
    if (!next) return current;
    return {
      inputTokens: (current?.inputTokens || 0) + (next.inputTokens || 0),
      cachedInputTokens:
        (current?.cachedInputTokens || 0) + (next.cachedInputTokens || 0),
      outputTokens: (current?.outputTokens || 0) + (next.outputTokens || 0),
      reasoningOutputTokens:
        (current?.reasoningOutputTokens || 0) +
        (next.reasoningOutputTokens || 0),
    };
  }

  private recordUsage(provider: LLMProvider, usage?: Partial<ProviderUsage>): void {
    const current = this.settings.providerUsage[provider] || {
      requests: 0,
      inputTokens: 0,
      cachedInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0,
    };
    this.settings.providerUsage[provider] = {
      requests: current.requests + 1,
      inputTokens: current.inputTokens + (usage?.inputTokens || 0),
      cachedInputTokens:
        current.cachedInputTokens + (usage?.cachedInputTokens || 0),
      outputTokens: current.outputTokens + (usage?.outputTokens || 0),
      reasoningOutputTokens:
        current.reasoningOutputTokens + (usage?.reasoningOutputTokens || 0),
      lastUsedAt: Date.now(),
    };
    this.persistSettings?.().catch(() => {
      // Usage accounting should never block the answer.
    });
  }

  private buildCliCommand(
    prompt: string,
    outputFile?: string,
    provider?: LLMProvider,
    preferStdin = false
  ): {
    command: string;
    args: string[];
    env?: Record<string, string>;
    stdin?: string;
  } {
    const model = this.settings.model;
    switch (provider ?? this.settings.provider) {
      case "antigravity": {
        this.syncAgyMcpConfig();
        return {
          command: "agy",
          args: [
            "-p", prompt,
            "--print-timeout", `${Math.max(30, this.settings.antigravityPrintTimeoutSec || 300)}s`,
            "--dangerously-skip-permissions",
          ],
          env: {
            GEMINI_CLI_TRUST_WORKSPACE: "true",
            ANTIGRAVITY_TRUST_WORKSPACE: "true",
          },
        };
      }
      case "claude": {
        const claudeMcpPath = this.syncClaudeMcpConfig();
        return {
          command: "claude",
          args: [
            "--mcp-config", claudeMcpPath,
            "-p", prompt,
            "--model", model,
            "--effort", this.settings.claudeEffort,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
          ],
        };
      }
      case "openai": {
        this.syncCodexMcpConfig();
        return {
          command: "codex",
          args: [
            "--profile", "obsidian",
            "exec",
            "-m",
            model,
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--json",
            "-c",
            `model_reasoning_effort=${JSON.stringify(this.settings.codexReasoningEffort)}`,
            ...(outputFile ? ["--output-last-message", outputFile] : []),
            preferStdin ? "-" : prompt,
          ],
          stdin: preferStdin ? prompt : undefined,
        };
      }
      default:
        throw new Error(`Provider "${provider ?? this.settings.provider}" does not support CLI mode.`);
    }
  }

  private getCliCwd(): string {
    const dir = join(homedir(), ".incurator-obsidian-agent-cli");
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    return dir;
  }

  private processMcpServer(server: any): any {
    const replaceVars = (str: string) => str.replace(/\{VAULT_ROOT\}/g, this.vaultRoot);
    
    const processedEnv: Record<string, string> = {};
    for (const [k, v] of Object.entries(server.env || {})) {
      processedEnv[k] = typeof v === 'string' ? replaceVars(v) : String(v);
    }

    return {
      command: server.command,
      args: server.args.map((a: string) => replaceVars(a)),
      env: processedEnv,
    };
  }

  private syncClaudeMcpConfig(): string {
    const mcpServers: Record<string, unknown> = {};
    for (const server of this.settings.mcpServers) {
      if (server.enabled) {
        mcpServers[server.name] = this.processMcpServer(server);
      }
    }
    const claudeMcpPath = join(this.getCliCwd(), "claude_mcp.json");
    writeFileSync(
      claudeMcpPath,
      JSON.stringify({ mcpServers }, null, 2)
    );
    return claudeMcpPath;
  }

  private syncCodexMcpConfig(): void {
    const codexDir = join(homedir(), ".codex");
    if (!existsSync(codexDir)) {
      mkdirSync(codexDir, { recursive: true });
    }
    const tomlPath = join(codexDir, "obsidian.config.toml");
    
    let tomlContent = "";
    for (const rawServer of this.settings.mcpServers) {
      if (!rawServer.enabled) continue;
      const server = this.processMcpServer(rawServer);
      tomlContent += `[mcp_servers.${rawServer.name}]\n`;
      tomlContent += `command = ${JSON.stringify(server.command)}\n`;
      tomlContent += `args = ${JSON.stringify(server.args)}\n`;
      if (server.env && Object.keys(server.env).length > 0) {
        tomlContent += `[mcp_servers.${rawServer.name}.env]\n`;
        for (const [k, v] of Object.entries(server.env)) {
          tomlContent += `${k} = ${JSON.stringify(v)}\n`;
        }
      }
      tomlContent += "\n";
    }
    writeFileSync(tomlPath, tomlContent);
  }

  private syncAgyMcpConfig(): void {
    const geminiDir = join(homedir(), ".gemini");
    mkdirSync(geminiDir, { recursive: true });

    const mcpServers: Record<string, unknown> = {};
    for (const server of this.settings.mcpServers) {
      if (server.enabled) {
        mcpServers[server.name] = this.processMcpServer(server);
      }
    }

    const settingsPath = join(geminiDir, "settings.json");
    let existing: Record<string, unknown> = {};
    try {
      existing = JSON.parse(readFileSync(settingsPath, "utf-8"));
    } catch { /* file missing or malformed — start fresh */ }

    const merged = {
      ...existing,
      admin: {
        ...(existing.admin as Record<string, unknown> | undefined ?? {}),
        mcp: { enabled: true },
      },
      mcpServers,
    };

    writeFileSync(settingsPath, `${JSON.stringify(merged, null, 2)}\n`);
  }

  private messagesToCliPrompt(messages: LLMMessage[]): string {
    return messages
      .map((message) => {
        const content = this.contentToCliText(message.content);
        const label =
          message.role === "system"
            ? "System"
            : message.role === "assistant"
              ? "Assistant"
              : "User";
        return `${label}:\n${content}`;
      })
      .join("\n\n---\n\n");
  }

  private contentToCliText(content: string | LLMContentPart[]): string {
    if (typeof content === "string") return content;
    return content
      .map((part) => {
        if (part.type === "text") return part.text;
        
        try {
          const tmpDir = join(homedir(), ".incurator", "tmp_images");
          if (!existsSync(tmpDir)) {
            mkdirSync(tmpDir, { recursive: true });
          }
          let ext = part.mimeType.split("/")[1] || "png";
          if (ext === "jpeg") ext = "jpg";
          const filepath = join(tmpDir, `img_${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`);
          writeFileSync(filepath, Buffer.from(part.data, "base64"));
          // Provide an explicit instruction to the agent so it knows it should look at this file
          return `[Attached image saved to: ${filepath} - Please read/view this file to see the image]`;
        } catch (e) {
          return `[Attached image ${part.mimeType} omitted from CLI fallback (save failed: ${e instanceof Error ? e.message : String(e)})]`;
        }
      })
      .join("\n");
  }

  private cleanCliOutput(provider: LLMProvider, stdout: string): string {
    const trimmed = stdout.trim();
    if (provider !== "openai") return trimmed;

    const lines = trimmed
      .split(/\r?\n/)
      .filter((line) => {
        const value = line.trim();
        return (
          value.length > 0 &&
          value !== "codex" &&
          value !== "tokens used" &&
          !/^[\d,]+$/.test(value) &&
          !value.startsWith("202")
        );
      });

    return lines.join("\n").trim();
  }

  /**
   * Edit text using the LLM — returns only the modified text.
   */
  async editText(
    originalText: string,
    instruction: string,
    onChunk?: (chunk: StreamChunk) => void
  ): Promise<string> {
    const messages: LLMMessage[] = [
      {
        role: "system",
        content: `You are an expert text editor embedded in Obsidian. The user will give you a piece of text and an editing instruction.

RULES:
- Apply the instruction to the text and return ONLY the modified text.
- Do NOT include any explanation, preamble, or markdown code fences.
- Preserve the original formatting (markdown, indentation) unless the instruction says otherwise.
- If the instruction is unclear, make your best judgment.`,
      },
      {
        role: "user",
        content: `Original text:
\`\`\`
${originalText}
\`\`\`

Instruction: ${instruction}`,
      },
    ];

    if (onChunk && this.settings.streamingEnabled) {
      return this.streamChat(messages, onChunk);
    }
    return this.complete(messages);
  }
}
