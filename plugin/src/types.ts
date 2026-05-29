
export interface ZoteroImportProfile {
  name: string;
  templatePath: string;
  outputFolder: string;
  outputSubfolder: string;
  outputFilename: string;
  assetFolder: string;
  assetSubfolder: string;
  bibliographyStyle: string;
  /** @deprecated use assetFolder + assetSubfolder */
  imageFolder?: string;
}

export interface FileScrollPosition {
  scroll: number;
  line: number;
  ch: number;
  updatedAt?: number;
}

export interface LastMarkdownScrollPosition extends FileScrollPosition {
  path: string;
}

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
  tier: "flash" | "think" | "stable" | "preview" | "legacy";
  supportsVision: boolean;
  contextWindow?: number;
}

export type ModelCatalogue = Partial<Record<LLMProvider, ModelOption[]>>;

// ─── Session Data (device-local, stored in sessions.json) ───────
export interface SessionData {
  chatSessions: ChatSession[];
  activeChatSessionId?: string;
  deletedSessionIds?: string[];
}

export const DEFAULT_SESSION_DATA: SessionData = {
  chatSessions: [],
  activeChatSessionId: undefined,
  deletedSessionIds: [],
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
  incuratorMcpCommand: string;
  incuratorMcpArgs: string[];
  incuratorDefaultDestination: string;
  incuratorDefaultImportMode: "copy" | "reference";
  incuratorStatusPolling: boolean;
  zoteroBasePath: string;
  zoteroProfiles: ZoteroImportProfile[];
  lastMarkdownScrollPosition?: LastMarkdownScrollPosition;
  fileScrollPositions?: Record<string, FileScrollPosition>;
}

export const DEFAULT_SETTINGS: PluginSettings = {
  zoteroBasePath: "~/Zotero",
  zoteroProfiles: [],
  provider: "antigravity",
  model: "",
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
  incuratorMcpCommand: "wiki",
  incuratorMcpArgs: ["mcp"],
  incuratorDefaultDestination: "04_Resources",
  incuratorDefaultImportMode: "reference",
  incuratorStatusPolling: true,
  fileScrollPositions: {},
};

export function getModelOption(
  catalogue: ModelCatalogue,
  provider: LLMProvider,
  model: string
): ModelOption | undefined {
  return catalogue[provider]?.find((option) => option.id === model);
}

export function getDefaultModel(
  catalogue: ModelCatalogue,
  provider: LLMProvider
): string {
  const options = catalogue[provider] || [];
  return (
    options.find((option) => option.tier === "flash")?.id ||
    options.find((option) => option.tier === "stable")?.id ||
    options[0]?.id ||
    ""
  );
}

export function modelSupportsVision(
  catalogue: ModelCatalogue,
  provider: LLMProvider,
  model: string
): boolean {
  const option = getModelOption(catalogue, provider, model);
  return option ? option.supportsVision === true : true;
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
  fileHash?: string;
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
  fileHash?: string;
}

export type IncuratorSourceState =
  | "unknown"
  | "untracked"
  | "l1_ready"
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

export interface ExternalPdfState {
  docId: string;
  name: string;
  path?: string;
  zoom: number;
  darkMode: boolean;
  tocOpen: boolean;
  currentPage: number;
  zoteroAttachmentKey?: string;
  targetAnnotationKey?: string;
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

// ─── Curator Query (v0.2.1) ─────────────────────────────────────
export interface CuratorQueryTrace {
  matched_concepts: string[];
  source_ids: number[];
  source_paths: string[];
  section_ids?: string[];
  latency_ms: number;
  l3_complete: boolean;
}

export interface CuratorQueryResult {
  ok: boolean;
  answer?: string;
  exhibition_id?: string;
  cache_hit?: boolean;
  fallback?: string;
  fallback_hits?: Array<{ path?: string; title?: string; score?: number; snippet?: string }>;
  question: string;
  trace?: CuratorQueryTrace;
  error?: string;
}

export interface PromoteExhibitionResult {
  ok: boolean;
  exhibition_id?: string;
  promoted_to?: string;
  error?: string;
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
