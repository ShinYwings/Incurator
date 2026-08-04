import { describe, expect, it, vi } from "vitest";

// incuratorClient pulls in the Zotero asset-localization helpers, whose module
// chain imports "obsidian" at runtime (templateRenderer); mock it for node.
vi.mock("obsidian", () => ({ moment: (value: string) => ({ format: () => value }) }));

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
    incuratorPdfAssetFolder: "",
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

  it("routes interactive PDF transcription through the backend transcribe command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, latex: "Clean $x^2$", model: "claude-code::sonnet" };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    const result = await client.transcribePdfRegion({
      imageFile: "/tmp/crop.png",
      text: "garbled x2",
    });

    expect(calls[0]).toEqual([
      "plugin",
      "pdf",
      "transcribe",
      "--image-file",
      "/tmp/crop.png",
      "--text",
      "garbled x2",
    ]);
    expect(result).toEqual({ ok: true, latex: "Clean $x^2$", model: "claude-code::sonnet", error: undefined });
  });

  it("normalizes layer status progressively and lets errors win", async () => {
    const client = new IncuratorClient(settings());
    const normalize = (value: unknown) => (client as any).normalizeStatus(value);

    expect(normalize({ state: "done", l1_status: "done" })).toMatchObject({
      state: "l1_ready",
      l1Complete: true,
      l2Complete: false,
      l3Complete: false,
      l4Complete: false,
    });
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
    // v0.42.0: identity is read from `build`, never from the top-level
    // `version` (installed package metadata). Real backends always send both.
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.2",
      build: { backend_version: "0.3.2" },
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
      build: { backend_version: "0.3.3" },
    }));

    const originalManifest = JSON.parse(JSON.stringify(localBuildManifest));
    (localBuildManifest as any).backend_version = "0.3.2"; // Expected 0.3.2, got 0.3.3

    await client.checkBackendVersion();

    expect(client.needsUpdate).toBe(true);
    expect(client.updateMessage).toContain("backend version mismatch");
    expect(client.updateActionLabel).toBe("Run Setup");

    Object.assign(localBuildManifest, originalManifest);
  });

  it("ignores stale package metadata when build identity is present", async () => {
    // The field case: an editable install froze its metadata at 0.4.3 while
    // executing current code, so gating on it produced an unclearable banner.
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.4.3",
      build: { backend_version: "0.3.2" },
    }));

    const originalManifest = JSON.parse(JSON.stringify(localBuildManifest));
    (localBuildManifest as any).backend_version = "0.3.2";

    await client.checkBackendVersion();

    expect(client.backendVersion).toBe("0.3.2");
    expect(client.needsUpdate).toBe(false);
    expect(client.updateMessage).toBe("");

    Object.assign(localBuildManifest, originalManifest);
  });

  it("reports an absent build identity instead of falling back to metadata", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.2",
    }));

    const originalManifest = JSON.parse(JSON.stringify(localBuildManifest));
    (localBuildManifest as any).backend_version = "0.3.2";

    await client.checkBackendVersion();

    expect(client.backendVersion).toBe("unknown");
    expect(client.needsUpdate).toBe(true);
    expect(client.updateMessage).toContain("did not report a build identity");

    Object.assign(localBuildManifest, originalManifest);
  });

  it("captures repo_path from backend version response", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.1",
      repo_path: "/home/shin/Workspace/Incurator",
    }));
    await client.checkBackendVersion();
    expect(client.repoPath).toBe("/home/shin/Workspace/Incurator");
  });

  it("leaves repoPath null when backend reports no repo (site-packages install)", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: true,
      version: "0.3.1",
      repo_path: null,
    }));
    await client.checkBackendVersion();
    expect(client.repoPath).toBeNull();
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
        context_source: "durable_l1_projection",
        degraded_reason: "projection_preview_only",
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
    expect(result?.contextSource).toBe("durable_l1_projection");
    expect(result?.degradedReason).toBe("projection_preview_only");
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
        pack_id: "PACK-1234abcd",
        snapshot: { snapshot_id: "SNAP-1234abcd" },
        budget: { used_tokens: 20, limit_tokens: 100 },
        prompt_trace_ids: ["PTR-1234abcd"],
        source_span_ids: ["SPAN-1234abcd"],
        trace: {
          matched_concepts: ["CON-1234abcd"],
          source_ids: [7],
          source_paths: ["03_Concepts/CON-1234abcd.md"],
          trace_id: "QTR-1234abcd",
          route: "local",
          pack_id: "PACK-1234abcd",
          snapshot: { snapshot_id: "SNAP-1234abcd" },
          budget: { used_tokens: 20, limit_tokens: 100 },
          prompt_trace_ids: ["PTR-1234abcd"],
          source_span_ids: ["SPAN-1234abcd"],
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
    expect(result.pack_id).toBe("PACK-1234abcd");
    expect(result.snapshot?.snapshot_id).toBe("SNAP-1234abcd");
    expect(result.budget?.used_tokens).toBe(20);
    expect(result.prompt_trace_ids).toEqual(["PTR-1234abcd"]);
    expect(result.source_span_ids).toEqual(["SPAN-1234abcd"]);
    expect(result.trace?.matched_concepts).toEqual(["CON-1234abcd"]);
    expect(result.trace?.pack_id).toBe("PACK-1234abcd");
    expect(result.trace?.l3_complete).toBe(true);
  });

  it("curatorQuery preserves failed QTR, PTR, provenance, and warnings", async () => {
    const client = new IncuratorClient(settings(), "0.37.1", async () => ({
      ok: false,
      question: "Why did synthesis fail?",
      error: "Antigravity CLI returned no output.",
      route: "local",
      trace_id: "QTR-failed01",
      pack_id: "PACK-failed01",
      snapshot: { snapshot_id: "SNAP-failed01" },
      budget: { used_tokens: 42, limit_tokens: 128 },
      prompt_trace_ids: ["PTR-failed01"],
      source_span_ids: ["SPAN-failed01"],
      community_report_ids: ["REP-failed01"],
      warnings: ["retrieval evidence retained"],
      trace: {
        matched_concepts: [],
        source_ids: [],
        source_paths: ["04_Resources/source.md"],
        trace_id: "QTR-failed01",
        route: "local",
        pack_id: "PACK-failed01",
        snapshot: { snapshot_id: "SNAP-failed01" },
        budget: { used_tokens: 42, limit_tokens: 128 },
        prompt_trace_ids: ["PTR-failed01"],
        source_span_ids: ["SPAN-failed01"],
        latency_ms: 12,
        l3_complete: true,
      },
    }));

    const result = await client.curatorQuery("Why did synthesis fail?");

    expect(result.ok).toBe(false);
    expect(result.error).toBe("Antigravity CLI returned no output.");
    expect(result.trace_id).toBe("QTR-failed01");
    expect(result.prompt_trace_ids).toEqual(["PTR-failed01"]);
    expect(result.source_span_ids).toEqual(["SPAN-failed01"]);
    expect(result.community_report_ids).toEqual(["REP-failed01"]);
    expect(result.warnings).toEqual(["retrieval evidence retained"]);
    expect(result.trace?.trace_id).toBe("QTR-failed01");
    expect(result.trace?.prompt_trace_ids).toEqual(["PTR-failed01"]);
  });

  it("fetchContext requests a backend evidence pack without synthesis", async () => {
    const calls: string[][] = [];
    const client = new IncuratorClient(settings(), "0.3.1", async (args: string[]) => {
      calls.push(args);
      return {
        ok: true,
        operation: "context_fetch",
        contract_version: "1",
        pack_id: "PACK-1234abcd",
        trace_id: "QTR-1234abcd",
        retrieval_execution_id: "RTR-1234abcd",
        route: "local",
        snapshot: { snapshot_id: "SNAP-1234abcd" },
        budget: { used_tokens: 20, limit_tokens: 128 },
        items: [
          {
            kind: "source_span",
            record_id: "SPAN-1234abcd",
            summary: "Residual learning",
            detail: "Residual connections ease optimization.",
            expansion_handle: "EXP-1234abcd",
            verification_handle: "VER-1234abcd",
          },
        ],
        evidence: [
          {
            id: "SPAN-1234abcd",
            kind: "source_span",
            title: "Residual learning",
            text: "Residual connections ease optimization.",
          },
        ],
        source_span_ids: ["SPAN-1234abcd"],
        warnings: [],
        next: [],
      };
    });

    const result = await client.fetchContext("What does residual learning do?", {
      workspacePath: "/tmp/workspace",
      limitTokens: 128,
    });

    expect(calls[0]).toEqual([
      "plugin",
      "context",
      "fetch",
      "--query",
      "What does residual learning do?",
      "--workspace-path",
      "/tmp/workspace",
      "--limit-tokens",
      "128",
    ]);
    expect(result.ok).toBe(true);
    expect(result.operation).toBe("context_fetch");
    expect(result.pack_id).toBe("PACK-1234abcd");
    expect(result.items?.[0]?.record_id).toBe("SPAN-1234abcd");
    expect((result as any).answer).toBeUndefined();
  });

  it("expandContext and verifyContext call hidden context commands", async () => {
    const calls: string[][] = [];
    const client = new IncuratorClient(settings(), "0.3.1", async (args: string[]) => {
      calls.push(args);
      return { ok: true, operation: args[2] === "expand" ? "context_expand" : "context_verify" };
    });

    await client.expandContext({
      packId: "PACK-1",
      handles: ["EXP-1", "EXP-2"],
      expectedSnapshotId: "SNAP-1",
      workspacePath: "/tmp/workspace",
      limitTokens: 512,
    });
    await client.verifyContext({
      packId: "PACK-1",
      verificationHandle: "VER-1",
      expectedSnapshotId: "SNAP-1",
      workspacePath: "/tmp/workspace",
    });

    expect(calls[0]).toEqual([
      "plugin",
      "context",
      "expand",
      "--pack-id",
      "PACK-1",
      "--expected-snapshot-id",
      "SNAP-1",
      "--limit-tokens",
      "512",
      "--workspace-path",
      "/tmp/workspace",
      "--handle",
      "EXP-1",
      "--handle",
      "EXP-2",
    ]);
    expect(calls[1]).toEqual([
      "plugin",
      "context",
      "verify",
      "--pack-id",
      "PACK-1",
      "--verification-handle",
      "VER-1",
      "--expected-snapshot-id",
      "SNAP-1",
      "--workspace-path",
      "/tmp/workspace",
    ]);
  });

  it("feedbackContext calls the hidden append-only feedback command", async () => {
    const calls: string[][] = [];
    const client = new IncuratorClient(settings(), "0.3.1", async (args: string[]) => {
      calls.push(args);
      return {
        ok: true,
        operation: "context_feedback",
        feedback_id: "FBK-1",
        review_status: "pending",
        ranking_or_truth_mutated: false,
      };
    });

    const result = await client.feedbackContext({
      traceId: "QTR-1",
      packId: "PACK-1",
      feedbackType: "incorrect",
      statement: "Cited span does not support the claim.",
      client: "obsidian",
      purpose: "ground",
      targetItemId: "SPAN-9",
      targetRecordId: "SPAN-9",
      reviewedSpanIds: ["SPAN-9"],
      workspacePath: "/tmp/workspace",
    });

    expect(result.ok).toBe(true);
    expect(result.feedback_id).toBe("FBK-1");
    expect(result.ranking_or_truth_mutated).toBe(false);
    expect(calls[0]).toEqual([
      "plugin",
      "context",
      "feedback",
      "--trace-id",
      "QTR-1",
      "--pack-id",
      "PACK-1",
      "--feedback-type",
      "incorrect",
      "--statement",
      "Cited span does not support the claim.",
      "--client",
      "obsidian",
      "--purpose",
      "ground",
      "--target-item-id",
      "SPAN-9",
      "--target-record-id",
      "SPAN-9",
      "--workspace-path",
      "/tmp/workspace",
      "--reviewed-span-id",
      "SPAN-9",
    ]);
  });

  it("feedbackContext is a no-op without pack id, type, or statement", async () => {
    let called = false;
    const client = new IncuratorClient(settings(), "0.3.1", async () => {
      called = true;
      return { ok: true };
    });
    const result = await client.feedbackContext({
      traceId: "QTR-1",
      packId: "",
      feedbackType: "relevant",
      statement: "x",
    });
    expect(called).toBe(false);
    expect(result.ok).toBe(false);
  });

  it("preserves snapshot conflict metadata from context commands", async () => {
    const client = new IncuratorClient(settings(), "0.3.1", async () => ({
      ok: false,
      operation: "context_expand",
      error_type: "snapshot_conflict",
      expected_snapshot_id: "SNAP-old",
      current_snapshot_id: "SNAP-new",
      resolution: "refetch_or_rebase",
    }));

    const result = await client.expandContext({
      packId: "PACK-1",
      handles: ["EXP-1"],
      expectedSnapshotId: "SNAP-old",
    });

    expect(result.ok).toBe(false);
    expect(result.error_type).toBe("snapshot_conflict");
    expect(result.expected_snapshot_id).toBe("SNAP-old");
    expect(result.current_snapshot_id).toBe("SNAP-new");
    expect(result.resolution).toBe("refetch_or_rebase");
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
      ["plugin", "zotero", "status"],
      ["plugin", "zotero", "init", "--data-dir", "~/Zotero"],
      ["plugin", "zotero", "search", "--query", "paper", "--limit", "3"],
      ["plugin", "zotero", "metadata", "--item-key", "ITEM1", "--citation-style", "apa"],
      ["plugin", "zotero", "annotations", "--attachment-key", "ATT"],
      ["plugin", "zotero", "resolve-pdf", "--attachment-key", "ATT"],
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

  it("dbAutosync maps a structured backend failure without merged stats", async () => {
    const client = new IncuratorClient(settings(), "0.36.2", async () => ({
      ok: false,
      error: "Peer dev-broken.jsonl import failed",
      conflicts: ["dev-broken.sync-conflict.jsonl"],
    }));

    const res = await client.dbAutosync();

    expect(res).toEqual({ ok: false, error: "Peer dev-broken.jsonl import failed" });
    expect(res.conflicts).toBeUndefined();
    expect(res.importedFiles).toBeUndefined();
  });

  it("dbAutosync short-circuits when backend disabled", async () => {
    const s = settings();
    s.incuratorEnabled = false;
    const client = new IncuratorClient(s);
    const res = await client.dbAutosync();
    expect(res.ok).toBe(false);
    expect(res.error).toBe("backend_disabled");
  });

  // ── PDF asset routing (--asset-dir, PLUGIN_SCHEMA §1.1, v0.5.6) ──────────

  function ingestBackend(calls: string[][]) {
    return async (args: string[]) => {
      calls.push(args);
      if (args[2] === "import") {
        return { ok: true, source_id: 7, relpath: "04_Resources/paper.pdf" };
      }
      return { ok: true, state: "queued", l1_status: "done", jobs_pending: [{ id: 1 }] };
    };
  }

  it("passes --asset-dir from incuratorPdfAssetFolder for non-Zotero PDFs", async () => {
    const calls: string[][] = [];
    const s = settings();
    s.incuratorPdfAssetFolder = "05_Assets/PDF Figures";
    const client = new IncuratorClient(s, "0.2.2", ingestBackend(calls));

    await client.ingestPdf({
      filePath: "/tmp/paper.pdf",
      sourcePath: "/tmp/paper.pdf",
      destinationRelpath: "04_Resources",
      importMode: "reference",
    });

    const importCall = calls.find((c) => c[2] === "import");
    const registerCall = calls.find((c) => c[2] === "register");
    expect(importCall).not.toContain("--asset-dir");
    expect(registerCall).toContain("--asset-dir");
    expect(registerCall![registerCall!.indexOf("--asset-dir") + 1]).toBe(
      "05_Assets/PDF Figures/paper"
    );
  });

  it("sanitizes the PDF filename in the non-Zotero asset subfolder", async () => {
    const calls: string[][] = [];
    const s = settings();
    s.incuratorPdfAssetFolder = "05_Assets/PDF Figures";
    const client = new IncuratorClient(s, "0.2.2", ingestBackend(calls));

    await client.ingestPdf({
      filePath: "C:\\papers\\A B: Study?.PDF",
      sourcePath: "C:\\papers\\A B: Study?.PDF",
      destinationRelpath: "04_Resources",
      importMode: "reference",
    });

    const registerCall = calls.find((c) => c[2] === "register");
    expect(registerCall![registerCall!.indexOf("--asset-dir") + 1]).toBe(
      "05_Assets/PDF Figures/A B- Study-"
    );
  });

  it("omits --asset-dir when no asset folder resolves", async () => {
    const calls: string[][] = [];
    const client = new IncuratorClient(settings(), "0.2.2", ingestBackend(calls));

    await client.ingestPdf({
      filePath: "/tmp/paper.pdf",
      sourcePath: "/tmp/paper.pdf",
      destinationRelpath: "04_Resources",
      importMode: "reference",
    });

    const registerCall = calls.find((c) => c[2] === "register");
    expect(registerCall).not.toContain("--asset-dir");
  });

  it("derives the Zotero asset dir from the import profile asset spec", async () => {
    const calls: string[][] = [];
    const s = settings();
    s.incuratorPdfAssetFolder = "05_Assets/PDF Figures"; // must NOT win for Zotero
    s.zoteroProfiles = [{
      name: "Papers",
      templatePath: "",
      outputFolder: "",
      outputSubfolder: "",
      outputFilename: "",
      assetFolder: "05_Assets/Zotero Assets",
      assetSubfolder: "{{citekey}}",
      bibliographyStyle: "",
    }];
    const client = new IncuratorClient(s, "0.2.2", ingestBackend(calls));

    await client.ingestPdf({
      sourcePath: "/zotero/storage/ABCD1234/paper.pdf",
      zoteroAttachmentKey: "ABCD1234",
      displayName: "Kim et al. 2024",
      destinationRelpath: "",
      importMode: "reference",
    });

    const registerCall = calls.find((c) => c[2] === "register");
    expect(registerCall).toContain("--asset-dir");
    expect(registerCall![registerCall!.indexOf("--asset-dir") + 1]).toBe(
      "05_Assets/Zotero Assets/Kim et al. 2024"
    );
  });

  it("falls back to the attachment key when a Zotero item has no display name", async () => {
    const calls: string[][] = [];
    const s = settings();
    s.zoteroProfiles = [{
      name: "Papers",
      templatePath: "",
      outputFolder: "",
      outputSubfolder: "",
      outputFilename: "",
      assetFolder: "05_Assets/Zotero Assets",
      assetSubfolder: "{{citekey}}",
      bibliographyStyle: "",
    }];
    const client = new IncuratorClient(s, "0.2.2", ingestBackend(calls));

    await client.ingestPdf({
      sourcePath: "/zotero/storage/ABCD1234/paper.pdf",
      zoteroAttachmentKey: "ABCD1234",
      destinationRelpath: "",
      importMode: "reference",
    });

    const registerCall = calls.find((c) => c[2] === "register");
    expect(registerCall![registerCall!.indexOf("--asset-dir") + 1]).toBe(
      "05_Assets/Zotero Assets/ABCD1234"
    );
  });

  it("promoteAnswer passes source_span_ids as a JSON array when provided", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, promoted_to: "02_Wiki/General/x.md" };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    await client.promoteAnswer("Q?", "A.", "/v", ["SPAN-a", "SPAN-b"]);

    const args = calls[0];
    expect(args.slice(0, 6)).toEqual([
      "plugin", "promote", "--question", "Q?", "--answer", "A.",
    ]);
    expect(args[args.indexOf("--source-span-ids") + 1]).toBe('["SPAN-a","SPAN-b"]');
  });

  it("promoteAnswer omits --source-span-ids when none are given", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, promoted_to: "02_Wiki/General/x.md" };
    };
    const client = new IncuratorClient(settings(), "0.2.2", backendJson);

    await client.promoteAnswer("Q?", "A.");

    expect(calls[0]).not.toContain("--source-span-ids");
  });

});
