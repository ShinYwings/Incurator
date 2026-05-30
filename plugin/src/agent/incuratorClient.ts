import type { MCPManager } from "./mcpClient";
import type {
  CuratorQueryResult,
  IncuratorSourceStatus,
  IncuratorSourceState,
  MCPTool,
  ModelCatalogue,
  PdfOutlineItem,
  PdfRagHit,
  PdfWindowPage,
  PluginSettings,
  PromoteExhibitionResult,
} from "../types";

type ToolWithServer = MCPTool & { serverName: string };

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
  displayName?: string;
  destinationRelpath: string;
  importMode?: "copy" | "reference";
}

export interface IncuratorStatusEvent {
  type: "status";
  status: IncuratorSourceStatus;
}

export class IncuratorClient {
  public needsUpdate = false;
  public backendVersion = "unknown";

  constructor(
    private readonly mcpManager: MCPManager,
    private readonly settings: PluginSettings,
    public readonly pluginVersion: string = "0.2.1"
  ) {}

  get available(): boolean {
    return this.settings.incuratorEnabled !== false && this.getIncuratorTools().length > 0;
  }

  async checkBackendVersion(): Promise<void> {
    if (!this.available) return;
    const result = await this.tryTool(["curator_get_version"], {});
    if (result && typeof result === "string") {
      this.backendVersion = result;
      // Compare backendVersion with pluginVersion
      // Assuming semantic versioning string comparison works for simple equality
      this.needsUpdate = this.backendVersion !== this.pluginVersion;
    }
  }

