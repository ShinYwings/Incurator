import { logger } from "../utils/logger";
import type {
  CuratorQueryResult,
  CuratorContextPack,
  CuratorContextFeedbackResult,
  CuratorFeedbackType,
  IncuratorCuratePlan,
  IncuratorInsightListResult,
  IncuratorInsightPromoteResult,
  IncuratorPromptTrace,
  IncuratorSynthesisAuditResult,
  IncuratorSynthesisListResult,
  IncuratorSourceStatus,
  IncuratorSourceState,
  GitHistoryResult,
  GitPushResult,
  GitStatusResult,
  PdfOutlineItem,
  PdfRagHit,
  PdfWindowPage,
  PluginSettings,
  PromoteAnswerResult,
} from "../types";
import localBuildManifest from "../generated/buildManifest.json";
import { joinVaultPath, resolveProfileAssetSpec } from "../zotero/assetLocalization";
import { sanitizePathSegment } from "../zotero/templateRenderer";

type BackendJsonRunner = (cmdArgs: string[]) => Promise<unknown>;

export interface DbAutosyncResult {
  ok: boolean;
  inserted?: number;
  updated?: number;
  deleted?: number;
  importedFiles?: number;
  conflicts?: string[];
  exported?: string | null;
  error?: string;
}

function readString(record: unknown, key: string): string {
  if (!record || typeof record !== "object") return "";
  const value = (record as Record<string, unknown>)[key];
  return typeof value === "string" ? value : "";
}

export interface IncuratorHit {
  title?: string;
  path?: string;
  snippet: string;
  score?: number;
  sourceId?: number;
  pageNum?: number;
}

export interface IncuratorIngestRequest {
  sourcePath?: string;
  filePath?: string;
  zoteroAttachmentKey?: string;
  displayName?: string;
  destinationRelpath: string;
  importMode?: "copy" | "reference";
}

export interface ZoteroStatus {
  ok: boolean;
  state: string;
  dataDir?: string;
  dbPath?: string;
  rootsChecked: string[];
  issues: Array<Record<string, unknown>>;
  error?: string;
}

export interface ZoteroPdfResolution {
  ok: boolean;
  path?: string;
  /** Effective ATTACHMENT key the backend resolved to. Differs from the input
   * when a parent item key (from zotero_app_url) was resolved to its child PDF
   * attachment — needed so annotation lookups use the child key. */
  attachmentKey?: string;
  state?: string;
  error?: string;
  dbPath?: string;
  zoteroDb?: string;
  rootsChecked: string[];
  pathsChecked: string[];
}

export interface PdfTranscribeResult {
  ok: boolean;
  latex?: string;
  model?: string;
  error?: string;
}

export interface IncuratorStatusEvent {
  type: "status";
  status: IncuratorSourceStatus;
}

export class IncuratorClient {
  public needsUpdate = false;
  public backendVersion = "unknown";
  public updateMessage = "";
  public updateActionLabel = "Run Setup";
  // Repo root reported by the backend (null for non-editable site-packages installs).
  public repoPath: string | null = null;

  constructor(
    private readonly settings: PluginSettings,
    public readonly pluginVersion: string = "0.3.1",
    private readonly backendJson?: BackendJsonRunner
  ) {}

  get available(): boolean {
    return this.settings.incuratorEnabled !== false && !!this.backendJson;
  }

  async checkBackendVersion(): Promise<void> {
    if (!this.available) return;
    const result = await this.callBackendJson(["plugin", "version"]);
    if (result && typeof result === "object") {
      const record = result as Record<string, unknown>;
      const version = record.version;
      if (typeof version === "string") {
        this.backendVersion = version;
      }
      const repoPath = record.repo_path;
      this.repoPath = typeof repoPath === "string" && repoPath ? repoPath : null;

      const expectedBackendVersion = readString(localBuildManifest, "backend_version");
      if (expectedBackendVersion) {
        this.needsUpdate = this.backendVersion !== expectedBackendVersion;
        this.updateMessage = this.needsUpdate
          ? `Incurator backend version mismatch. Expected ${expectedBackendVersion}, got ${this.backendVersion}. Run setup to update this device.`
          : "";
        this.updateActionLabel = "Run Setup";
        return;
      }

      this.needsUpdate = this.backendVersion !== this.pluginVersion;
      this.updateMessage = this.needsUpdate
        ? "Incurator build metadata is missing or legacy. Run setup to refresh this device."
        : "";
      this.updateActionLabel = "Run Setup";
    }
  }

  async getSourceStatus(
    input?: string | { sourcePath?: string; fileHash?: string }
  ): Promise<IncuratorSourceStatus> {
    const sourcePath = typeof input === "string" ? input : input?.sourcePath;
    const fileHash = typeof input === "string" ? undefined : input?.fileHash;
    if ((!sourcePath && !fileHash) || this.settings.incuratorEnabled === false) {
      return { state: "unknown", message: "No source path available" };
    }

    const args = ["plugin", "source", "status"];
    if (fileHash) args.push("--file-hash", fileHash);
    if (sourcePath) args.push("--source-path", sourcePath);
    const result = await this.callBackendJson(args);
    if (!result || typeof result !== "object") return { state: "unknown", sourcePath };
    const record = result as Record<string, unknown>;
    if (record.registered === false) {
      return {
        state: "untracked",
        sourcePath,
        message: "Source is not registered in Incurator.",
        updatedAt: Date.now(),
      };
    }
    if (this.pickRecord(result).error) {
      return {
        state: "untracked",
        sourcePath,
        message: this.readString(this.pickRecord(result), ["error", "message"]),
      };
    }
    return this.normalizeStatus(result, sourcePath);
  }

