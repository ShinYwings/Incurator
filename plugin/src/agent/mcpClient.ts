import { spawn, ChildProcess } from "child_process";
import { Notice } from "obsidian";
import type { MCPServerConfig, MCPTool, MCPToolResult } from "../types";

// ─── JSON-RPC 2.0 Types ────────────────────────────────────────

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

// ─── MCP Client ─────────────────────────────────────────────────

export class MCPClient {
  private config: MCPServerConfig;
  private process: ChildProcess | null = null;
  private nextId = 1;
  private pending = new Map<
    number,
    {
      resolve: (value: unknown) => void;
      reject: (reason: unknown) => void;
    }
  >();
  private buffer = "";
  private _tools: MCPTool[] = [];
  private _ready = false;

  constructor(config: MCPServerConfig) {
    this.config = config;
  }

  get name(): string {
    return this.config.name;
  }

  get tools(): MCPTool[] {
    return this._tools;
  }

  get ready(): boolean {
    return this._ready;
  }

  /**
   * Spawn the MCP server process and initialize the connection.
   */
  async start(): Promise<void> {
    if (this.process) {
      await this.shutdown();
    }

    return new Promise((resolve, reject) => {
      try {
        this.process = spawn(this.config.command, this.config.args, {
          stdio: ["pipe", "pipe", "pipe"],
          env: { ...process.env, ...this.config.env },
        });

        this.process.stdout?.on("data", (data: Buffer) => {
          this.onData(data.toString("utf-8"));
        });

        this.process.stderr?.on("data", (data: Buffer) => {
          console.warn(`[MCP:${this.config.name}] stderr:`, data.toString());
        });

        this.process.on("error", (err) => {
          console.error(`[MCP:${this.config.name}] process error:`, err);
          this._ready = false;
          reject(err);
        });

        this.process.on("exit", (code) => {
          console.log(`[MCP:${this.config.name}] exited with code ${code}`);
          this._ready = false;
          this.process = null;
          // Reject all pending requests
          for (const [, pending] of this.pending) {
            pending.reject(new Error(`MCP process exited with code ${code}`));
          }
          this.pending.clear();
        });

        // Initialize after a short delay to let the process start
        setTimeout(async () => {
          try {
            await this.initialize();
            await this.refreshTools();
            this._ready = true;
            resolve();
          } catch (err) {
            reject(err);
          }
        }, 500);
      } catch (err) {
        reject(err);
      }
    });
  }

  /**
   * Send the MCP initialize handshake.
   */
  private async initialize(): Promise<void> {
    await this.sendRequest("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: {
        name: "incurator-obsidian-agent",
        version: "0.1.0",
      },
    });

    // Send initialized notification (no response expected)
    this.sendNotification("notifications/initialized", {});
  }

  /**
   * Refresh the list of available tools.
   */
  async refreshTools(): Promise<MCPTool[]> {
    const result = (await this.sendRequest("tools/list", {})) as {
      tools?: MCPTool[];
    };
    this._tools = result?.tools || [];
    return this._tools;
  }

  /**
   * Call an MCP tool by name.
   */
  async callTool(
    name: string,
    args: Record<string, unknown>
  ): Promise<MCPToolResult> {
    const result = (await this.sendRequest("tools/call", {
      name,
      arguments: args,
    })) as MCPToolResult;
    return result;
  }

  /**
   * Gracefully shut down the MCP server.
   */
  async shutdown(): Promise<void> {
    if (!this.process) return;

    try {
      this.sendNotification("notifications/cancelled", {});
      // Give it a moment to clean up
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          this.process?.kill("SIGTERM");
          resolve();
        }, 2000);

        this.process?.on("exit", () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    } catch {
      this.process?.kill("SIGKILL");
    } finally {
      this.process = null;
      this._ready = false;
      this.pending.clear();
    }
  }

  // ── Internal Protocol ─────────────────────────────────────────

  private sendRequest(
    method: string,
    params: Record<string, unknown>
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.process?.stdin?.writable) {
        reject(new Error("MCP process stdin not writable"));
        return;
      }

      const id = this.nextId++;
      const request: JsonRpcRequest = {
        jsonrpc: "2.0",
        id,
        method,
        params,
      };

      this.pending.set(id, { resolve, reject });

      const data = JSON.stringify(request) + "\n";
      this.process.stdin.write(data);

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`MCP request ${method} timed out`));
        }
      }, 30000);
    });
  }

  private sendNotification(
    method: string,
    params: Record<string, unknown>
  ): void {
    if (!this.process?.stdin?.writable) return;
    const msg = JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n";
    this.process.stdin.write(msg);
  }

  private onData(raw: string): void {
    this.buffer += raw;

    // Process complete lines (newline-delimited JSON)
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      try {
        const msg = JSON.parse(trimmed) as JsonRpcResponse;
        if (msg.id !== undefined && this.pending.has(msg.id)) {
          const handler = this.pending.get(msg.id)!;
          this.pending.delete(msg.id);
          if (msg.error) {
            handler.reject(
              new Error(`MCP error: ${msg.error.message} (${msg.error.code})`)
            );
          } else {
            handler.resolve(msg.result);
          }
        }
      } catch {
        // Not valid JSON, skip
      }
    }
  }
}

// ─── MCP Manager ────────────────────────────────────────────────

export class MCPManager {
  private clients = new Map<string, MCPClient>();

  async start(config: MCPServerConfig): Promise<void> {
    if (!config.enabled || !config.command) return;
    const existing = this.clients.get(config.name);
    if (existing) {
      await existing.shutdown();
      this.clients.delete(config.name);
    }

    try {
      const client = new MCPClient(config);
      await client.start();
      this.clients.set(config.name, client);
      new Notice(`MCP server "${config.name}" started`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`Failed to start MCP server ${config.name}:`, msg);
      new Notice(`MCP server "${config.name}" failed: ${msg}`);
    }
  }

  /**
   * Start all enabled MCP servers.
   */
  async startAll(configs: MCPServerConfig[]): Promise<void> {
    for (const config of configs) {
      await this.start(config);
    }
  }

  async shutdown(serverName: string): Promise<void> {
    const client = this.clients.get(serverName);
    if (!client) return;
    await client.shutdown();
    this.clients.delete(serverName);
  }

  /**
   * Get all available tools across all running MCP servers.
   */
  getAllTools(): Array<MCPTool & { serverName: string }> {
    const tools: Array<MCPTool & { serverName: string }> = [];
    for (const [name, client] of this.clients) {
      if (!client.ready) continue;
      for (const tool of client.tools) {
        tools.push({ ...tool, serverName: name });
      }
    }
    return tools;
  }

  /**
   * Call a tool on the appropriate MCP server.
   */
  async callTool(
    serverName: string,
    toolName: string,
    args: Record<string, unknown>
  ): Promise<MCPToolResult> {
    const client = this.clients.get(serverName);
    if (!client || !client.ready) {
      throw new Error(`MCP server "${serverName}" is not available`);
    }
    return client.callTool(toolName, args);
  }

  /**
   * Shut down all MCP servers.
   */
  async shutdownAll(): Promise<void> {
    const promises: Promise<void>[] = [];
    for (const [, client] of this.clients) {
      promises.push(client.shutdown());
    }
    await Promise.all(promises);
    this.clients.clear();
  }
}
