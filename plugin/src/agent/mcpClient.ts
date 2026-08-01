import { logger } from "../utils/logger";
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

const MCP_GRACEFUL_SHUTDOWN_MS = 500;
const MCP_TERMINATE_WAIT_MS = 1500;
const MCP_FORCE_KILL_WAIT_MS = 500;

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
      timeout: ReturnType<typeof setTimeout>;
    }
  >();
  private buffer = "";
  private _tools: MCPTool[] = [];
  private _ready = false;
  private shuttingDown = false;

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
    this.shuttingDown = false;

    return new Promise((resolve, reject) => {
      let child: ChildProcess;
      let startupSettled = false;
      let startupTimer: ReturnType<typeof setTimeout> | null = null;
      const resolveStartup = () => {
        if (startupSettled) return;
        startupSettled = true;
        resolve();
      };
      const rejectStartup = (error: unknown) => {
        if (startupSettled) return;
        startupSettled = true;
        reject(error);
      };
      try {
        child = spawn(this.config.command, this.config.args, {
          stdio: ["pipe", "pipe", "pipe"],
          env: { ...process.env, ...this.config.env },
        });
        this.process = child;

        child.stdout?.on("data", (data: Buffer) => {
          this.onData(data.toString("utf-8"));
        });

        child.stderr?.on("data", (data: Buffer) => {
          logger.warn(`[MCP:${this.config.name}] stderr:`, data.toString());
        });

        child.on("error", (err) => {
          logger.error(`[MCP:${this.config.name}] process error:`, err);
          if (this.process === child) {
            this._ready = false;
            this.process = null;
            this.rejectAllPending(err);
          }
          rejectStartup(err);
        });

        child.on("exit", (code) => {
          if (startupTimer) clearTimeout(startupTimer);
          // A non-zero exit means the MCP server crashed — keep it visible
          // (warn) for troubleshooting; a clean exit stays gated (debug).
          if (code) {
            logger.warn(`[MCP:${this.config.name}] exited with code ${code}`);
          } else {
            logger.debug(`[MCP:${this.config.name}] exited with code ${code}`);
          }
          if (this.process === child) {
            this._ready = false;
            this.process = null;
            this._tools = [];
            this.rejectAllPending(
              new Error(`MCP process exited with code ${code}`),
            );
          }
          rejectStartup(new Error(`MCP process exited with code ${code}`));
        });

        // Initialize after a short delay to let the process start
        startupTimer = setTimeout(async () => {
          try {
            if (this.process !== child) {
              throw new Error(`MCP server "${this.config.name}" stopped during startup`);
            }
            await this.initialize();
            await this.refreshTools();
            if (this.process !== child) {
              throw new Error(`MCP server "${this.config.name}" stopped during startup`);
            }
            this._ready = true;
            resolveStartup();
          } catch (err) {
            rejectStartup(err);
            if (this.process === child && !this.shuttingDown) {
              this._ready = false;
              await this.shutdown();
            }
          }
        }, 500);
      } catch (err) {
        rejectStartup(err);
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
    const child = this.process;
    this.shuttingDown = true;
    this._ready = false;
    this.rejectAllPending(
      new Error(`MCP server "${this.config.name}" is shutting down`),
    );
    if (!child) return;

    try {
      this.sendNotification("notifications/cancelled", {});
    } catch (error) {
      logger.warn(
        `[MCP:${this.config.name}] shutdown notification failed:`,
        error,
      );
    }
    let exited = await this.waitForExit(child, MCP_GRACEFUL_SHUTDOWN_MS);
    if (!exited) {
      child.kill("SIGTERM");
      exited = await this.waitForExit(child, MCP_TERMINATE_WAIT_MS);
    }
    if (!exited) {
      child.kill("SIGKILL");
      await this.waitForExit(child, MCP_FORCE_KILL_WAIT_MS);
    }
    if (this.process === child) {
      this.process = null;
      this._tools = [];
    }
  }

  // ── Internal Protocol ─────────────────────────────────────────

  private sendRequest(
    method: string,
    params: Record<string, unknown>
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (this.shuttingDown) {
        reject(new Error(`MCP server "${this.config.name}" is shutting down`));
        return;
      }
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

      const timeout = setTimeout(() => {
        const pending = this.pending.get(id);
        if (!pending) return;
        this.pending.delete(id);
        pending.reject(new Error(`MCP request ${method} timed out`));
      }, 30000);
      this.pending.set(id, { resolve, reject, timeout });

      const data = JSON.stringify(request) + "\n";
      try {
        this.process.stdin.write(data);
      } catch (error) {
        clearTimeout(timeout);
        this.pending.delete(id);
        reject(error);
      }
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
          clearTimeout(handler.timeout);
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

  private rejectAllPending(error: Error): void {
    const pendingRequests = Array.from(this.pending.values());
    this.pending.clear();
    for (const pending of pendingRequests) {
      clearTimeout(pending.timeout);
      pending.reject(error);
    }
  }

  private waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
    if (child.exitCode !== null) return Promise.resolve(true);
    return new Promise((resolve) => {
      let settled = false;
      const finish = (exited: boolean) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        child.off("exit", onExit);
        resolve(exited);
      };
      const onExit = () => finish(true);
      const timeout = setTimeout(() => finish(false), timeoutMs);
      child.once("exit", onExit);
    });
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
      logger.error(`Failed to start MCP server ${config.name}:`, msg);
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