  async ingestPdf(request: IncuratorIngestRequest): Promise<IncuratorSourceStatus> {
    const path = request.sourcePath || request.filePath;
    if (!path && !request.zoteroAttachmentKey) {
      return { state: "unknown", message: "No PDF path or Zotero attachment key available" };
    }

    const imported = await this.callBackendJson([
      "plugin", "source", "import",
      ...(path ? ["--file-path", path] : []),
      ...(request.zoteroAttachmentKey ? ["--zotero-attachment-key", request.zoteroAttachmentKey] : []),
      "--destination", request.destinationRelpath,
      "--policy", request.importMode === "copy" ? "mirror_03_to_04" : "reference",
    ]);
    if (!imported) {
      return {
        state: "unknown",
        sourcePath: path,
        destinationRelpath: request.destinationRelpath,
        message: "Incurator backend command is not available",
      };
    }
    const importRecord = this.pickRecord(imported);
    if (importRecord.ok === false || importRecord.error) {
      return {
        state: "error",
        sourcePath: path,
        destinationRelpath: request.destinationRelpath,
        message: this.readString(importRecord, ["error", "message"]) || "Source registration failed",
      };
    }
    const sourceId = this.readNumber(importRecord, ["sourceId", "source_id", "id"]);
    const relpath = this.readString(importRecord, ["relpath", "source_path", "path"]);
    const assetDir = this.resolvePdfAssetDir(request);
    const registered = await this.callBackendJson([
      "plugin", "source", "register",
      ...(sourceId ? ["--source-id", String(sourceId)] : []),
      ...(relpath ? ["--relpath", relpath] : []),
      ...(assetDir ? ["--asset-dir", assetDir] : []),
      "--build",
    ]);
    const status = this.normalizeStatus(registered || imported, path);
    status.sourceId = status.sourceId || sourceId;
    status.destinationRelpath = status.destinationRelpath || request.destinationRelpath || relpath;
    status.sourcePath = status.sourcePath || path;
    return status;
  }

  /**
   * Resolve the vault-relative folder for images extracted from an added PDF
   * (PLUGIN_SCHEMA §1.1). Zotero-backed PDFs reuse the first import profile's
   * asset spec with a per-item subfolder (display name, falling back to the
   * attachment key); other PDFs use a sanitized filename subfolder under the
   * `incuratorPdfAssetFolder` setting. Returns "" to omit --asset-dir so the
   * backend falls back to `05_Assets/<slug>/`.
   */
  private resolvePdfAssetDir(request: IncuratorIngestRequest): string {
    if (request.zoteroAttachmentKey) {
      const profile = this.settings.zoteroProfiles?.[0];
      if (profile) {
        const spec = resolveProfileAssetSpec(profile);
        const item = sanitizePathSegment(request.displayName || request.zoteroAttachmentKey);
        return joinVaultPath(spec.assetFolder, item);
      }
    }
    const baseFolder = (this.settings.incuratorPdfAssetFolder || "").trim();
    if (!baseFolder) return "";
    const path = request.filePath || request.sourcePath || "";
    const filename = path.split(/[\\/]/).pop() || "source";
    const slug = sanitizePathSegment(filename.replace(/\.pdf$/i, "")) || "source";
    return joinVaultPath(baseFolder, slug);
  }

  /**
   * Fire-and-forget auto-indexing for a PDF opened in the viewer.
   * Registers the file as an in-place reference and generates instant L1
   * (structural, no LLM) so backend PDF RAG becomes available
   * within seconds; L2/L3 are queued to the background worker.
   */
  async registerSource(filePath: string): Promise<IncuratorSourceStatus | null> {
    if (!filePath || this.settings.incuratorEnabled === false) return null;
    try {
      return await this.ingestPdf({
        filePath,
        sourcePath: filePath,
        destinationRelpath: "04_Resources",
        importMode: "reference",
      });
    } catch {
      return null;
    }
  }

