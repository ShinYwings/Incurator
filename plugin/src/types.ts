
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
export type LLMProvider = "antigravity" | "claude" | "openai" | "ollama" | "deepseek";
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
  supportsVision: boolean;

  contextWindow?: number;
  // Reasoning/effort levels the underlying CLI accepts for this model.
  // Empty/undefined means the model has no selectable effort dimension.
  efforts?: string[];
  defaultEffort?: string;
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
  agentEffort: string;
  antigravityPrintTimeoutSec: number;
  providerUsage: Record<LLMProvider, ProviderUsage>;
  diffMode: "inline" | "side-by-side";
  streamingEnabled: boolean;
  quickQueryEnabled: boolean;
  mcpServers: MCPServerConfig[];
  maxContextLength: number;
  deepseekApiKey: string;
  ollamaHost: string;
  pdfCaptureMode: "text" | "image" | "both";
  pdfWindowRadius: number;
  pdfOutlineEnabled: boolean;
  pdfRagEnabled: boolean;
  pdfRagTopK: number;
  pdfVisionFallback: boolean;
  pdfFullDocumentIndex: boolean;
  incuratorEnabled: boolean;
  incuratorBackendCommand: string;
  incuratorBackendArgs: string[];
  incuratorRepoPath: string;
  incuratorDefaultDestination: string;
  incuratorDefaultImportMode: "copy" | "reference";
  /** Vault-relative base folder for images extracted from non-Zotero add-source
   *  PDFs; each PDF gets a filename subfolder, while "" lets the backend default
   *  to 05_Assets/<slug>/ (PLUGIN_SCHEMA §1.1). */
  incuratorPdfAssetFolder: string;
  incuratorStatusPolling: boolean;
  // Cross-device knowledge auto-sync over Syncthing (one-writer-per-file).
  // Optional + read with `!== false` so older saved settings default to enabled.
  autoSyncEnabled?: boolean;     // master switch for all auto-sync behavior
  autoSyncOnLoad?: boolean;      // run autosync once when Obsidian opens
  autoSyncWatch?: boolean;       // watch .curator/sync for peer files (desktop only)
  autoSyncNotify?: boolean;      // toast only when peers actually delivered changes
  zoteroBasePath: string;
  zoteroProfiles: ZoteroImportProfile[];
  recentZoteroItems: string[];
  lastMarkdownScrollPosition?: LastMarkdownScrollPosition;
  fileScrollPositions?: Record<string, FileScrollPosition>;
}

export const DEFAULT_SETTINGS: PluginSettings = {
  zoteroBasePath: "~/Zotero",
  zoteroProfiles: [],
  recentZoteroItems: [],
  provider: "antigravity",
  model: "",
  chatMode: "chat",
  codexReasoningEffort: "medium",
  claudeEffort: "medium",
  agentEffort: "",
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
    ollama: {
      requests: 0,
      inputTokens: 0,
      cachedInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0,
    },
    deepseek: {
      requests: 0,
      inputTokens: 0,
      cachedInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0,
    },
  },
  deepseekApiKey: "",
  ollamaHost: "http://localhost:11434",
  diffMode: "inline",
  streamingEnabled: true,
  quickQueryEnabled: true,
  mcpServers: [],
  maxContextLength: 128000,
  pdfCaptureMode: "text",
  pdfWindowRadius: 1,
  pdfOutlineEnabled: true,
  pdfRagEnabled: true,
  pdfRagTopK: 5,
  pdfVisionFallback: true,
  pdfFullDocumentIndex: true,
  incuratorEnabled: true,
  incuratorBackendCommand: "wiki",
  incuratorBackendArgs: [],
  incuratorRepoPath: "",
  incuratorDefaultDestination: "04_Resources",
  incuratorDefaultImportMode: "reference",
  incuratorPdfAssetFolder: "",
  incuratorStatusPolling: true,
  autoSyncEnabled: true,
  autoSyncOnLoad: true,
  autoSyncWatch: true,
  autoSyncNotify: true,
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
  return options[0]?.id || "";
}