  async getBackendStatus(): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_status"], {});
  }

  async runSync(): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_sync"], {});
  }

  async runLint(): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_lint"], {});
  }

  async runReindex(): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_reindex"], {});
  }

  async runAdd(): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_add_all", "curator_add"], {});
  }

  async runBuild(): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_build_all", "curator_build"], {});
  }

  async runCurate(workspacePath?: string): Promise<any> {
    if (this.settings.incuratorEnabled === false) return null;
    return await this.tryTool(["curator_curate_workspace"], { workspace_path: workspacePath ?? "" });
  }

  async getSourceStatus(
    input?: string | { sourcePath?: string; fileHash?: string }
  ): Promise<IncuratorSourceStatus> {
    const sourcePath = typeof input === "string" ? input : input?.sourcePath;
    const fileHash = typeof input === "string" ? undefined : input?.fileHash;
    if ((!sourcePath && !fileHash) || this.settings.incuratorEnabled === false) {
      return { state: "unknown", message: "No source path available" };
    }

    if (fileHash) {
      const byHash = await this.tryTool(["check_source_status"], {
        file_hash: fileHash,
      });
      if (byHash && typeof byHash === "object") {
        const record = byHash as Record<string, unknown>;
        if (record.registered === false) {
          return {
            state: "untracked",
            sourcePath,
            message: "Source is not registered in Incurator.",
            updatedAt: Date.now(),
          };
        }
        return this.normalizeStatus(byHash, sourcePath);
      }
    }

    const result = await this.tryTool(
      ["curator_source_status", "source_status", "get_source_status", "pdf_status", "status"],
      { source_path: sourcePath, file_path: sourcePath, path: sourcePath, relpath: sourcePath }
    );
    if (!result) return { state: "unknown", sourcePath };
    if (this.pickRecord(result).error) {
      return {
        state: "untracked",
        sourcePath,
        message: this.readString(this.pickRecord(result), ["error", "message"]),
      };
    }
    return this.normalizeStatus(result, sourcePath);
  }

  async getAvailableModels(): Promise<ModelCatalogue> {
    if (this.settings.incuratorEnabled === false) return {};
    const result = await this.tryTool(["get_available_models"], {});
    const record = this.pickRecord(result);
    const providers = record.providers;
    if (!providers || typeof providers !== "object" || Array.isArray(providers)) {
      return {};
    }
    const catalogue: ModelCatalogue = {};
    for (const [provider, rawModels] of Object.entries(providers as Record<string, unknown>)) {
      if (!["antigravity", "claude", "openai", "ollama"].includes(provider) || !Array.isArray(rawModels)) {
        continue;
      }
      catalogue[provider as keyof ModelCatalogue] = rawModels
        .map((item) => {
          const model = this.pickRecord(item);
          const id = this.readString(model, ["id"]);
          if (!id) return null;
          const rawEfforts = model["efforts"];
          const efforts = Array.isArray(rawEfforts)
            ? rawEfforts.filter((e): e is string => typeof e === "string")
            : [];
          return {
            id: this.readString(model, ["id"]),
            label: this.readString(model, ["label"]),
            supportsVision: this.readBoolean(model, ["supports_vision", "supportsVision"]) !== false,

            contextWindow: this.readNumber(model, ["context_window", "contextWindow"]),
            efforts,
            defaultEffort: this.readString(model, ["default_effort", "defaultEffort"]),
          };
        })
        .filter((model): model is NonNullable<typeof model> => Boolean(model));
    }
    return catalogue;
  }

  async ingestPdf(request: IncuratorIngestRequest): Promise<IncuratorSourceStatus> {
    const path = request.sourcePath || request.filePath;
    if (!path) {
      return { state: "unknown", message: "No PDF path available" };
    }

    const imported = await this.tryTool(["curator_import_source"], {
      source_path: path,
      file_path: path,
      path,
      display_name: request.displayName,
      name: request.displayName,
      destination_relpath: request.destinationRelpath,
      destination: request.destinationRelpath,
      policy: request.importMode === "copy" ? "mirror_03_to_04" : "reference",
      dry_run: false,
    });

    if (!imported) {
      return {
        state: "unknown",
        sourcePath: path,
        destinationRelpath: request.destinationRelpath,
        message: "Incurator ingest tool is not available",
      };
    }

    const importedRecord = this.pickRecord(imported);
    const sourceId = this.readNumber(importedRecord, ["sourceId", "source_id", "id"]);
    const relpath = this.readString(importedRecord, ["relpath", "source_path", "path"]);

    // Instant L1 (no LLM) + enqueue L2/L3 to the background worker (build=true).
    const ingested = await this.tryTool(["curator_register_source"], {
      source_id: sourceId,
      relpath,
      source_path: relpath,
      file_path: relpath,
      path: relpath,
      build: true,
    });

    const status = this.normalizeStatus(ingested || imported, path);
    status.sourceId = status.sourceId || sourceId;
    status.destinationRelpath =
      status.destinationRelpath || request.destinationRelpath || relpath;
    status.sourcePath = status.sourcePath || path;
    return status;
  }

  /**
   * Fire-and-forget auto-indexing for a PDF opened in the viewer.
   * Registers the file as an in-place reference and generates instant L1
   * (structural, no LLM) so curator_search_sources RAG becomes available
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

  async rebindSource(args: {
    sourceId?: number;
    sourcePath?: string;
    newPath: string;
    apply: boolean;
  }): Promise<IncuratorSourceStatus> {
    const result = await this.tryTool(["curator_rebind_source"], {
      source_id: args.sourceId,
      source_path: args.sourcePath,
      file_path: args.sourcePath,
      path: args.sourcePath,
      new_path: args.newPath,
      apply: args.apply,
      update_hash: true,
    });
    if (!result) {
      return {
        state: "unknown",
        sourcePath: args.sourcePath,
        candidatePath: args.newPath,
        message: "Incurator rebind tool is not available",
      };
    }
    const status = this.normalizeStatus(result, args.sourcePath);
    status.candidatePath = status.candidatePath || args.newPath;
    return status;
  }

  async search(query: string, topK = 6): Promise<IncuratorHit[]> {
    if (!query.trim() || this.settings.incuratorEnabled === false) return [];
    const result = await this.tryTool(
      ["search_curator"],
      { query, text: query, top_k: topK, topK, limit: topK }
    );
    return this.normalizeHits(result);
  }

  async getPdfContext(args: {
    filePath: string;
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
  } | null> {
    if (!args.filePath || this.settings.incuratorEnabled === false) return null;
    const result = await this.tryTool(["curator_get_pdf_context"], {
      file_path: args.filePath,
      query: args.query || "",
      page_num: args.pageNum ?? 0,
      radius: args.radius ?? 2,
      max_pages: args.maxPages ?? 8,
    });
    if (!result || typeof result !== "object") return null;
    const r = result as Record<string, unknown>;
    if (r["ok"] === false) return null;
    return {
      pages: this.normalizeWindowPages(r["pages"]),
      outline: this.normalizeOutline(r["outline"]),
      totalPages: typeof r["total_pages"] === "number" ? r["total_pages"] : 0,
      sourceTracked: r["source_tracked"] === true,
      isEmptyPdf: r["is_empty_pdf"] === true,
    };
  }

  async getPdfRagHits(args: {
    query: string;
    sourcePath?: string;
    documentId?: string;
    topK: number;
  }): Promise<PdfRagHit[]> {
    if (!args.query.trim() || this.settings.incuratorEnabled === false) return [];
    const result = await this.tryTool(["curator_search_sources"], {
      query: args.query,
      source_path: args.sourcePath,
      file_path: args.sourcePath,
      path: args.sourcePath,
      relpath: args.sourcePath,
      document_id: args.documentId,
      top_k: args.topK,
      topK: args.topK,
      limit: args.topK,
    });
    return this.normalizeRagHits(result);
  }

  async getZoteroAnnotations(attachmentKey: string): Promise<any[]> {
    if (!attachmentKey || this.settings.incuratorEnabled === false) return [];
    const result = await this.tryTool(["curator_get_zotero_annotations"], {
      attachment_key: attachmentKey,
      attachmentKey: attachmentKey,
      custom_paths: this.buildZoteroCustomPaths(),
    });

    if (result && typeof result === "object" && (result as any).ok) {
      return (result as any).annotations || [];
    }
    return [];
  }

  async resolveZoteroPdf(attachmentKey: string): Promise<string | null> {
    if (!attachmentKey || this.settings.incuratorEnabled === false) return null;
    const result = await this.tryTool(["curator_resolve_zotero_pdf"], {
      attachment_key: attachmentKey,
      attachmentKey: attachmentKey,
      custom_paths: this.buildZoteroCustomPaths(),
    });

    if (result && typeof result === "object" && (result as any).ok) {
      return (result as any).path || null;
    }
    return null;
  }

  private buildZoteroCustomPaths(): string {
    return this.settings.zoteroBasePath || "";
  }

  async curatorQuery(
    question: string,
    opts: { workspacePath?: string; forceNew?: boolean } = {}
  ): Promise<CuratorQueryResult> {
    const empty: CuratorQueryResult = { ok: false, question, error: "curator_query not available" };
    if (!question.trim() || this.settings.incuratorEnabled === false) return empty;

    const result = await this.tryTool(["curator_query"], {
      question,
      workspace_path: opts.workspacePath ?? "",
      force_new: opts.forceNew ?? false,
    });
    if (!result || typeof result !== "object") return empty;
    const r = result as Record<string, unknown>;
    return {
      ok: r.ok === true,
      answer: typeof r.answer === "string" ? r.answer : undefined,
      exhibition_id: typeof r.exhibition_id === "string" ? r.exhibition_id : undefined,
      cache_hit: typeof r.cache_hit === "boolean" ? r.cache_hit : undefined,
      fallback: typeof r.fallback === "string" ? r.fallback : undefined,
      fallback_hits: Array.isArray(r.fallback_hits)
        ? (r.fallback_hits as CuratorQueryResult["fallback_hits"])
        : undefined,
      question: typeof r.question === "string" ? r.question : question,
      trace: r.trace as CuratorQueryResult["trace"],
      error: typeof r.error === "string" ? r.error : undefined,
    };
  }

  async promoteExhibition(
    exhId: string,
    workspacePath?: string
  ): Promise<PromoteExhibitionResult> {
    const empty: PromoteExhibitionResult = { ok: false, exhibition_id: exhId, error: "promote_exhibition not available" };
    if (!exhId || this.settings.incuratorEnabled === false) return empty;

    const result = await this.tryTool(["promote_exhibition"], {
      exh_id: exhId,
      workspace_path: workspacePath ?? "",
    });
    if (!result || typeof result !== "object") return empty;
    const r = result as Record<string, unknown>;
    return {
      ok: r.ok === true,
      exhibition_id: typeof r.exhibition_id === "string" ? r.exhibition_id : exhId,
      promoted_to: typeof r.promoted_to === "string" ? r.promoted_to : undefined,
      error: typeof r.error === "string" ? r.error : undefined,
    };
  }

  private getIncuratorTools(): ToolWithServer[] {
    return this.mcpManager
      .getAllTools()
      .filter((tool) => {
        const serverName = tool.serverName.toLowerCase();
        const toolName = tool.name.toLowerCase();
        return serverName.includes("incurator") || toolName.includes("incurator");
      });
  }

  public async tryTool(
    preferredNames: string[],
    args: Record<string, unknown>
  ): Promise<unknown | null> {
    const tools = this.getIncuratorTools();
    if (tools.length === 0) return null;

    const lowerPreferred = preferredNames.map((name) => name.toLowerCase());
    const candidates = tools
      .filter((tool) => {
        const name = tool.name.toLowerCase();
        return lowerPreferred.some((preferred) => name === preferred || name.endsWith(preferred));
      })
      .concat(
        tools.filter((tool) => {
          const name = tool.name.toLowerCase();
          return lowerPreferred.some((preferred) => name.includes(preferred));
        })
      );

    const unique = Array.from(
      new Map(candidates.map((tool) => [`${tool.serverName}:${tool.name}`, tool])).values()
    );

    for (const tool of unique) {
      try {
        const result = await this.mcpManager.callTool(tool.serverName, tool.name, this.compactArgs(args));
        if (result.isError) continue;
        return this.readToolResult(result);
      } catch (err) {
        console.warn(`[Incurator] Tool ${tool.name} failed:`, err);
      }
    }

    return null;
  }

  private compactArgs(args: Record<string, unknown>): Record<string, unknown> {
    return Object.fromEntries(
      Object.entries(args).filter(([, value]) => value !== undefined && value !== "")
    );
  }

  private readToolResult(result: unknown): unknown {
    if (!result || typeof result !== "object") return result;
    const content = (result as { content?: Array<{ type: string; text?: string }> }).content;
    if (!Array.isArray(content)) return result;

    const text = content
      .filter((part) => part.type === "text" && part.text)
      .map((part) => part.text)
      .join("\n")
      .trim();
    if (!text) return result;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  private normalizeStatus(value: unknown, sourcePath?: string): IncuratorSourceStatus {
    const record = this.pickRecord(value);
    let state = this.normalizeState(
      this.readString(record, ["state", "status", "ingest_state", "result"]) || "unknown"
    );
    const l1 = this.readBoolean(record, ["l1_complete"]) || this.readString(record, ["l1_status"]) === "done";
    const l2 = this.readBoolean(record, ["l2_complete"]) || this.readString(record, ["l2_status"]) === "done";
    const l3 = this.readBoolean(record, ["l3_complete"]) || this.readString(record, ["l3_status"]) === "done";
    const l4 = this.readString(record, ["l4_status"]) === "done";
    const pendingJobs = this.readArray(record.jobs_pending);
    if (state === "unknown" || state === "queued" || state === "indexed") {
      if (l4 || state === "curated") state = "curated";
      else if (l3) state = "indexed";
      else if (l2) state = "l2_ready";
      else if (l1 && pendingJobs.length > 0) state = "queued";
      else if (l1) state = "l1_ready";
    }
    if (state === "unknown" && record.ok === true) {
      state = record.context_id || record.contextId ? "indexed" : "queued";
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
    if (lower.includes("curated")) return "curated";
    if (lower.includes("index") || lower.includes("ready") || lower.includes("done")) return "indexed";
    if (lower.includes("queue") || lower.includes("pending")) return "queued";
    if (lower.includes("run") || lower.includes("ingest") || lower.includes("process")) return "running";
    if (lower.includes("stale")) return "stale";
    if (lower.includes("moved") && lower.includes("hash")) return "moved_and_hash_drift";
    if (lower.includes("hash_drift") || (lower.includes("hash") && lower.includes("drift"))) return "hash_drift";
    if (lower.includes("moved")) return "moved";
    if (lower.includes("missing")) return "missing";
    if (lower.includes("error") || lower.includes("fail")) return "error";
    if (lower.includes("untracked") || lower.includes("not_found")) return "untracked";
    return "unknown";
  }
}
