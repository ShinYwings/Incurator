import { describe, expect, it, vi } from "vitest";

// incuratorClient pulls in the Zotero asset-localization helpers, whose module
// chain imports "obsidian" at runtime (templateRenderer); mock it for node.
vi.mock("obsidian", () => ({ moment: (value: string) => ({ format: () => value }) }));

import { IncuratorClient } from "./incuratorClient";
import type { PluginSettings } from "../types";

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

describe("IncuratorClient v0.3.1 curation-native methods", () => {
  it("getCuratePlan calls the hidden plugin curate plan command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, planId: "PLAN-1", workspaceId: "Lab", route: "local",
               selectedSources: ["03_Notes/**"], allowedModes: ["local", "global"] };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);
    const plan = await client.getCuratePlan("/v/01_Workspaces/Lab");
    expect(calls[0]).toEqual(["plugin", "curate", "plan", "--workspace-path", "/v/01_Workspaces/Lab"]);
    expect(plan.ok).toBe(true);
    expect(plan.planId).toBe("PLAN-1");
    expect(plan.route).toBe("local");
  });

  it("getPromptTrace calls the hidden plugin prompt trace command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, traceId: "PTR-1", promptId: "curator.x", validatorStatus: "ok" };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);
    const trace = await client.getPromptTrace("PTR-1");
    expect(calls[0]).toEqual(["plugin", "prompt", "trace", "--trace-id", "PTR-1"]);
    expect(trace.promptId).toBe("curator.x");
    expect(trace.validatorStatus).toBe("ok");
  });

  it("listInsightCandidates calls the hidden plugin insight list command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, candidates: [
        { id: "INS-1", classification: "derived_insight", statement: "X~Y",
          status: "pending", affectedNodeIds: ["CON-1"], confidence: 0.6 }] };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);
    const res = await client.listInsightCandidates("/v/01_Workspaces/Lab");
    expect(calls[0]).toEqual([
      "plugin", "insight", "list", "--workspace-path", "/v/01_Workspaces/Lab", "--status", "pending",
    ]);
    expect(res.candidates).toHaveLength(1);
    expect(res.candidates[0].id).toBe("INS-1");
  });

  it("promoteInsight calls the hidden plugin insight promote command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, insightId: "INS-1", promotedTo: "02_Wiki/x.md" };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);
    const res = await client.promoteInsight("INS-1", "/v/01_Workspaces/Lab");
    expect(calls[0]).toEqual([
      "plugin", "insight", "promote", "--insight-id", "INS-1", "--workspace-path", "/v/01_Workspaces/Lab",
    ]);
    expect(res.promotedTo).toBe("02_Wiki/x.md");
  });

  it("listSynthesisNodes calls the hidden plugin synthesis list command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, synthesis: [
        { id: "SYN-1", title: "S", confidence: 0.8, sourceSpanIds: ["SPAN-1"], communityReportIds: ["REP-1"] },
      ] };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);
    const res = await client.listSynthesisNodes("/v/01_Workspaces/Lab", 10);
    expect(calls[0]).toEqual([
      "plugin", "synthesis", "list", "--workspace-path", "/v/01_Workspaces/Lab", "--limit", "10",
    ]);
    expect(res.synthesis[0].id).toBe("SYN-1");
  });

  it("getSynthesisAudit calls the hidden plugin synthesis show command", async () => {
    const calls: string[][] = [];
    const backendJson = async (args: string[]) => {
      calls.push(args);
      return { ok: true, audit: { ok: true, kind: "synthesis", id: "SYN-1", warnings: [] } };
    };
    const client = new IncuratorClient(settings(), "0.3.1", backendJson);
    const res = await client.getSynthesisAudit("SYN-1", "/v/01_Workspaces/Lab");
    expect(calls[0]).toEqual([
      "plugin", "synthesis", "show", "--synthesis-id", "SYN-1", "--workspace-path", "/v/01_Workspaces/Lab",
    ]);
    expect(res.audit?.id).toBe("SYN-1");
  });

  it("returns graceful empties when the backend is disabled", async () => {
    const disabled = { ...settings(), incuratorEnabled: false };
    const client = new IncuratorClient(disabled, "0.3.1", async () => ({ ok: true }));
    expect((await client.getCuratePlan("/v/ws")).ok).toBe(false);
    expect((await client.listInsightCandidates("/v/ws")).candidates).toEqual([]);
    expect((await client.listSynthesisNodes("/v/ws")).synthesis).toEqual([]);
  });
});