export function modelSupportsVision(
  catalogue: ModelCatalogue,
  provider: LLMProvider,
  model: string
): boolean {
  const option = getModelOption(catalogue, provider, model);
  if (option) return option.supportsVision === true;
  // Unknown Ollama models default to no vision to avoid sending images to text-only models
  if (provider === "ollama") {
    const lower = model.toLowerCase();
    if (lower.includes("vision") || lower.includes("llava") || lower.includes("minicpm-v") || lower.includes("pixtral") || lower.includes("-vl")) {
      return true;
    }
    return false;
  }
  return true;
}

// ─── Chat Messages ──────────────────────────────────────────────
export interface ContextRef {
  type: "file" | "selection" | "line-range" | "pdf-page" | "text" | "image";
  label: string;
  content: string;
  /** Keep this context chip after sending and refresh it from the source tab/file. */
  isPinned?: boolean;
  /** When false, keep the chip visible but exclude it from model prompts. */
  includeInPrompt?: boolean;
  /** Original view type for pinned open-tab context. */
  sourceViewType?: string;
  /** Base64-encoded image for PDF page captures */
  imageBase64?: string;
  fileHash?: string;
  backendStatus?: IncuratorSourceStatus;
  windowPages?: PdfWindowPage[];
  outline?: PdfOutlineItem[];
  pageLabels?: string[];
  ragHits?: PdfRagHit[];
  textQuality?: PdfTextQuality;
  isScannedLike?: boolean;
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  pageNum?: number;
  zoteroAttachmentKey?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  name?: string;
  tool_calls?: Array<{
    id: string;
    type: "function";
    function: { name: string; arguments: string };
  }>;
  tool_call_id?: string;
  timestamp: number;
  contextRefs?: ContextRef[];
  /** For streaming: is the message still being received? */
  isStreaming?: boolean;
  appliedEdits?: boolean;
  /** True once this message's edit diff was auto-opened, so it never re-opens. */
  diffAutoOpened?: boolean;
  revertData?: { filepath: string; originalContent: string | null }[];
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
  /** PDF PageLabels array, 0-based physical page index -> printed label. */
  pageLabels?: string[];
  text: string;
  imageBase64?: string;
  selectedImageBase64?: string;
  windowPages?: PdfWindowPage[];
  outline?: PdfOutlineItem[];
  textQuality?: PdfTextQuality;
  ragHits?: PdfRagHit[];
  isScannedLike?: boolean;
  documentId?: string;
  documentName?: string;
  filePath?: string;
  fileHash?: string;
  zoteroAttachmentKey?: string;
}

export type IncuratorSourceState =
  | "unknown"
  | "untracked"
  | "l1_ready"
  | "l2_ready"
  | "l3_ready"
  | "l4_ready"
  | "queued"
  | "running"
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
  cache_hit?: boolean;
  fallback?: string;
  fallback_hits?: Array<{ path?: string; title?: string; score?: number; snippet?: string }>;
  question: string;
  input_language?: string;
  english_query?: string;
  final_output_language?: string;
  trace?: CuratorQueryTrace;
  error?: string;
  // v0.3.1 curation-native trace fields (additive; omitted by legacy responses).
  route?: "local" | "global" | "explore" | "source-section";
  trace_id?: string;
  prompt_trace_ids?: string[];
  source_span_ids?: string[];
  community_report_ids?: string[];
  synthesis_node_ids?: string[];
  memory_path_ids?: string[];
  insight_candidate_ids?: string[];
  warnings?: string[];
}

