import { describe, expect, it, beforeAll, afterAll, vi } from "vitest";

// LLMClient pulls in obsidian at module load; this file only needs the one
// exported string constant from it.
vi.mock("obsidian", () => ({
  Notice: class Notice { constructor(_m: string) {} },
  requestUrl: vi.fn(async () => ({ json: {} })),
}));
import { spawn } from "child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "fs";
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
function converse(lines: object[], timeoutMs = 15000, script?: string): Promise<any[]> {
  return new Promise((resolve, reject) => {
    const proc = spawn("node", [script ?? scriptPath], { stdio: ["pipe", "pipe", "pipe"] });
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

/** A real PDF header followed by every byte value — the bytes UTF-8 destroys. */
const PDF_BYTES = Buffer.concat([
  Buffer.from("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", "binary"),
  Buffer.from(Array.from({ length: 256 }, (_, i) => i)),
  Buffer.from("\n%%EOF\n"),
]);

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
  let openScriptPath: string;

  beforeAll(async () => {
    server = createServer((req, res) => {
      if (req.url === "/x.txt") {
        res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("hello, text");
        return;
      }
      res.writeHead(200, { "Content-Type": "application/pdf" });
      res.end(PDF_BYTES);
    });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    port = (server.address() as any).port;

    // The SSRF guard blocks every address a test server can bind to, so the
    // binary path is unreachable through the shipped script. Rather than assert
    // on the refusal and CALL that a binary test -- which is what the first
    // version of this block did, and it would have passed with the binary
    // handling deleted -- take the REAL script and neuter only
    // `isBlockedAddress`. Everything under test (content-type split, buffering,
    // the disk save, the reply text) is the shipped code; the guard is
    // orthogonal and has its own spawned tests above.
    const opened = FETCH_MCP_SERVER_SCRIPT.replace(
      "function isBlockedAddress(h) {",
      "function isBlockedAddress(h) {\n  return false;"
    );
    expect(opened).not.toBe(FETCH_MCP_SERVER_SCRIPT);
    openScriptPath = join(dir, "server-open.js");
    writeFileSync(openScriptPath, opened);
  });
  afterAll(() => new Promise<void>((r) => server.close(() => r())));

  it("saves a PDF to disk with its bytes intact, instead of returning corrupted text", async () => {
    // Measured on the original implementation: a 314-byte PDF came back with 132
    // U+FFFD characters -- irreversibly destroyed, and useless as the "PDF
    // information" this tool existed to deliver. `body += chunk` coerces each
    // Buffer to UTF-8.
    const replies = await converse(
      [INIT, { jsonrpc: "2.0", id: 2, method: "tools/call",
               params: { name: "fetch_url", arguments: { url: `http://127.0.0.1:${port}/x.pdf` } } }],
      15000, openScriptPath
    );
    const text = replies[1].result.content[0].text as string;
    expect(text).not.toContain("\uFFFD");
    expect(text).toContain("binary content");
    expect(text).toContain("curator_get_pdf_context");

    const saved = /Saved to: (.+)/.exec(text);
    expect(saved, `no path in reply: ${text}`).toBeTruthy();
    const bytes = readFileSync(saved![1].trim());
    // The whole point: the file on disk is byte-identical to what was served.
    expect(Buffer.compare(bytes, PDF_BYTES)).toBe(0);
    rmSync(saved![1].trim(), { force: true });
  });

  it("still returns a textual response inline", async () => {
    const replies = await converse(
      [INIT, { jsonrpc: "2.0", id: 2, method: "tools/call",
               params: { name: "fetch_url", arguments: { url: `http://127.0.0.1:${port}/x.txt` } } }],
      15000, openScriptPath
    );
    expect(replies[1].result.content[0].text).toContain("hello, text");
  });

  it("tells the model what it actually does", async () => {
    // The description is what the model reads when deciding to call this on a
    // PDF URL. It promised "the response body as plain text" long after the tool
    // stopped doing that for binary.
    const replies = await converse([INIT, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }]);
    const description = replies[1].result.tools[0].description as string;
    expect(description).toMatch(/saved to disk/i);
    expect(description).toContain("curator_get_pdf_context");
  });
});
