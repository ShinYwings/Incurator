// ─── LLM Provider ───────────────────────────────────────────────
export type LLMProvider = "antigravity" | "claude" | "openai";
export type ChatMode = "chat" | "plan";
export type CodexReasoningEffort = "low" | "medium" | "high" | "xhigh";
export type ClaudeEffort = "low" | "medium" | "high" | "xhigh" | "max";

export interface ProviderUsage {
  requests: number;
  inputTokens: number;
  cachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
  lastUsedAt?: number;
}

export interface ModelOption {
  id: string;
  label: string;
  tier: "stable" | "preview" | "legacy";
  supportsVision: boolean;
}

// ─── Session Data (device-local, stored in sessions.json) ───────
export interface SessionData {
  chatSessions: ChatSession[];
  activeChatSessionId?: string;
}

export const DEFAULT_SESSION_DATA: SessionData = {
  chatSessions: [],
  activeChatSessionId: undefined,
};

// ─── Plugin Settings ────────────────────────────────────────────
export interface MCPServerConfig {
  name: string;
  command: string;
  args: string[];
  env?: Record<string, string>;
  enabled: boolean;
}

export interface PluginSettings {
  provider: LLMProvider;
  model: string;
  chatMode: ChatMode;
  codexReasoningEffort: CodexReasoningEffort;
  claudeEffort: ClaudeEffort;
  antigravityPrintTimeoutSec: number;
  providerUsage: Record<LLMProvider, ProviderUsage>;
  diffMode: "inline" | "side-by-side";
  streamingEnabled: boolean;
  mcpServers: MCPServerConfig[];
  maxContextLength: number;
  pdfCaptureMode: "text" | "image" | "both";
  pdfWindowRadius: number;
  pdfOutlineEnabled: boolean;
  pdfRagEnabled: boolean;
  pdfRagTopK: number;
  pdfVisionFallback: boolean;
  pdfFullDocumentIndex: boolean;
  incuratorEnabled: boolean;
  incuratorDefaultDestination: string;
  incuratorDefaultImportMode: "copy" | "reference";
  incuratorStatusPolling: boolean;
  fileScrollPositions?: Record<string, { scroll: number; line: number; ch: number }>;
}

export const DEFAULT_SETTINGS: PluginSettings = {
  provider: "antigravity",
  model: "gemini-3.5-flash",
  chatMode: "chat",
  codexReasoningEffort: "medium",
  claudeEffort: "medium",
  antigravityPrintTimeoutSec: 300,
  providerUsage: {
    antigravity: {
      requests: 0,
      inputTokens: 0,
      cachedInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0,
    },
    claude: {
      requests: 0,
      inputTokens: 0,
      cachedInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0,
    },
    openai: {
      requests: 0,
      inputTokens: 0,
      cachedInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0,
    },
  },
  diffMode: "inline",
  streamingEnabled: true,
  mcpServers: [],
  maxContextLength: 128000,
  pdfCaptureMode: "both",
  pdfWindowRadius: 1,
  pdfOutlineEnabled: true,
  pdfRagEnabled: true,
  pdfRagTopK: 5,
  pdfVisionFallback: true,
  pdfFullDocumentIndex: true,
  incuratorEnabled: true,
  incuratorDefaultDestination: "04_Resources",
  incuratorDefaultImportMode: "reference",
  incuratorStatusPolling: true,
  fileScrollPositions: {},
};

export const DEFAULT_MODELS: Record<LLMProvider, string> = {
  antigravity: "gemini-3.5-flash",
  claude: "claude-sonnet-4-5-20250929",
  openai: "gpt-5.5",
};

export const MODEL_OPTIONS: Record<LLMProvider, ModelOption[]> = {
  antigravity: [
    // ── Stable (Antigravity 3.x GA) ───────────────────────────────
    {
      id: "gemini-3.5-flash",
      label: "Antigravity 3.5 Flash",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "gemini-3.1-pro",
      label: "Antigravity 3.1 Pro",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "gemini-3-flash",
      label: "Antigravity 3 Flash",
      tier: "stable",
      supportsVision: true,
    },
    // ── Preview ─────────────────────────────────────────────────
    {
      id: "gemini-3.1-pro-preview",
      label: "Antigravity 3.1 Pro Preview",
      tier: "preview",
      supportsVision: true,
    },
    {
      id: "gemini-3.1-flash-lite-preview",
      label: "Antigravity 3.1 Flash Lite Preview",
      tier: "preview",
      supportsVision: true,
    },
    // ── Legacy ───────────────────────────────────────────────────
    {
      id: "gemini-2.5-pro",
      label: "Antigravity 2.5 Pro (Legacy)",
      tier: "legacy",
      supportsVision: true,
    },
    {
      id: "gemini-2.5-flash",
      label: "Antigravity 2.5 Flash (Legacy)",
      tier: "legacy",
      supportsVision: true,
    },
    {
      id: "gemma-4-31b-it",
      label: "Gemma 4 31B IT",
      tier: "stable",
      supportsVision: false,
    },
    {
      id: "gemma-4-26b-a4b-it",
      label: "Gemma 4 26B A4B IT",
      tier: "stable",
      supportsVision: false,
    },
  ],
  claude: [
    {
      id: "claude-sonnet-4-5-20250929",
      label: "Claude Sonnet 4.5",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "claude-opus-4-1-20250805",
      label: "Claude Opus 4.1",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "claude-haiku-4-5-20251001",
      label: "Claude Haiku 4.5",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "claude-sonnet-4-20250514",
      label: "Claude Sonnet 4",
      tier: "legacy",
      supportsVision: true,
    },
    {
      id: "claude-3-7-sonnet-20250219",
      label: "Claude Sonnet 3.7",
      tier: "legacy",
      supportsVision: true,
    },
  ],
  openai: [
    {
      id: "gpt-5.5",
      label: "GPT-5.5",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "gpt-5.4",
      label: "GPT-5.4",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "gpt-5.4-mini",
      label: "GPT-5.4 Mini",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "gpt-5.3-codex",
      label: "GPT-5.3 Codex",
      tier: "stable",
      supportsVision: true,
    },
    {
      id: "gpt-5.2",
      label: "GPT-5.2",
      tier: "stable",
      supportsVision: true,
    },
  ],
};

