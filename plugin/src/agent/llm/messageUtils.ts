import type { ToolPolicy } from "../../context/promptRegistry";
import type {
  LLMContentPart,
  LLMMessage,
  LLMProvider,
  StreamChunk,
} from "../../types";

export function shouldInjectMcpTools(
  toolPolicy: ToolPolicy,
  hasMcpManager: boolean,
  useCli: boolean
): boolean {
  if (toolPolicy === "none") return false;
  if (useCli) return false;
  return hasMcpManager;
}

function messageHasContent(content: string | LLMContentPart[]): boolean {
  if (typeof content === "string") return content.trim().length > 0;
  return Array.isArray(content) && content.length > 0;
}

export function sanitizeOpenAIMessages(messages: LLMMessage[]): LLMMessage[] {
  return messages.filter((message) => {
    if (message.role !== "assistant") return true;
    const hasTools = Array.isArray(message.tool_calls) && message.tool_calls.length > 0;
    return messageHasContent(message.content) || hasTools;
  });
}

export function normalizeOpenAIContent(
  message: LLMMessage,
  toContent: (content: string | LLMContentPart[]) => string | Array<Record<string, unknown>>
): string | Array<Record<string, unknown>> | null {
  if (messageHasContent(message.content)) return toContent(message.content);
  if (message.role === "assistant" || message.role === "tool") return "";
  return null;
}

export function mapOpenAIFinishReason(
  finishReason: string | null | undefined
): Pick<StreamChunk, "done" | "finishReason" | "truncated"> {
  if (finishReason === "length") {
    return { done: true, finishReason: "length", truncated: true };
  }
  if (finishReason === "stop") return { done: true, finishReason: "stop" };
  if (finishReason === "tool_calls") return { done: true, finishReason: "tool_calls" };
  if (finishReason === "content_filter") {
    return { done: true, finishReason: "content_filter" };
  }
  if (finishReason) return { done: true, finishReason: "stop" };
  return { done: false };
}

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
    return raw.length > 600 ? `${raw.slice(0, 600)}\n…` : raw;
  }
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return raw.length > 600 ? `${raw.slice(0, 600)}\n…` : raw;
    }
    const compact = {
      ok: parsed.ok,
      question: parsed.question,
      route: parsed.route,
      trace_id: parsed.trace_id,
      fallback: parsed.fallback,
      error: parsed.error,
      prompt_trace_ids: parsed.prompt_trace_ids,
      warnings: parsed.warnings,
      trace: parsed.trace,
    };
    return JSON.stringify(compact, null, 2);
  } catch {
    return raw.length > 600 ? `${raw.slice(0, 600)}\n…` : raw;
  }
}

function stripAnsi(text: string): string {
  return text.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "");
}

export function isAntigravityStatusLine(line: string): boolean {
  const value = stripAnsi(line).trim();
  if (!value) return true;
  if (/^[⠁-⣿◐◓◑◒|/\\\-]+\s*$/.test(value)) return true;
  if (
    /^[-–—•*]?\s*(thinking|processing|generating|starting|loading|initializing|connecting|authenticating|requesting|waiting)\b/i.test(
      value
    )
  ) {
    return true;
  }
  if (
    /^[-–—•*]?\s*(mcp servers? available|using tool|running tool|calling tool|tool use|tool result)\b/i.test(
      value
    )
  ) {
    return true;
  }
  if (
    /^[-–—•*]?\s*(antigravity|gemini)\b.*\b(generating|thinking|processing)\b/i.test(
      value
    )
  ) {
    return true;
  }
  return false;
}

export function extractAntigravityAnswerFromStderr(stderr: string): string {
  return stderr
    .replace(/\r/g, "\n")
    .split("\n")
    .map((line) => stripAnsi(line).trim())
    .filter((line) => line && !isAntigravityStatusLine(line))
    .join("\n")
    .trim();
}
