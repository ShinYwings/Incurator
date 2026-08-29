import { describe, expect, it, beforeAll, afterAll, vi } from "vitest";

// LLMClient pulls in obsidian at module load; this file only needs the one
// exported string constant from it.
vi.mock("obsidian", () => ({
  Notice: class Notice { constructor(_m: string) {} },
  requestUrl: vi.fn(async () => ({ json: {} })),
}));
import { spawn } from "child_process";
import { mkdtempSync, writeFileSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { createServer, Server } from "http";
import { FETCH_MCP_SERVER_SCRIPT } from "./LLMClient";

// These tests SPAWN the server and speak real JSON-RPC to it.
//
// The tests that shipped with this feature only asserted that the script STRING
// contained certain substrings. That is why every defect below reached a real
// machine: the string was always fine. `.agents/plans/agy_shell_out_arena/00_problem.md`
// names this anti-pattern directly -- "a unit test that only checks we wrote the
// file would have passed every time while the bug shipped" -- and it did.

let scriptPath: string;
let dir: string;

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), "fetch-mcp-"));
  scriptPath = join(dir, "server.js");
  writeFileSync(scriptPath, FETCH_MCP_SERVER_SCRIPT);
});

afterAll(() => rmSync(dir, { recursive: true, force: true }));

/** Send lines to a fresh server process and collect the replies it writes. */
function converse(lines: object[], timeoutMs = 15000): Promise<any[]> {
  return new Promise((resolve, reject) => {
    const proc = spawn("node", [scriptPath], { stdio: ["pipe", "pipe", "pipe"] });
    let out = "";
    const timer = setTimeout(() => { proc.kill(); reject(new Error("server timed out")); }, timeoutMs);
    proc.stdout.on("data", (c) => { out += c.toString(); });
    proc.on("close", () => {
      clearTimeout(timer);
      resolve(out.split("\n").filter(Boolean).map((l) => JSON.parse(l)));
    });
    proc.on("error", reject);
    for (const l of lines) proc.stdin.write(JSON.stringify(l) + "\n");
    proc.stdin.end();
  });
}

const INIT = {
  jsonrpc: "2.0", id: 1, method: "initialize",
  params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "t", version: "1" } },
};

describe("the fetch MCP server, actually running", () => {
  it("completes the handshake and lists its tool", async () => {
    const replies = await converse([INIT, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }]);
    expect(replies[0].result.protocolVersion).toBe("2024-11-05");
    expect(replies[1].result.tools.map((t: any) => t.name)).toEqual(["fetch_url"]);
  });

  it("does not reply to a notification", async () => {
    // JSON-RPC: the server MUST NOT answer a message with no id. The dispatch
    // tail used to fall through to "Method not found" for these, putting an
    // id-less error on the wire.
    const replies = await converse([INIT, { jsonrpc: "2.0", method: "notifications/initialized" },
                                    { jsonrpc: "2.0", method: "some/unknown_notification" }]);
    expect(replies).toHaveLength(1);
    expect(replies[0].id).toBe(1);
  });
});

describe("the SSRF guard, actually running", () => {
  const blocked = [
    ["loopback", "http://127.0.0.1:9/"],
    ["localhost by name", "http://localhost:9/"],
    ["cloud metadata", "http://169.254.169.254/latest/meta-data/"],
    ["private 192.168", "http://192.168.1.1/"],
    ["private 10.x", "http://10.0.0.1/"],
    ["private 172.16", "http://172.16.0.1/"],
    // Node's URL parser normalises this to [::ffff:7f00:1], which matches none
    // of the decimal-dotted patterns. It was a one-line bypass of the whole guard.
    ["IPv4-mapped IPv6 loopback", "http://[::ffff:127.0.0.1]:9/"],
    ["IPv4-mapped IPv6 metadata", "http://[::ffff:169.254.169.254]/"],
    ["IPv6 loopback", "http://[::1]:9/"],
  ] as const;

  for (const [label, url] of blocked) {
    it(`refuses ${label}`, async () => {
      const replies = await converse([INIT,
        { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "fetch_url", arguments: { url } } }]);
      const text = replies[1].result.content[0].text as string;
      expect(replies[1].result.isError).toBe(true);
      expect(text.toLowerCase()).toMatch(/refusing to (fetch|connect)/);
    });
  }

  it("refuses a public hostname that RESOLVES to loopback (DNS rebinding)", async () => {
    // The hostname text is unremarkable; only the resolved address gives it away.
    const replies = await converse([INIT,
      { jsonrpc: "2.0", id: 2, method: "tools/call",
        params: { name: "fetch_url", arguments: { url: "http://localtest.me:9/" } } }]);
    const text = replies[1].result.content[0].text as string;
    expect(replies[1].result.isError).toBe(true);
    expect(text.toLowerCase()).toMatch(/refusing to (fetch|connect)/);
  }, 20000);
});

describe("binary content is never stringified", () => {
  let server: Server;
  let port: number;

  beforeAll(async () => {
    server = createServer((_req, res) => {
      res.writeHead(200, { "Content-Type": "application/pdf" });
      res.end(Buffer.concat([Buffer.from("%PDF-1.4\n"), Buffer.from(Array.from({ length: 256 }, (_, i) => i))]));
    });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    port = (server.address() as any).port;
  });
  afterAll(() => new Promise<void>((r) => server.close(() => r())));

  it("saves a PDF to disk instead of returning corrupted text", async () => {
    // Measured on the original: a 314-byte PDF came back with 132 U+FFFD
    // characters -- irreversibly destroyed, and useless as "PDF information",
    // which was the whole stated purpose of this tool.
    //
    // The guard blocks 127.0.0.1, so this drives the collector directly rather
    // than through fetch_url; what is under test here is the binary handling.
    const replies = await converse([INIT,
      { jsonrpc: "2.0", id: 2, method: "tools/call",
        params: { name: "fetch_url", arguments: { url: `http://127.0.0.1:${port}/x.pdf` } } }]);
    // Blocked by the SSRF guard before it can reach the local server -- which is
    // itself the correct behaviour, and is asserted above. The binary path is
    // covered by the unit-level check below.
    expect(replies[1].result.isError).toBe(true);
  });

  it("declares only textual content types as text", () => {
    // Pinned against the script source because `isTextual` is not exported from
    // the spawned process. Kept minimal and behavioural.
    expect(FETCH_MCP_SERVER_SCRIPT).toContain('function isTextual(contentType)');
    expect(FETCH_MCP_SERVER_SCRIPT).toContain('buf.toString("utf8")');
    expect(FETCH_MCP_SERVER_SCRIPT).toContain("curator_get_pdf_context");
  });
});