export function getModelOption(
  provider: LLMProvider,
  model: string
): ModelOption | undefined {
  return MODEL_OPTIONS[provider].find((option) => option.id === model);
}

export function modelSupportsVision(
  provider: LLMProvider,
  model: string
): boolean {
  return getModelOption(provider, model)?.supportsVision === true;
}

// ─── Chat Messages ──────────────────────────────────────────────
export interface ContextRef {
  type: "file" | "selection" | "line-range" | "pdf-page" | "text" | "image";
  label: string;
  content: string;
  /** Keep this context chip after sending and refresh it from the source tab/file. */
  isPinned?: boolean;
  /** Original view type for pinned open-tab context. */
  sourceViewType?: string;
  /** Base64-encoded image for PDF page captures */
  imageBase64?: string;
  backendStatus?: IncuratorSourceStatus;
  windowPages?: PdfWindowPage[];
  outline?: PdfOutlineItem[];
  ragHits?: PdfRagHit[];
  textQuality?: PdfTextQuality;
  isScannedLike?: boolean;
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  pageNum?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  contextRefs?: ContextRef[];
  /** For streaming: is the message still being received? */
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

// ─── PDF Context ────────────────────────────────────────────────
export type PdfTextSource = "pdfjs" | "obsidian-text-layer" | "dom" | "none";

export interface PdfTextQuality {
  score: number;
  charCount: number;
  wordCount: number;
  lineCount: number;
  brokenCharRatio: number;
  whitespaceRatio: number;
  isScannedLike: boolean;
  source: PdfTextSource;
  reason?: string;
}

export interface PdfWindowPage {
  pageNum: number;
  text: string;
  textQuality?: PdfTextQuality;
}

export interface PdfOutlineItem {
  title: string;
  pageNum?: number;
  level: number;
}

export interface PdfRagHit {
  pageNum: number;
  score: number;
  snippet: string;
  sectionTitle?: string;
}

export interface PdfPageContext {
  pageNum: number;
  pageCount?: number;
  text: string;
  imageBase64?: string;
  windowPages?: PdfWindowPage[];
  outline?: PdfOutlineItem[];
  textQuality?: PdfTextQuality;
  ragHits?: PdfRagHit[];
  isScannedLike?: boolean;
  documentId?: string;
  documentName?: string;
  filePath?: string;
}

export type IncuratorSourceState =
  | "unknown"
  | "untracked"
  | "queued"
  | "running"
  | "indexed"
  | "curated"
  | "stale"
  | "missing"
  | "moved"
  | "hash_drift"
  | "moved_and_hash_drift"
  | "error";

export interface IncuratorSourceStatus {
  state: IncuratorSourceState;
  sourceId?: number;
  sourcePath?: string;
  destinationRelpath?: string;
  contextId?: string;
  pageCount?: number;
  currentPath?: string;
  candidatePath?: string;
  requiresRebind?: boolean;
  message?: string;
  updatedAt?: number;
  /** Which pipeline layer is currently running, e.g. "l1", "l2", "l3", "l4" */
  runningLayer?: string;
}

// ─── Active Context ─────────────────────────────────────────────
export interface ActiveContext {
  /** Currently active file path (vault-relative) */
  filePath?: string;
  /** Absolute filesystem path to the active file */
  absolutePath?: string;
  /** Full file content */
  fileContent?: string;
  /** Type of active view */
  viewType: "markdown" | "pdf" | "canvas" | "other";
  /** Human-readable active view label, useful when there is no vault file. */
  displayName?: string;
  /** Selected text in editor */
  selectedText?: string;
  /** Selection line range */
  selectionStart?: number;
  selectionEnd?: number;
  /** PDF-specific context */
  pdfPage?: PdfPageContext;
  /** Currently open workspace tabs/leaves */
  openTabs?: OpenTabContext[];
}

export interface OpenTabContext {
  label: string;
  viewType: string;
  filePath?: string;
  isActive: boolean;
  content?: string;
  selectedText?: string;
  pdfPage?: PdfPageContext;
}

// ─── MCP Protocol Types ─────────────────────────────────────────
export interface MCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export interface MCPToolResult {
  content: Array<{ type: string; text?: string }>;
  isError?: boolean;
}

// ─── LLM Request/Response ───────────────────────────────────────
export interface LLMMessage {
  role: "user" | "assistant" | "system";
  content: string | LLMContentPart[];
}

export type LLMContentPart =
  | { type: "text"; text: string }
  | { type: "image"; mimeType: string; data: string };

export type StreamEventType = "text" | "thinking" | "status" | "tool" | "done";

export interface StreamChunk {
  text: string;
  done: boolean;
  eventType?: StreamEventType;
  status?: string;
  toolName?: string;
}