  async getGitStatus(): Promise<GitStatusResult> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled", message: "Incurator backend is disabled." };
    }
    const result = await this.callBackendJson(["plugin", "git", "status"]);
    return this.pickRecord(result) as unknown as GitStatusResult;
  }

  async getGitLog(limit = 10): Promise<{ ok: boolean; commits?: unknown[]; error?: string; message?: string }> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled", message: "Incurator backend is disabled." };
    }
    const result = await this.callBackendJson([
      "plugin", "git", "log",
      "--limit", String(limit),
    ]);
    return this.pickRecord(result) as { ok: boolean; commits?: unknown[]; error?: string; message?: string };
  }

  async getGitDiffStat(): Promise<{ ok: boolean; stat?: string; staged_stat?: string; error?: string; message?: string }> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled", message: "Incurator backend is disabled." };
    }
    const result = await this.callBackendJson(["plugin", "git", "diff", "--stat"]);
    return this.pickRecord(result) as { ok: boolean; stat?: string; staged_stat?: string; error?: string; message?: string };
  }

  async getGitHistory(filePath: string, queryText = "", limit = 10): Promise<GitHistoryResult> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled", message: "Incurator backend is disabled." };
    }
    const result = await this.callBackendJson([
      "plugin", "git", "history",
      "--file-path", filePath,
      "--query", queryText,
      "--limit", String(limit),
    ]);
    return this.pickRecord(result) as unknown as GitHistoryResult;
  }

  async pushGitChanges(): Promise<GitPushResult> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled", message: "Incurator backend is disabled." };
    }
    const result = await this.callBackendJson(["plugin", "git", "push"]);
    return this.pickRecord(result) as unknown as GitPushResult;
  }

  async commitGitChanges(message: string): Promise<{ ok: boolean; commit?: string; error?: string; message?: string }> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled", message: "Incurator backend is disabled." };
    }
    const result = await this.callBackendJson([
      "plugin", "git", "commit",
      "--message", message,
    ]);
    return this.pickRecord(result) as { ok: boolean; commit?: string; error?: string; message?: string };
  }

  /**
   * Cross-device knowledge sync: import peer snapshots (and merge any Syncthing
   * conflict files), then export this device's snapshot if anything changed.
   * Runs in the backend subprocess so the Obsidian UI thread never parses JSONL.
   */
  async dbAutosync(): Promise<DbAutosyncResult> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled" };
    }
    const result = await this.callBackendJson(["db", "autosync", "--json", "--skip-reindex"]);
    if (!result) return { ok: false, error: "Empty response from backend" };
    const r = this.pickRecord(result);
    if (r.error) return { ok: false, error: r.error as string };
    return {
      ok: true,
      inserted: (r.inserted as number) ?? 0,
      updated: (r.updated as number) ?? 0,
      deleted: (r.deleted as number) ?? 0,
      importedFiles: (r.imported_files as number) ?? 0,
      conflicts: Array.isArray(r.conflicts) ? (r.conflicts as string[]) : [],
      exported: (r.exported as string | null) ?? null,
    };
  }

  async rebindSource(args: {
    sourceId?: number;
    sourcePath?: string;
    newPath: string;
    apply: boolean;
  }): Promise<IncuratorSourceStatus> {
    const cmd = [
      "plugin", "source", "rebind",
      "--new-path", args.newPath,
      args.apply ? "--apply" : "",
    ].filter(Boolean);
    if (args.sourceId) cmd.push("--source-id", String(args.sourceId));
    if (args.sourcePath) cmd.push("--source-path", args.sourcePath);
    const result = await this.callBackendJson(cmd);
    const status = this.normalizeStatus(result, args.sourcePath);
    status.candidatePath = status.candidatePath || args.newPath;
    return status;
  }

  async search(query: string, topK = 6): Promise<IncuratorHit[]> {
    if (!query.trim() || this.settings.incuratorEnabled === false) return [];
    const result = await this.callBackendJson([
      "plugin", "pdf", "search",
      "--query", query,
      "--limit", String(topK),
    ]);
    return this.normalizeHits(result);
  }

  async getPdfContext(args: {
    filePath?: string;
    sourceId?: number;
    relpath?: string;
    sourcePath?: string;
    fileHash?: string;
    zoteroAttachmentKey?: string;
    zoteroCustomPaths?: string;
    query?: string;
    pageNum?: number;
    radius?: number;
    maxPages?: number;
  }): Promise<{
    pages: PdfWindowPage[];
    outline: PdfOutlineItem[];
    totalPages: number;
    sourceTracked: boolean;
    isEmptyPdf: boolean;
    contextSource?: "durable_l1_projection" | "ephemeral_parse";
    degradedReason?: string;
  } | null> {
    if (
      this.settings.incuratorEnabled === false ||
      (!args.filePath && !args.sourceId && !args.relpath && !args.sourcePath && !args.fileHash && !args.zoteroAttachmentKey)
    ) return null;
    const cmd = [
      "plugin", "pdf", "context",
      "--query", args.query || "",
      "--page-num", String(args.pageNum ?? 0),
      "--radius", String(args.radius ?? 2),
      "--max-pages", String(args.maxPages ?? 8),
    ];
    if (args.filePath) cmd.push("--file-path", args.filePath);
    if (args.sourceId) cmd.push("--source-id", String(args.sourceId));
    if (args.relpath) cmd.push("--relpath", args.relpath);
    if (args.sourcePath) cmd.push("--source-path", args.sourcePath);
    if (args.fileHash) cmd.push("--file-hash", args.fileHash);
    if (args.zoteroAttachmentKey) cmd.push("--zotero-attachment-key", args.zoteroAttachmentKey);
    if (args.zoteroCustomPaths) cmd.push("--zotero-custom-paths", args.zoteroCustomPaths);
    const result = await this.callBackendJson(cmd);
    if (!result || typeof result !== "object") return null;
    const r = result as Record<string, unknown>;
    if (r["ok"] === false) return null;
    return {
      pages: this.normalizeWindowPages(r["pages"]),
      outline: this.normalizeOutline(r["outline"]),
      totalPages: typeof r["total_pages"] === "number" ? r["total_pages"] : 0,
      sourceTracked: r["source_tracked"] === true,
      isEmptyPdf: r["is_empty_pdf"] === true,
      contextSource:
        r["context_source"] === "durable_l1_projection" || r["context_source"] === "ephemeral_parse"
          ? r["context_source"]
          : undefined,
      degradedReason: typeof r["degraded_reason"] === "string" ? r["degraded_reason"] : undefined,
    };
  }

  async getPdfToc(filePath: string): Promise<PdfOutlineItem[]> {
    if (!filePath || this.settings.incuratorEnabled === false) return [];
    const result = await this.callBackendJson([
      "plugin", "pdf", "toc",
      "--file-path", filePath,
    ]);
    return this.normalizeOutline(result);
  }

  async getPdfRagHits(args: {
    query: string;
    sourcePath?: string;
    documentId?: string;
    topK: number;
  }): Promise<PdfRagHit[]> {
    if (!args.query.trim() || this.settings.incuratorEnabled === false) return [];
    const result = await this.callBackendJson([
      "plugin", "pdf", "search",
      "--query", args.query,
      ...(args.sourcePath ? ["--source-path", args.sourcePath] : []),
      "--limit", String(args.topK),
    ]);
    return this.normalizeRagHits(result);
  }

  async transcribePdfRegion(args: {
    imageFile?: string;
    text?: string;
    workspacePath?: string;
  }): Promise<PdfTranscribeResult> {
    if (this.settings.incuratorEnabled === false) {
      return { ok: false, error: "backend_disabled" };
    }
    const result = await this.callBackendJson([
      "plugin", "pdf", "transcribe",
      ...(args.imageFile ? ["--image-file", args.imageFile] : []),
      ...(args.text ? ["--text", args.text] : []),
      ...(args.workspacePath ? ["--workspace-path", args.workspacePath] : []),
    ]);
    return this.normalizePdfTranscribeResult(result);
  }

  async curatorQuery(
    question: string,
    opts: {
      workspacePath?: string;
      forceNew?: boolean;
      inputLanguage?: string;
      englishQuery?: string;
      finalOutputLanguage?: string;
    } = {}
  ): Promise<CuratorQueryResult> {
    const empty: CuratorQueryResult = { ok: false, question, error: "Incurator backend query command is not available" };
    if (!question.trim() || this.settings.incuratorEnabled === false) return empty;

    const result = await this.callBackendJson([
      "plugin", "query",
      "--question", question,
      ...(opts.inputLanguage ? ["--input-language", opts.inputLanguage] : []),
      ...(opts.englishQuery ? ["--english-query", opts.englishQuery] : []),
      ...(opts.finalOutputLanguage ? ["--final-output-language", opts.finalOutputLanguage] : []),
      ...(opts.workspacePath ? ["--workspace-path", opts.workspacePath] : []),
      ...(opts.forceNew ? ["--force-new"] : []),
    ]);
    return this.normalizeCuratorQueryResult(result, question, empty);
  }

  async fetchContext(
    query: string,
    opts: {
      workspacePath?: string;
      limitTokens?: number;
    } = {}
  ): Promise<CuratorContextPack> {
    const empty: CuratorContextPack = {
      ok: false,
      operation: "context_fetch",
      error: "Incurator backend context command is not available",
    };
    if (!query.trim() || this.settings.incuratorEnabled === false) return empty;

    const result = await this.callBackendJson([
      "plugin", "context", "fetch",
      "--query", query,
      ...(opts.workspacePath ? ["--workspace-path", opts.workspacePath] : []),
      ...(opts.limitTokens ? ["--limit-tokens", String(opts.limitTokens)] : []),
    ]);
    return this.normalizeContextPack(result, empty);
  }

  async expandContext(args: {
    packId: string;
    handles: string[];
    expectedSnapshotId: string;
    workspacePath?: string;
    limitTokens?: number;
  }): Promise<CuratorContextPack> {
    const empty: CuratorContextPack = {
      ok: false,
      operation: "context_expand",
      error: "Incurator backend context command is not available",
    };
    if (!args.packId || !args.handles.length || !args.expectedSnapshotId || this.settings.incuratorEnabled === false) {
      return empty;
    }

    const result = await this.callBackendJson([
      "plugin", "context", "expand",
      "--pack-id", args.packId,
      "--expected-snapshot-id", args.expectedSnapshotId,
      ...(args.limitTokens ? ["--limit-tokens", String(args.limitTokens)] : []),
      ...(args.workspacePath ? ["--workspace-path", args.workspacePath] : []),
      ...args.handles.flatMap((handle) => ["--handle", handle]),
    ]);
    return this.normalizeContextPack(result, empty);
  }

  async verifyContext(args: {
    packId: string;
    verificationHandle: string;
    expectedSnapshotId: string;
    workspacePath?: string;
  }): Promise<CuratorContextPack> {
    const empty: CuratorContextPack = {
      ok: false,
      operation: "context_verify",
      error: "Incurator backend context command is not available",
    };
    if (!args.packId || !args.verificationHandle || !args.expectedSnapshotId || this.settings.incuratorEnabled === false) {
      return empty;
    }

    const result = await this.callBackendJson([
      "plugin", "context", "verify",
      "--pack-id", args.packId,
      "--verification-handle", args.verificationHandle,
      "--expected-snapshot-id", args.expectedSnapshotId,
      ...(args.workspacePath ? ["--workspace-path", args.workspacePath] : []),
    ]);
    return this.normalizeContextPack(result, empty);
  }

  async feedbackContext(args: {
    traceId: string;
    packId: string;
    feedbackType: CuratorFeedbackType;
    statement: string;
    client?: string;
    purpose?: string;
    targetItemId?: string;
    targetRecordId?: string;
    reviewedSpanIds?: string[];
    workspacePath?: string;
  }): Promise<CuratorContextFeedbackResult> {
    const empty: CuratorContextFeedbackResult = {
      ok: false,
      operation: "context_feedback",
      error: "Incurator backend context command is not available",
    };
    if (!args.traceId || !args.packId || !args.feedbackType || !args.statement.trim() || this.settings.incuratorEnabled === false) {
      return empty;
    }

    const result = await this.callBackendJson([
      "plugin", "context", "feedback",
      "--trace-id", args.traceId,
      "--pack-id", args.packId,
      "--feedback-type", args.feedbackType,
      "--statement", args.statement,
      ...(args.client ? ["--client", args.client] : []),
      ...(args.purpose ? ["--purpose", args.purpose] : []),
      ...(args.targetItemId ? ["--target-item-id", args.targetItemId] : []),
      ...(args.targetRecordId ? ["--target-record-id", args.targetRecordId] : []),
      ...(args.workspacePath ? ["--workspace-path", args.workspacePath] : []),
      ...(args.reviewedSpanIds ?? []).flatMap((id) => ["--reviewed-span-id", id]),
    ]);
    return (result as CuratorContextFeedbackResult) ?? empty;
  }

  async promoteAnswer(
    question: string,
    answer: string,
    workspacePath?: string,
    sourceSpanIds?: string[]
  ): Promise<PromoteAnswerResult> {
    const empty: PromoteAnswerResult = { ok: false, error: "Incurator backend promote command is not available" };
    if (!question || !answer || this.settings.incuratorEnabled === false) return empty;

    // Pass the answer's query-trace source_span_ids so the promoted 02_Wiki/ note
    // gets a `## Sources` section linking the original source documents — making
    // them visible in Obsidian's Graph view / Backlinks (the hidden DAG can't).
    const result = await this.callBackendJson([
      "plugin", "promote",
      "--question", question,
      "--answer", answer,
      ...(workspacePath ? ["--workspace-path", workspacePath] : []),
      ...(sourceSpanIds && sourceSpanIds.length
        ? ["--source-span-ids", JSON.stringify(sourceSpanIds)]
        : []),
    ]);
    return this.normalizePromoteResult(result, empty);
  }

  // -- v0.3.1 curation-native interfaces ------------------------------------

  async getCuratePlan(workspacePath: string): Promise<IncuratorCuratePlan> {
    const empty: IncuratorCuratePlan = { ok: false, error: "Incurator backend is not available" };
    if (!workspacePath || this.settings.incuratorEnabled === false) return empty;
    const result = await this.callBackendJson([
      "plugin", "curate", "plan", "--workspace-path", workspacePath,
    ]);
    return (result as IncuratorCuratePlan) ?? empty;
  }

  async getPromptTrace(traceId: string, workspacePath = ""): Promise<IncuratorPromptTrace> {
    const empty: IncuratorPromptTrace = { ok: false, error: "Incurator backend is not available" };
    if (!traceId || this.settings.incuratorEnabled === false) return empty;
    const result = await this.callBackendJson([
      "plugin", "prompt", "trace", "--trace-id", traceId,
      ...(workspacePath ? ["--workspace-path", workspacePath] : []),
    ]);
    return (result as IncuratorPromptTrace) ?? empty;
  }

  async listInsightCandidates(
    workspacePath: string, status = "pending"
  ): Promise<IncuratorInsightListResult> {
    const empty: IncuratorInsightListResult = { ok: false, candidates: [], error: "Incurator backend is not available" };
    if (this.settings.incuratorEnabled === false) return empty;
    const result = await this.callBackendJson([
      "plugin", "insight", "list",
      ...(workspacePath ? ["--workspace-path", workspacePath] : []),
      "--status", status,
    ]);
    return (result as IncuratorInsightListResult) ?? empty;
  }

  async promoteInsight(
    insightId: string, workspacePath = ""
  ): Promise<IncuratorInsightPromoteResult> {
    const empty: IncuratorInsightPromoteResult = { ok: false, insightId, error: "Incurator backend is not available" };
    if (!insightId || this.settings.incuratorEnabled === false) return empty;
    const result = await this.callBackendJson([
      "plugin", "insight", "promote", "--insight-id", insightId,
      ...(workspacePath ? ["--workspace-path", workspacePath] : []),
    ]);
    return (result as IncuratorInsightPromoteResult) ?? empty;
  }

  async listSynthesisNodes(
    workspacePath = "", limit = 50
  ): Promise<IncuratorSynthesisListResult> {
    const empty: IncuratorSynthesisListResult = { ok: false, synthesis: [], error: "Incurator backend is not available" };
    if (this.settings.incuratorEnabled === false) return empty;
    const result = await this.callBackendJson([
      "plugin", "synthesis", "list",
      ...(workspacePath ? ["--workspace-path", workspacePath] : []),
      "--limit", String(limit),
    ]);
    return (result as IncuratorSynthesisListResult) ?? empty;
  }

  async getSynthesisAudit(
    synthesisId: string, workspacePath = ""
  ): Promise<IncuratorSynthesisAuditResult> {
    const empty: IncuratorSynthesisAuditResult = { ok: false, synthesisId, error: "Incurator backend is not available" };
    if (!synthesisId || this.settings.incuratorEnabled === false) return empty;
    const result = await this.callBackendJson([
      "plugin", "synthesis", "show", "--synthesis-id", synthesisId,
      ...(workspacePath ? ["--workspace-path", workspacePath] : []),
    ]);
    return (result as IncuratorSynthesisAuditResult) ?? empty;
  }

  async getZoteroStatus(): Promise<ZoteroStatus> {
    const result = await this.callBackendJson([
      "plugin", "zotero", "status",
      ...this.zoteroCustomPathArgs(),
    ]);
    return this.normalizeZoteroStatus(result);
  }

  async initZotero(dataDir = "", linkedBaseDir = ""): Promise<ZoteroStatus> {
    const result = await this.callBackendJson([
      "plugin", "zotero", "init",
      ...(dataDir ? ["--data-dir", dataDir] : []),
      ...(linkedBaseDir ? ["--linked-base-dir", linkedBaseDir] : []),
      ...this.zoteroCustomPathArgs(),
    ]);
    return this.normalizeZoteroStatus(result);
  }

  async searchZoteroItems(query: string, limit = 20): Promise<unknown[]> {
    const result = await this.callBackendJson([
      "plugin", "zotero", "search",
      "--query", query,
      "--limit", String(limit),
      ...this.zoteroCustomPathArgs(),
    ]);
    const record = this.pickRecord(result);
    if (record.ok === false) throw new Error(this.readString(record, ["error", "state"]) || "Zotero search failed");
    return this.readArray(result);
  }

  async getZoteroItemMetadata(itemKey: string, citationStyle = ""): Promise<unknown> {
    const result = await this.callBackendJson([
      "plugin", "zotero", "metadata",
      "--item-key", itemKey,
      ...(citationStyle ? ["--citation-style", citationStyle] : []),
      ...this.zoteroCustomPathArgs(),
    ]);
    const record = this.pickRecord(result);
    if (record.ok === false || !record.metadata) {
      throw new Error(this.readString(record, ["error", "state"]) || "Failed to fetch Zotero metadata");
    }
    return record.metadata;
  }

  async getZoteroAnnotations(attachmentKey: string): Promise<unknown[]> {
    const result = await this.callBackendJson([
      "plugin", "zotero", "annotations",
      "--attachment-key", attachmentKey,
      ...this.zoteroCustomPathArgs(),
    ]);
    const record = this.pickRecord(result);
    if (record.ok === false) throw new Error(this.readString(record, ["error", "state"]) || "Failed to fetch Zotero annotations");
    return this.readArray(record.annotations);
  }

  async resolveZoteroPdf(attachmentKey: string): Promise<ZoteroPdfResolution> {
    const result = await this.callBackendJson([
      "plugin", "zotero", "resolve-pdf",
      "--attachment-key", attachmentKey,
      ...this.zoteroCustomPathArgs(),
    ]);
    const record = this.pickRecord(result);
    return {
      ok: record.ok === true,
      path: this.readString(record, ["path"]),
      attachmentKey: this.readString(record, ["attachment_key", "attachmentKey"]),
      state: this.readString(record, ["state"]),
      error: this.readString(record, ["error", "message"]),
      dbPath: this.readString(record, ["db_path", "dbPath"]),
      zoteroDb: this.readString(record, ["zotero_db", "zoteroDb"]),
      rootsChecked: this.readArray(record.roots_checked).filter((item): item is string => typeof item === "string"),
      pathsChecked: this.readArray(record.paths_checked).filter((item): item is string => typeof item === "string"),
    };
  }

  private zoteroCustomPathArgs(): string[] {
    return [];
  }

  private async callBackendJson(cmdArgs: string[]): Promise<unknown | null> {
    if (!this.backendJson) return null;
    try {
      return await this.backendJson(cmdArgs);
    } catch (err) {
      logger.warn("Backend JSON command failed:", err);
      return null;
    }
  }

  private normalizeCuratorQueryResult(
    result: unknown,
    question: string,
    empty: CuratorQueryResult
  ): CuratorQueryResult {
    if (!result || typeof result !== "object") return empty;
    const r = result as Record<string, unknown>;
    return {
      ok: r.ok === true,
      answer: typeof r.answer === "string" ? r.answer : undefined,
      cache_hit: typeof r.cache_hit === "boolean" ? r.cache_hit : undefined,
      fallback: typeof r.fallback === "string" ? r.fallback : undefined,
      fallback_hits: Array.isArray(r.fallback_hits)
        ? (r.fallback_hits as CuratorQueryResult["fallback_hits"])
        : undefined,
      question: typeof r.question === "string" ? r.question : question,
      input_language: typeof r.input_language === "string" ? r.input_language : undefined,
      english_query: typeof r.english_query === "string" ? r.english_query : undefined,
      final_output_language: typeof r.final_output_language === "string" ? r.final_output_language : undefined,
      trace: r.trace as CuratorQueryResult["trace"],
      error: typeof r.error === "string" ? r.error : undefined,
      route: typeof r.route === "string" ? (r.route as CuratorQueryResult["route"]) : undefined,
      trace_id: typeof r.trace_id === "string" ? r.trace_id : undefined,
      pack_id: typeof r.pack_id === "string" || r.pack_id === null ? r.pack_id : undefined,
      snapshot:
        r.snapshot && typeof r.snapshot === "object" && !Array.isArray(r.snapshot)
          ? (r.snapshot as Record<string, unknown>)
          : r.snapshot === null
            ? null
            : undefined,
      budget:
        r.budget && typeof r.budget === "object" && !Array.isArray(r.budget)
          ? (r.budget as Record<string, unknown>)
          : r.budget === null
            ? null
            : undefined,
      prompt_trace_ids: Array.isArray(r.prompt_trace_ids) ? (r.prompt_trace_ids as string[]) : undefined,
      source_span_ids: Array.isArray(r.source_span_ids) ? (r.source_span_ids as string[]) : undefined,
      community_report_ids: Array.isArray(r.community_report_ids) ? (r.community_report_ids as string[]) : undefined,
      synthesis_node_ids: Array.isArray(r.synthesis_node_ids) ? (r.synthesis_node_ids as string[]) : undefined,
      memory_path_ids: Array.isArray(r.memory_path_ids) ? (r.memory_path_ids as string[]) : undefined,
      insight_candidate_ids: Array.isArray(r.insight_candidate_ids) ? (r.insight_candidate_ids as string[]) : undefined,
      warnings: Array.isArray(r.warnings) ? (r.warnings as string[]) : undefined,
    };
  }

  private normalizeContextPack(
    result: unknown,
    empty: CuratorContextPack
  ): CuratorContextPack {
    if (!result || typeof result !== "object") return empty;
    const r = result as Record<string, unknown>;
    return {
      ok: r.ok === true,
      operation: typeof r.operation === "string" ? r.operation : undefined,
      contract_version: typeof r.contract_version === "string" ? r.contract_version : undefined,
      pack_id: typeof r.pack_id === "string" ? r.pack_id : undefined,
      trace_id: typeof r.trace_id === "string" ? r.trace_id : undefined,
      retrieval_execution_id:
        typeof r.retrieval_execution_id === "string" ? r.retrieval_execution_id : undefined,
      route: typeof r.route === "string" ? r.route : undefined,
      route_reason: typeof r.route_reason === "string" ? r.route_reason : undefined,
      workspace_id: typeof r.workspace_id === "string" ? r.workspace_id : undefined,
      snapshot:
        r.snapshot && typeof r.snapshot === "object" && !Array.isArray(r.snapshot)
          ? (r.snapshot as Record<string, unknown>)
          : undefined,
      budget:
        r.budget && typeof r.budget === "object" && !Array.isArray(r.budget)
          ? (r.budget as Record<string, unknown>)
          : undefined,
      coverage:
        r.coverage && typeof r.coverage === "object" && !Array.isArray(r.coverage)
          ? (r.coverage as Record<string, unknown>)
          : undefined,
      actions: Array.isArray(r.actions) ? (r.actions as Array<Record<string, unknown>>) : undefined,
      items: Array.isArray(r.items) ? (r.items as CuratorContextPack["items"]) : undefined,
      evidence: Array.isArray(r.evidence) ? (r.evidence as CuratorContextPack["evidence"]) : undefined,
      source_span_ids: Array.isArray(r.source_span_ids) ? (r.source_span_ids as string[]) : undefined,
      community_report_ids: Array.isArray(r.community_report_ids)
        ? (r.community_report_ids as string[])
        : undefined,
      synthesis_node_ids: Array.isArray(r.synthesis_node_ids) ? (r.synthesis_node_ids as string[]) : undefined,
      memory_path_ids: Array.isArray(r.memory_path_ids) ? (r.memory_path_ids as string[]) : undefined,
      warnings: Array.isArray(r.warnings) ? (r.warnings as string[]) : undefined,
      next: Array.isArray(r.next) ? (r.next as Array<Record<string, unknown>>) : undefined,
      error: typeof r.error === "string" ? r.error : undefined,
      error_type: typeof r.error_type === "string" ? r.error_type : undefined,
      expected_snapshot_id:
        typeof r.expected_snapshot_id === "string" ? r.expected_snapshot_id : undefined,
      current_snapshot_id:
        typeof r.current_snapshot_id === "string" ? r.current_snapshot_id : undefined,
      resolution: typeof r.resolution === "string" ? r.resolution : undefined,
    };
  }

  private normalizePromoteResult(
    result: unknown,
    empty: PromoteAnswerResult
  ): PromoteAnswerResult {
    if (!result || typeof result !== "object") return empty;
    const r = result as Record<string, unknown>;
    return {
      ok: r.ok === true,
      promoted_to: typeof r.promoted_to === "string" ? r.promoted_to : undefined,
      error: typeof r.error === "string" ? r.error : undefined,
    };
  }

  private normalizeZoteroStatus(result: unknown): ZoteroStatus {
    const record = this.pickRecord(result);
    return {
      ok: record.ok === true,
      state: this.readString(record, ["state"]) || (record.ok === true ? "ready" : "unknown"),
      dataDir: this.readString(record, ["data_dir", "dataDir"]),
      dbPath: this.readString(record, ["db_path", "dbPath"]),
      rootsChecked: this.readArray(record.roots_checked).filter((item): item is string => typeof item === "string"),
      issues: this.readArray(record.issues).filter((item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item)),
      error: this.readString(record, ["error", "message"]),
    };
  }

  private normalizeStatus(value: unknown, sourcePath?: string): IncuratorSourceStatus {
    const record = this.pickRecord(value);
    let state = this.normalizeState(
      this.readString(record, ["state", "status", "ingest_state", "result"]) || "unknown"
    );
    const l1 = this.readBoolean(record, ["l1_complete"]) || this.readString(record, ["l1_status"]) === "done";
    const l2 = this.readBoolean(record, ["l2_complete"]) || this.readString(record, ["l2_status"]) === "done";
    const l3 = this.readBoolean(record, ["l3_complete"]) || this.readString(record, ["l3_status"]) === "done";
    const l4 = this.readBoolean(record, ["l4_complete"]) || this.readString(record, ["l4_status"]) === "done";
    const layerError = Boolean(
      this.readString(record, ["layer_error", "error_reason"]) ||
      ["l1", "l2", "l3", "l4"].some((layer) => this.readString(record, [`${layer}_status`]) === "error")
    );
    const pendingJobs = this.readArray(record.jobs_pending);
    if (record.ok === false) {
      state = "error";
    } else if (layerError) {
      state = "error";
    } else if (state === "unknown" || state === "queued" || state === "l1_ready" || state === "l2_ready" || state === "l3_ready" || state === "l4_ready") {
      if (l4) state = "l4_ready";
      else if (l3) state = "l3_ready";
      else if (l2) state = "l2_ready";
      else if (l1 && pendingJobs.length > 0) state = "queued";
      else if (l1) state = "l1_ready";
    }
    if (state === "unknown" && record.ok === true) {
      state = record.context_id || record.contextId ? "l1_ready" : "queued";
    }

    let runningLayer: string | undefined;
    if (state === "running") {
      for (const layer of ["l4", "l3", "l2", "l1"]) {
        const layerStatus = this.readString(record, [`${layer}_status`]);
        if (layerStatus === "running") {
          runningLayer = layer;
          break;
        }
      }
    }

    return {
      state,
      l1Complete: l1,
      l2Complete: l2,
      l3Complete: l3,
      l4Complete: l4,
      sourceId: this.readNumber(record, ["sourceId", "source_id", "id"]),
      sourcePath: this.readString(record, ["sourcePath", "source_path", "file_path", "path"]) || sourcePath,
      destinationRelpath: this.readString(record, [
        "destinationRelpath",
        "destination_relpath",
        "destination",
      ]),
      contextId: this.readString(record, ["contextId", "context_id", "document_id"]),
      pageCount: this.readNumber(record, ["pageCount", "page_count", "pages"]),
      currentPath: this.readString(record, ["currentPath", "current_path", "external_path"]),
      candidatePath: this.readString(record, ["candidatePath", "candidate_path"]),
      requiresRebind: this.readBoolean(record, ["requiresRebind", "requires_rebind"]),
      message: this.readString(record, ["message", "detail", "error"]),
      updatedAt: Date.now(),
      runningLayer,
    };
  }

  private normalizeHits(value: unknown): IncuratorHit[] {
    return this.readArray(value).map((item) => {
      const record = this.pickRecord(item);
      return {
        title: this.readString(record, ["title", "name"]),
        path: this.readString(record, ["path", "source_path", "file_path"]),
        snippet: this.readString(record, ["snippet", "text", "content", "summary"]) || "",
        score: this.readNumber(record, ["score", "rank"]),
        sourceId: this.readNumber(record, ["sourceId", "source_id", "id"]),
        pageNum: this.readNumber(record, ["pageNum", "page_num", "page"]),
      };
    }).filter((hit) => hit.snippet || hit.path || hit.title);
  }

  private normalizeWindowPages(value: unknown): PdfWindowPage[] {
    return this.readArray(value).map((item) => {
      const record = this.pickRecord(item);
      return {
        pageNum: this.readNumber(record, ["pageNum", "page_num", "page"]) || 0,
        text: this.readString(record, ["text", "content", "snippet"]) || "",
      };
    }).filter((page) => page.pageNum > 0 && page.text.trim());
  }

  private normalizeOutline(value: unknown): PdfOutlineItem[] {
    return this.readArray(value).map((item) => {
      const record = this.pickRecord(item);
      return {
        title: this.readString(record, ["title", "label", "name"]) || "Untitled",
        pageNum: this.readNumber(record, ["pageNum", "page_num", "page"]),
        level: this.readNumber(record, ["level", "depth"]) || 0,
      };
    }).filter((item) => item.title.trim());
  }

  private normalizeRagHits(value: unknown): PdfRagHit[] {
    return this.readArray(value).map((item) => {
      const record = this.pickRecord(item);
      return {
        pageNum: this.readNumber(record, ["pageNum", "page_num", "page"]) || 0,
        score: this.readNumber(record, ["score", "rank"]) || 0,
        snippet: this.readString(record, ["snippet", "text", "content"]) || "",
        sectionTitle: this.readString(record, ["sectionTitle", "section_title", "section"]),
      };
    }).filter((hit) => hit.pageNum > 0 && hit.snippet.trim());
  }

  private normalizePdfTranscribeResult(value: unknown): PdfTranscribeResult {
    if (!value || typeof value !== "object") {
      return { ok: false, error: "Empty response from backend" };
    }
    const record = this.pickRecord(value);
    return {
      ok: record.ok === true,
      latex: this.readString(record, ["latex"]) || undefined,
      model: this.readString(record, ["model"]) || undefined,
      error: this.readString(record, ["error"]) || undefined,
    };
  }

  private readArray(value: unknown): unknown[] {
    if (Array.isArray(value)) return value;
    const record = this.pickRecord(value);
    for (const key of ["items", "results", "hits", "pages", "outline", "window"]) {
      const nested = record[key];
      if (Array.isArray(nested)) return nested;
    }
    return [];
  }

  private pickRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object") return {};
    const record = value as Record<string, unknown>;
    for (const key of ["data", "result", "source", "status"]) {
      const nested = record[key];
      if (nested && typeof nested === "object" && !Array.isArray(nested)) {
        return nested as Record<string, unknown>;
      }
    }
    return record;
  }

  private readString(record: Record<string, unknown>, keys: string[]): string | undefined {
    for (const key of keys) {
      const value = record[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return undefined;
  }

  private readNumber(record: Record<string, unknown>, keys: string[]): number | undefined {
    for (const key of keys) {
      const value = record[key];
      if (typeof value === "number" && Number.isFinite(value)) return value;
      if (typeof value === "string") {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
      }
    }
    return undefined;
  }

  private readBoolean(record: Record<string, unknown>, keys: string[]): boolean | undefined {
    for (const key of keys) {
      const value = record[key];
      if (typeof value === "boolean") return value;
      if (typeof value === "number") return value !== 0;
      if (typeof value === "string") {
        const lower = value.toLowerCase();
        if (["true", "1", "yes"].includes(lower)) return true;
        if (["false", "0", "no"].includes(lower)) return false;
      }
    }
    return undefined;
  }

  private normalizeState(value: string): IncuratorSourceState {
    const lower = value.toLowerCase();
    if (lower.includes("error") || lower.includes("fail")) return "error";
    if (lower.includes("l1_ready")) return "l1_ready";
    if (lower.includes("l2_ready")) return "l2_ready";
    if (lower.includes("l3_ready")) return "l3_ready";
    if (lower.includes("l4_ready")) return "l4_ready";
    if (lower.includes("curated")) return "l4_ready";
    if (lower.includes("index") || lower.includes("ready") || lower.includes("done")) return "l3_ready";
    if (lower.includes("queue") || lower.includes("pending")) return "queued";
    if (lower.includes("run") || lower.includes("ingest") || lower.includes("process")) return "running";
    if (lower.includes("stale")) return "stale";
    if (lower.includes("moved") && lower.includes("hash")) return "moved_and_hash_drift";
    if (lower.includes("hash_drift") || (lower.includes("hash") && lower.includes("drift"))) return "hash_drift";
    if (lower.includes("moved")) return "moved";
    if (lower.includes("missing")) return "missing";
    if (lower.includes("untracked") || lower.includes("not_found")) return "untracked";
    return "unknown";
  }
}
