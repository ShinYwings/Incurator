import type { MCPManager } from "./mcpClient";
import type {
  IncuratorSourceStatus,
  IncuratorSourceState,
  MCPTool,
  PdfOutlineItem,
  PdfRagHit,
  PdfWindowPage,
  PluginSettings,
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
  constructor(
    private readonly mcpManager: MCPManager,
    private readonly settings: PluginSettings
  ) {}

  get available(): boolean {
    return this.settings.incuratorEnabled !== false && this.getIncuratorTools().length > 0;
  }

  async getSourceStatus(sourcePath?: string): Promise<IncuratorSourceStatus> {
    if (!sourcePath || this.settings.incuratorEnabled === false) {
      return { state: "unknown", message: "No source path available" };
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

  async ingestPdf(request: IncuratorIngestRequest): Promise<IncuratorSourceStatus> {
    const path = request.sourcePath || request.filePath;
    if (!path) {
      return { state: "unknown", message: "No PDF path available" };
    }

    const imported = await this.tryTool(["curator_import_source", "import_source", "ingest_pdf", "import_pdf"], {
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

    const ingested = await this.tryTool(["curator_ingest_source", "ingest_source", "source_ingest"], {
      source_id: sourceId,
      relpath,
      source_path: relpath,
      file_path: relpath,
      path: relpath,
    });

    const status = this.normalizeStatus(ingested || imported, path);
    status.sourceId = status.sourceId || sourceId;
    status.destinationRelpath =
      status.destinationRelpath || request.destinationRelpath || relpath;
    status.sourcePath = status.sourcePath || path;
    return status;
  }

  async rebindSource(args: {
    sourceId?: number;
    sourcePath?: string;
    newPath: string;
    apply: boolean;
  }): Promise<IncuratorSourceStatus> {
    const result = await this.tryTool(["curator_rebind_source", "rebind_source", "source_rebind"], {
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
      ["search_curator", "curator_search", "search", "vault_search", "semantic_search", "incurator_search"],
      { query, text: query, top_k: topK, topK, limit: topK }
    );
    return this.normalizeHits(result);
  }

  async getPdfWindow(args: {
    sourcePath?: string;
    documentId?: string;
    pageNum?: number;
    radius: number;
  }): Promise<PdfWindowPage[]> {
    if (!args.pageNum || this.settings.incuratorEnabled === false) return [];
    const result = await this.tryTool(["pdf_window", "get_pdf_window", "document_window"], {
      source_path: args.sourcePath,
      file_path: args.sourcePath,
      path: args.sourcePath,
      document_id: args.documentId,
      page: args.pageNum,
      page_num: args.pageNum,
      pageNum: args.pageNum,
      radius: args.radius,
    });
    return this.normalizeWindowPages(result);
  }

  async getDocumentOutline(args: {
    sourcePath?: string;
    documentId?: string;
  }): Promise<PdfOutlineItem[]> {
    const result = await this.tryTool(["document_outline", "get_document_outline", "pdf_outline"], {
      source_path: args.sourcePath,
      file_path: args.sourcePath,
      path: args.sourcePath,
      document_id: args.documentId,
    });
    return this.normalizeOutline(result);
  }

  async getPdfRagHits(args: {
    query: string;
    sourcePath?: string;
    documentId?: string;
    topK: number;
  }): Promise<PdfRagHit[]> {
    if (!args.query.trim() || this.settings.incuratorEnabled === false) return [];
    const result = await this.tryTool(["curator_search_source", "curator_search_sources", "search_sources", "pdf_rag_hits", "pdf_search", "search_pdf", "rag"], {
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

  private getIncuratorTools(): ToolWithServer[] {
    return this.mcpManager
      .getAllTools()
      .filter((tool) => {
        const serverName = tool.serverName.toLowerCase();
        const toolName = tool.name.toLowerCase();
        return serverName.includes("incurator") || toolName.includes("incurator");
      });
  }

  private async tryTool(
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
