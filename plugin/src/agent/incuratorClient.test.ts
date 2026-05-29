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
    antigravityPrintTimeoutSec: 300,
    providerUsage: {
      antigravity: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
      claude: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
      openai: { requests: 0, inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0 },
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
    zoteroBasePath: "~/Zotero",
    zoteroProfiles: [],
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
                    id: "gemini",
                    label: "Gemini",
                    tier: "flash",
                    supports_vision: true,
                    context_window: 1000000,
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
      id: "gemini",
      tier: "flash",
      supportsVision: true,
      contextWindow: 1000000,
    });
  });
});
