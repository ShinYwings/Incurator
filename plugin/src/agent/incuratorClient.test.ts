import { describe, expect, it } from "vitest";
import { IncuratorClient } from "./incuratorClient";
import type { PluginSettings } from "../types";
import localBuildManifest from "../generated/buildManifest.json";

function settings(): PluginSettings {
  return {
    provider: "antigravity",
    model: "",
    chatMode: "chat",
    codexReasoningEffort: "medium",
    claudeEffort: "medium",
    agentEffort: "",
    antigravityPrintTimeoutSec: 300,
    providerUsage: {
      antigravity: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
      claude: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
      openai: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
      ollama: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
      deepseek: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
    },
    deepseekApiKey: "",
    diffMode: "inline",
    streamingEnabled: true,
    editArtifactEnabled: true,
    quickQueryEnabled: true,
    mcpServers: [],
    maxContextLength: 128000,
    ollamaHost: "http://localhost:11434",
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
    incuratorStatusPolling: true,
    zoteroBasePath: "~/Zotero",
    zoteroProfiles: [],
    recentZoteroItems: [],
  };
}

describe("IncuratorClient", () => {
  it("uses the backend JSON source status command with file hashes", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return {
        registered: true,
        source: {
          state: "pending",
          l1_complete: true,
          l2_complete: false,
          l3_complete: false,
          jobs_pending: [{ id: 1 }],
        },
      };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);
    const status = await client.getSourceStatus({
      sourcePath: "/tmp/paper.pdf",
      fileHash: "abc",
    });

    expect(calls[0]).toEqual([
      "plugin",
      "source",
      "status",
      "--file-hash",
      "abc",
      "--source-path",
      "/tmp/paper.pdf",
    ]);
    expect(status.state).toBe("queued");
  });

  it("normalizes layer status progressively and lets errors win", async () => {
    const client = new IncuratorClient(settings());
    const normalize = (value: unknown) => (client as any).normalizeStatus(value);

    expect(normalize({ state: "done", l1_status: "done" }).state).toBe("l1_ready");
    expect(normalize({ l1_status: "done", l2_status: "done" }).state).toBe("l2_ready");
    expect(normalize({ l1_status: "done", l2_status: "done", l3_status: "done" }).state).toBe("l3_ready");
    expect(normalize({ l1_status: "done", l2_status: "done", l3_status: "done", l4_status: "done" }).state).toBe("l4_ready");
    expect(normalize({ l1_status: "done", l2_status: "done", l3_status: "error" }).state).toBe("error");
  });

  it("normalizes failed tool payloads as error states", async () => {
    const client = new IncuratorClient(settings());
    const normalize = (value: unknown) => (client as any).normalizeStatus(value);

    expect(normalize({ ok: false, error: "PDF not found" }).state).toBe("error");
    expect(normalize({ ok: false, error: "PDF not found" }).message).toBe("PDF not found");
  });

  it("checks backend version and sets needsUpdate flag", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.1",
      build: { backend_version: "0.3.1" },
    }));
    // Override local manifest mock for this test implicitly by passing version match
    const originalManifest = JSON.parse(JSON.stringify(localBuildManifest));
    (localBuildManifest as any).backend_version = "0.3.1";

    expect(client.needsUpdate).toBe(false);
    expect(client.backendVersion).toBe("unknown");
    
    await client.checkBackendVersion();
    
    expect(client.backendVersion).toBe("0.3.1");
    expect(client.needsUpdate).toBe(false);

    // restore
    Object.assign(localBuildManifest, originalManifest);
  });

  it("does not request setup when backend_version matches local manifest", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.2",
    }));
    
    const originalManifest = JSON.parse(JSON.stringify(localBuildManifest));
    (localBuildManifest as any).backend_version = "0.3.2";

    await client.checkBackendVersion();

    expect(client.needsUpdate).toBe(false);
    expect(client.updateMessage).toBe("");
    
    Object.assign(localBuildManifest, originalManifest);
  });

  it("requests setup when backend version and local manifest expected version differ", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.3",
    }));

    const originalManifest = JSON.parse(JSON.stringify(localBuildManifest));
    (localBuildManifest as any).backend_version = "0.3.2"; // Expected 0.3.2, got 0.3.3

    await client.checkBackendVersion();

    expect(client.needsUpdate).toBe(true);
    expect(client.updateMessage).toContain("backend version mismatch");
    expect(client.updateActionLabel).toBe("Run Setup");

    Object.assign(localBuildManifest, originalManifest);
  });

  it("registerSource calls plugin source import then plugin source register with --build", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      if (args[2] === "import") {
        return {
          ok: true,
          source_id: 42,
          relpath: "04_Resources/References/paper.md",
        };
      }
      return {
        ok: true,
        state: "l1_ready",
        source_id: 42,
        context_id: "CTX-abc",
        l2_l3_queued: true,
      };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);
    const status = await client.registerSource("/tmp/paper.pdf");

    expect(status).not.toBeNull();
    expect(calls.length).toBe(2);
    expect(calls[0]).toEqual([
      "plugin",
      "source",
      "import",
      "--file-path",
      "/tmp/paper.pdf",
      "--destination",
      "04_Resources",
      "--policy",
      "reference",
    ]);
    expect(calls[1]).toEqual([
      "plugin",
      "source",
      "register",
      "--source-id",
      "42",
      "--relpath",
      "04_Resources/References/paper.md",
      "--build",
    ]);
  });

  it("ingestPdf returns an error status when backend import fails", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: false, error: "File not found" };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    const status = await client.ingestPdf({
      sourcePath: "/tmp/missing.pdf",
      destinationRelpath: "04_Resources",
      importMode: "reference",
    });

    expect(status.state).toBe("error");
    expect(status.message).toBe("File not found");
    expect(calls.length).toBe(1);
  });

  it("ingestPdf can import by Zotero attachment key without a plugin-resolved path", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      if (args[2] === "import") {
        return {
          ok: true,
          source_id: 7,
          relpath: "04_Resources/References/paper.md",
          source_path: "/Users/me/Zotero/storage/ATT/paper.pdf",
        };
      }
      return { ok: true, state: "queued", source_id: 7, l2_l3_queued: true };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    const status = await client.ingestPdf({
      zoteroAttachmentKey: "ATT",
      destinationRelpath: "",
      importMode: "reference",
    });

    expect(status.sourceId).toBe(7);
    expect(status.state).toBe("queued");
    expect(calls[0]).toEqual([
      "plugin",
      "source",
      "import",
      "--zotero-attachment-key",
      "ATT",
      "--zotero-custom-paths",
      "~/Zotero",
      "--destination",
      "",
      "--policy",
      "reference",
    ]);
  });

  it("calls hidden plugin git commands for status, history, and push", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      if (args.includes("history")) {
        return { ok: true, file_path: "note.md", commits: [] };
      }
      if (args.includes("push")) {
        return { ok: true, branch: "main", upstream: "origin/main" };
      }
      return { ok: true, repo: { is_repo: true, branch: "main" } };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);

    await client.getGitStatus();
    await client.getGitHistory("/vault/note.md", "selected phrase", 7);
    await client.pushGitChanges();

    expect(calls).toEqual([
      ["plugin", "git", "status"],
      [
        "plugin",
        "git",
        "history",
        "--file-path",
        "/vault/note.md",
        "--query",
        "selected phrase",
        "--limit",
        "7",
      ],
      ["plugin", "git", "push"],
    ]);
  });

  it("getPdfContext can call backend with source identity instead of only a file path", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return {
        ok: true,
        pages: [{ page_num: 2, text: "context", score: 0 }],
        outline: [],
        total_pages: 10,
        source_tracked: true,
        is_empty_pdf: false,
      };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    const result = await client.getPdfContext({
      sourceId: 42,
      fileHash: "abc",
      zoteroAttachmentKey: "ZKEY123",
      pageNum: 2,
    });

    expect(result?.sourceTracked).toBe(true);
    expect(calls[0]).toEqual([
      "plugin",
      "pdf",
      "context",
      "--query",
      "",
      "--page-num",
      "2",
      "--radius",
      "2",
      "--max-pages",
      "8",
      "--source-id",
      "42",
      "--file-hash",
      "abc",
      "--zotero-attachment-key",
      "ZKEY123",
    ]);
  });

  it("curatorQuery preserves route and trace identity", async () => {
    const calls: string[][] = [];
    const client = new IncuratorClient(settings(), "0.2.2", async (args: string[]) => {
      calls.push(args);
      return {
        ok: true,
        question: "What does CON-1 imply?",
        input_language: "English",
        english_query: "What does CON-1 imply?",
        final_output_language: "English",
        answer: "It implies a geometric constraint.",
        route: "local",
        trace_id: "QTR-1234abcd",
        trace: {
          matched_concepts: ["CON-1234abcd"],
          source_ids: [7],
          source_paths: ["03_Concepts/CON-1234abcd.md"],
          latency_ms: 42,
          l3_complete: true,
        },
      };
    });

    const result = await client.curatorQuery("What does CON-1 imply?", {
      workspacePath: "/tmp/workspace",
      inputLanguage: "English",
      englishQuery: "What does CON-1 imply?",
      finalOutputLanguage: "English",
    });

    expect(calls[0]).toEqual([
      "plugin",
      "query",
      "--question",
      "What does CON-1 imply?",
      "--input-language",
      "English",
      "--english-query",
      "What does CON-1 imply?",
      "--final-output-language",
      "English",
      "--workspace-path",
      "/tmp/workspace",
    ]);
    expect(result.ok).toBe(true);
    expect(result.input_language).toBe("English");
    expect(result.english_query).toBe("What does CON-1 imply?");
    expect(result.final_output_language).toBe("English");
    expect(result.trace_id).toBe("QTR-1234abcd");
    expect(result.trace?.matched_concepts).toEqual(["CON-1234abcd"]);
    expect(result.trace?.l3_complete).toBe(true);
  });

  it("routes Zotero status, init, search, metadata, annotations, and PDF resolve through backend plugin commands", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      if (args[2] === "status" || args[2] === "init") {
        return { ok: true, state: "ready", db_path: "/Users/me/Zotero/zotero.sqlite", roots_checked: [] };
      }
      if (args[2] === "search") return { ok: true, items: [{ key: "ITEM1" }] };
      if (args[2] === "metadata") return { ok: true, metadata: { title: "Paper" } };
      if (args[2] === "annotations") return { ok: true, annotations: [{ key: "ANN1" }] };
      return { ok: true, path: "/Users/me/Zotero/storage/ATT/paper.pdf" };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    await client.getZoteroStatus();
    await client.initZotero("~/Zotero");
    await client.searchZoteroItems("paper", 3);
    await client.getZoteroItemMetadata("ITEM1", "apa");
    await client.getZoteroAnnotations("ATT");
    const resolved = await client.resolveZoteroPdf("ATT");

    expect(resolved.path).toBe("/Users/me/Zotero/storage/ATT/paper.pdf");
    expect(calls).toEqual([
      ["plugin", "zotero", "status", "--custom-paths", "~/Zotero"],
      ["plugin", "zotero", "init", "--data-dir", "~/Zotero", "--custom-paths", "~/Zotero"],
      ["plugin", "zotero", "search", "--query", "paper", "--limit", "3", "--custom-paths", "~/Zotero"],
      ["plugin", "zotero", "metadata", "--item-key", "ITEM1", "--citation-style", "apa", "--custom-paths", "~/Zotero"],
      ["plugin", "zotero", "annotations", "--attachment-key", "ATT", "--custom-paths", "~/Zotero"],
      ["plugin", "zotero", "resolve-pdf", "--attachment-key", "ATT", "--custom-paths", "~/Zotero"],
    ]);
  });

  it("normalizes structured Zotero PDF resolution failures", async () => {
    const client = new IncuratorClient(settings(), "0.2.2", async () => ({
      ok: false,
      state: "attachment_file_missing",
      error: "Zotero attachment file not found",
      zotero_db: "/Users/me/Zotero/zotero.sqlite",
      roots_checked: ["/Users/me/Zotero", "/Users/me/ZoteroLinked"],
      paths_checked: ["/Users/me/ZoteroLinked/paper.pdf"],
    }));

    const result = await client.resolveZoteroPdf("ATT");

    expect(result.ok).toBe(false);
    expect(result.state).toBe("attachment_file_missing");
    expect(result.zoteroDb).toBe("/Users/me/Zotero/zotero.sqlite");
    expect(result.rootsChecked).toEqual(["/Users/me/Zotero", "/Users/me/ZoteroLinked"]);
    expect(result.pathsChecked).toEqual(["/Users/me/ZoteroLinked/paper.pdf"]);
  });

  it("registerSource returns null when incuratorEnabled is false", async () => {
    const s = settings();
    s.incuratorEnabled = false;
    const client = new IncuratorClient(s);
    const result = await client.registerSource("/tmp/paper.pdf");
    expect(result).toBeNull();
  });

  it("dbAutosync calls the backend and maps stats", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return {
        dry_run: false,
        imported_files: 2,
        inserted: 3,
        updated: 1,
        deleted: 0,
        conflicts: ["dev-x.sync-conflict-20260607-1.jsonl"],
        exported: "dev-self.jsonl",
      };
    };
    const client = new IncuratorClient(settings(), "0.4.0", backendJson);
    const res = await client.dbAutosync();
    expect(calls[0]).toEqual(["db", "autosync", "--json", "--skip-reindex"]);
    expect(res.ok).toBe(true);
    expect(res.inserted).toBe(3);
    expect(res.importedFiles).toBe(2);
    expect(res.conflicts).toEqual(["dev-x.sync-conflict-20260607-1.jsonl"]);
    expect(res.exported).toBe("dev-self.jsonl");
  });

  it("dbAutosync short-circuits when backend disabled", async () => {
    const s = settings();
    s.incuratorEnabled = false;
    const client = new IncuratorClient(s);
    const res = await client.dbAutosync();
    expect(res.ok).toBe(false);
    expect(res.error).toBe("backend_disabled");
  });

});
