import type { ToolPolicy } from "../../context/promptRegistry";
import type {
  LLMContentPart,
  LLMMessage,
  LLMProvider,
  StreamChunk,
} from "../../types";

/**
 * MCP tool injection. Exhaustive over {@link ToolPolicy} so a future policy
 * value is a compile error rather than a silent grant. "local-only" (the
 * popover since v0.41.0) refuses MCP exactly like "none" — its zero-MCP
 * guarantee is unchanged; see PLUGIN_SCHEMA §13.5/§13.7.
 */
export function shouldInjectMcpTools(
  toolPolicy: ToolPolicy,
  hasMcpManager: boolean,
  useCli: boolean
): boolean {
  switch (toolPolicy) {
    case "none":
    case "local-only":
      return false;
    case "auto":
      if (useCli) return false;
      return hasMcpManager;
    default: {
      const exhaustive: never = toolPolicy;
      return exhaustive;
    }
  }
}

/**
 * Whether a surface is EPHEMERAL for CLI-sandbox purposes: read-only, no
 * filesystem roots, no native CLI tools. Both tool-free (`"none"`) and
 * local-tools-only (`"local-only"`) surfaces qualify — the local PDF reader is
 * plugin-executed and grants the CLI agent nothing, so it must not relax the
 * v0.23.0 sandbox. Exhaustive so a new policy value cannot silently fail open.
 */
export function isEphemeralToolPolicy(toolPolicy: ToolPolicy): boolean {
  switch (toolPolicy) {
    case "none":
    case "local-only":
      return true;
    case "auto":
      return false;
    default: {
      const exhaustive: never = toolPolicy;
      return exhaustive;
    }
  }
}

/**
 * Local (plugin-executed) tool injection — currently the read-only PDF page
 * reader. CLI providers are excluded by a locked decision so the v0.23.0
 * sandbox contract stays untouched.
 */
export function shouldInjectLocalTools(
  toolPolicy: ToolPolicy,
  hasLocalRunner: boolean,
  useCli: boolean
): boolean {
  switch (toolPolicy) {
    case "none":
      return false;
    case "auto":
    case "local-only":
      if (useCli) return false;
      return hasLocalRunner;
    default: {
      const exhaustive: never = toolPolicy;
      return exhaustive;
    }
  }
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

/** Phrases providers actually emit when they refuse for quota or capacity.
 *
 *  **Phrases, deliberately — never bare words.** This list used to contain bare
 *  `"capacity"` and `"quota"`, which are ordinary vocabulary ("register
 *  capacity", "model capacity", "cache capacity"), and the CLI path matched it
 *  against the model's own answer. Every answer that used one of those words was
 *  discarded and reported as a quota failure while the provider was healthy.
 *
 *  The asymmetry decides the design: a false positive **destroys an answer the
 *  user already paid for**, while a false negative costs only the friendly
 *  "switch provider" hint — the raw CLI error is surfaced either way. So match
 *  narrowly. Mirrors the backend's `_is_capacity_error` (`llm.py`), extended
 *  with the API-provider phrasings the plugin also sees. */
const QUOTA_PHRASES = [
  "no capacity available",
  "model_capacity_exhausted",
  "quota_exhausted",
  "resource_exhausted",
  "terminalquotaerror",
  "exhausted your capacity",
  "individual quota reached",
  "quota reached",
  "quota exceeded",
  "out of quota",
  "insufficient balance",
  "insufficient_quota",
  "rate limit",
  "rate_limit",
  "too many requests",
];

/** Word-bounded, which does two jobs at once: `14293 tokens` is not an HTTP 429,
 *  and neither is a typed Curator id like `ATM-429abc12` or `SPAN-429fffff`.
 *
 *  The backend guards the same hazard by stripping `\b[A-Z]{3,4}-[0-9a-fA-F]{8}\b`
 *  before matching (`ingest_worker.py`, after a span id reading `SPAN-13850308`
 *  made a permanent failure look transient once in every 15 runs). That strip is
 *  **redundant here and is deliberately not duplicated**: an id's hex run always
 *  flanks its digits with hex characters, so `\b429\b` can never fire inside
 *  one. A strip would be code no test exercises, which is worse than absent —
 *  it would invite someone to weaken this boundary believing the strip covers
 *  them. The typed-id tests below therefore pin the guarantee, not the
 *  mechanism. */
const HTTP_429_RE = /\b429\b/;

export function isQuotaErrorMessage(message: string): boolean {
  const value = message.toLowerCase();
  return QUOTA_PHRASES.some((phrase) => value.includes(phrase)) || HTTP_429_RE.test(value);
}

/** What may be used as evidence that a CLI run failed on quota.
 *
 *  **Never the model's answer.** `isQuotaErrorMessage` is a keyword matcher, and
 *  the words it looks for — "capacity", "quota", "429", "rate limit" — are
 *  ordinary vocabulary in CUDA and computer-vision writing. The CLI call site
 *  used to pass `stderr + "\n" + stdout`, where stdout IS the answer, so a
 *  complete and already-paid-for answer was thrown away and reported to the user
 *  as "quota or capacity is currently unavailable" while their quota was fine.
 *
 *  Stdout counts only when the run produced no answer at all, because some CLIs
 *  print the refusal there instead of on stderr. */
export function quotaEvidenceFor(
  stderr: string,
  stdout: string,
  answer: string
): string {
  return answer.trim().length === 0 ? `${stderr}\n${stdout}` : stderr;
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
