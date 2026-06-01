import { describe, expect, it } from "vitest";
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
    mcpServers: [],
    maxContextLength: 128000,
    ollamaHost: "http://localhost:11434",
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
  it("uses check_source_status before path-based status when a file hash is available", async () => {
    const calls: string[] = [];
    const mcp = {
      getAllTools: () => [
        { serverName: "incurator", name: "check_source_status", description: "", inputSchema: {} },
        { serverName: "incurator", name: "curator_source_status", description: "", inputSchema: {} },
      ],
      callTool: async (_server: string, tool: string) => {
        calls.push(tool);
        return {
          content: [
            {
              type: "text",
              text:
                tool === "check_source_status"
                  ? JSON.stringify({
                      registered: true,
                      source: {
                        state: "pending",
                        l1_complete: true,
                        l2_complete: false,
                        l3_complete: false,
                        jobs_pending: [{ id: 1 }],
                      },
                    })
                  : JSON.stringify({ state: "untracked" }),
            },
          ],
        };
      },
    };
    const client = new IncuratorClient(mcp as any, settings());
    const status = await client.getSourceStatus({
      sourcePath: "/tmp/paper.pdf",
      fileHash: "abc",
    });

    expect(calls[0]).toBe("check_source_status");
    expect(status.state).toBe("queued");
  });

  it("normalizes backend model catalogue responses", async () => {
    const mcp = {
      getAllTools: () => [
        { serverName: "incurator", name: "get_available_models", description: "", inputSchema: {} },
      ],
      callTool: async () => ({
        content: [
          {
            type: "text",
            text: JSON.stringify({
              ok: true,
              providers: {
                antigravity: [
                  {
                    id: "gemini-3.5-flash",
                    label: "Gemini 3.5 Flash",
                    supports_vision: true,
                    context_window: 1000000,
                    efforts: ["low", "medium", "high"],
                    default_effort: "medium",
                  },
                ],
              },
            }),
          },
        ],
      }),
    };
    const client = new IncuratorClient(mcp as any, settings());
    const catalogue = await client.getAvailableModels();
    expect(catalogue.antigravity?.[0]).toMatchObject({
      id: "gemini-3.5-flash",
      supportsVision: true,
      contextWindow: 1000000,
      efforts: ["low", "medium", "high"],
      defaultEffort: "medium",
    });
  });

  it("checks backend version and sets needsUpdate flag", async () => {
    const mcp = {
      getAllTools: () => [
        { serverName: "incurator", name: "curator_get_version", description: "", inputSchema: {} },
      ],
      callTool: async () => ({
        content: [{ type: "text", text: '"0.2.2"' }],
      }),
    };
    const client = new IncuratorClient(mcp as any, settings(), "0.2.1");
    expect(client.needsUpdate).toBe(false);
    expect(client.backendVersion).toBe("unknown");
    
    await client.checkBackendVersion();
    
    expect(client.backendVersion).toBe("0.2.2");
    expect(client.needsUpdate).toBe(true);
  });

  it("registerSource calls curator_import_source then curator_register_source with build=true", async () => {
    const calls: { tool: string; args: Record<string, unknown> }[] = [];
    const mcp = {
      getAllTools: () => [
        { serverName: "incurator", name: "curator_import_source", description: "", inputSchema: {} },
        { serverName: "incurator", name: "curator_register_source", description: "", inputSchema: {} },
      ],
      callTool: async (_server: string, tool: string, args: Record<string, unknown>) => {
        calls.push({ tool, args });
        if (tool === "curator_import_source") {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  ok: true,
                  source_id: 42,
                  relpath: "04_Resources/paper.pdf",
                }),
              },
            ],
          };
        }
        // curator_register_source response
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                ok: true,
                state: "l1_ready",
                source_id: 42,
                context_id: "CTX-abc",
                l2_l3_queued: true,
              }),
            },
          ],
        };
      },
    };
    const client = new IncuratorClient(mcp as any, settings());
    const status = await client.registerSource("/tmp/paper.pdf");

    expect(status).not.toBeNull();
    expect(calls.length).toBe(2);
    expect(calls[0].tool).toBe("curator_import_source");
    expect(calls[1].tool).toBe("curator_register_source");
    expect(calls[1].args.build).toBe(true);
  });

  it("registerSource returns null when incuratorEnabled is false", async () => {
    const mcp = {
      getAllTools: () => [],
      callTool: async () => ({ content: [] }),
    };
    const s = settings();
    s.incuratorEnabled = false;
    const client = new IncuratorClient(mcp as any, s);
    const result = await client.registerSource("/tmp/paper.pdf");
    expect(result).toBeNull();
  });
});
