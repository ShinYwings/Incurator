import { describe, it, expect, vi } from "vitest";
vi.mock("obsidian", () => ({
  Notice: class { constructor(_m: string) {} },
  normalizePath: (p: string) => p,
}));

import { IncuratorClient } from "./incuratorClient";

/** The plugin must not re-derive "what is a root" — it renders what the backend
 *  says. These tests pin the normalisation, which is the only judgment it makes. */
function clientWith(payload: unknown): IncuratorClient {
  const c = Object.create(IncuratorClient.prototype) as IncuratorClient;
  (c as unknown as { callBackendJson: (a: string[]) => Promise<unknown> }).callBackendJson =
    vi.fn().mockResolvedValue(payload);
  return c;
}

describe("accessReport", () => {
  it("carries grant_folder through — the field every prior surface dropped", async () => {
    const roots = await clientWith({
      ok: true,
      roots: [{
        label: "Zotero", path: "/icloud/Zotero", state: "denied",
        grant_folder: "/Users/x/Library/Mobile Documents",
        detail: "cannot be read",
      }],
    }).accessReport();
    expect(roots).toHaveLength(1);
    expect(roots[0].grantFolder).toBe("/Users/x/Library/Mobile Documents");
    expect(roots[0].state).toBe("denied");
  });

  it("keeps not_downloaded distinct from denied, and offers no folder", async () => {
    const roots = await clientWith({
      ok: true,
      roots: [{ label: "P", path: "/p.pdf", state: "not_downloaded", grant_folder: "", detail: "d" }],
    }).accessReport();
    expect(roots[0].state).toBe("not_downloaded");
    expect(roots[0].grantFolder).toBe("");
  });

  it("returns [] when the backend is offline rather than throwing", async () => {
    expect(await clientWith(null).accessReport()).toEqual([]);
  });

  it("drops rows with no path instead of rendering a blank button", async () => {
    const roots = await clientWith({ ok: true, roots: [{ label: "x" }, { path: "/ok", state: "ok" }] })
      .accessReport();
    expect(roots.map((r) => r.path)).toEqual(["/ok"]);
  });
});