// v0.3.1: sessionless promotion of a Q&A answer into 02_Wiki (no Exhibition file).
export interface PromoteAnswerResult {
  ok: boolean;
  promoted_to?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// v0.3.1 curation-native trace/insight payloads (PLUGIN_SCHEMA §10–11)
// ---------------------------------------------------------------------------

export interface IncuratorPromptTrace {
  ok: boolean;
  traceId?: string;
  promptId?: string;
  promptVersion?: string;
  family?: string;
  validatorStatus?: "ok" | "repaired" | "failed" | "pending";
  validatorErrors?: string[];
  modelProvider?: string;
  modelName?: string;
  error?: string;
}

export interface IncuratorEvidenceTrace {
  route: string;
  traceId: string;
  promptTraceIds: string[];
  sourceSpanIds: string[];
  communityReportIds: string[];
  memoryPathIds: string[];
  insightCandidateIds: string[];
}

export interface IncuratorCuratePlan {
  ok: boolean;
  planId?: string;
  workspaceId?: string;
  curateSpecHash?: string;
  route?: string;
  promptProfile?: string;
  selectedSources?: string[];
  excludedSources?: Array<{ path: string; reason: string }>;
  allowedModes?: string[];
  knownGaps?: string[];
  validationErrors?: string[];
  error?: string;
}

export interface IncuratorInsightCandidate {
  id: string;
  classification:
    | "correction"
    | "contradiction"
    | "derived_insight"
    | "style_only"
    | "promotion_request"
    | "ambiguous";
  statement: string;
  status: "pending" | "accepted" | "rejected" | "promoted" | "needs_review";
  affectedNodeIds: string[];
  confidence: number;
}

export interface IncuratorInsightListResult {
  ok: boolean;
  candidates: IncuratorInsightCandidate[];
  error?: string;
}

export interface IncuratorInsightPromoteResult {
  ok: boolean;
  insightId?: string;
  promotedTo?: string;
  error?: string;
}

export interface IncuratorSynthesisSummary {
  id: string;
  title: string;
  confidence: number;
  sourceSpanIds: string[];
  communityReportIds: string[];
  promptRunId?: string;
  updatedAt?: string;
}

export interface IncuratorSynthesisListResult {
  ok: boolean;
  synthesis: IncuratorSynthesisSummary[];
  error?: string;
}

export interface IncuratorSynthesisAuditResult {
  ok: boolean;
  audit?: {
    ok: boolean;
    kind: "synthesis" | "report" | "answer";
    id: string;
    synthesis?: Record<string, unknown>;
    community_reports?: unknown[];
    entities?: unknown[];
    relations?: unknown[];
    knowledge_units?: unknown[];
    source_spans?: unknown[];
    prompt_runs?: unknown[];
    query_trace?: unknown;
    dependency_warnings?: string[];
    warnings?: string[];
  };
  synthesisId?: string;
  error?: string;
}

export interface GitStatusResult {
  ok: boolean;
  repo?: {
    is_repo?: boolean;
    root?: string;
    branch?: string;
    upstream?: string;
    ahead?: number;
    behind?: number;
    remote_url?: string;
  };
  working_tree?: {
    clean?: boolean;
    staged?: number;
    unstaged?: number;
    untracked?: number;
    conflicted?: number;
  };
  warnings?: string[];
  error?: string;
  message?: string;
}

export interface GitHistoryCommit {
  hash: string;
  author?: string;
  date?: string;
  subject: string;
  patch?: string;
}

export interface GitHistoryResult {
  ok: boolean;
  file_path?: string;
  query_excerpt?: string;
  exact_match?: boolean;
  commits?: GitHistoryCommit[];
  error?: string;
  message?: string;
}

export interface GitPushResult {
  ok: boolean;
  branch?: string;
  upstream?: string;
  stdout?: string;
  stderr?: string;
  error?: string;
  message?: string;
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
  role: "user" | "assistant" | "system" | "tool";
  content: string | LLMContentPart[];
  name?: string;
  tool_calls?: Array<{
    id: string;
    type: "function";
    function: { name: string; arguments: string };
  }>;
  tool_call_id?: string;
}

export type LLMContentPart =
  | { type: "text"; text: string }
  | { type: "image"; mimeType: string; data: string };

export type StreamEventType = "text" | "thinking" | "status" | "tool" | "done";

export interface StreamChunk {
  text: string;
  done: boolean;
  reasoning_content?: string;
  eventType?: StreamEventType;
  status?: string;
  toolName?: string;
  tool_calls?: Array<{
    index: number;
    id?: string;
    type?: "function";
    function?: { name?: string; arguments?: string };
  }>;
}
