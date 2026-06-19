import { describe, it, expect, vi } from "vitest";
import {
  parseCuratorTarget,
  rewriteCuratorLinks,
  type RewriteDeps,
} from "./curatorWikilinks";

describe("parseCuratorTarget", () => {
  it("resolves all four layers (bare layer/ID form)", () => {
    const cases: Array<[string, string, string]> = [
      ["01_Contexts/CTX-a1b2c3d4", "01_Contexts", "CTX-a1b2c3d4"],
      ["02_Atoms/ATM-9f8e7d6c", "02_Atoms", "ATM-9f8e7d6c"],
      ["03_Concepts/CON-12345678", "03_Concepts", "CON-12345678"],
      ["04_Synthesis/SYN-abcdef01", "04_Synthesis", "SYN-abcdef01"],
    ];
    for (const [href, layer, id] of cases) {
      const t = parseCuratorTarget(href);
      expect(t, href).not.toBeNull();
      expect(t!.layer).toBe(layer);
      expect(t!.id).toBe(id);
      expect(t!.path).toBe(`.curator/Collections/${layer}/${id}.md`);
      expect(t!.linktext).toBe(`.curator/Collections/${layer}/${id}.md`);
    }
  });

  it("accepts the .curator/Collections/ prefix", () => {
    const t = parseCuratorTarget(".curator/Collections/02_Atoms/ATM-9f8e7d6c");
    expect(t).not.toBeNull();
    expect(t!.path).toBe(".curator/Collections/02_Atoms/ATM-9f8e7d6c.md");
  });

  it("accepts a trailing .md suffix", () => {
    const t = parseCuratorTarget("02_Atoms/ATM-9f8e7d6c.md");
    expect(t).not.toBeNull();
    expect(t!.path).toBe(".curator/Collections/02_Atoms/ATM-9f8e7d6c.md");
  });

  it("preserves a heading / block subpath in linktext, not in path", () => {
    const heading = parseCuratorTarget("03_Concepts/CON-12345678#Relations");
    expect(heading!.path).toBe(".curator/Collections/03_Concepts/CON-12345678.md");
    expect(heading!.subpath).toBe("#Relations");
    expect(heading!.linktext).toBe(
      ".curator/Collections/03_Concepts/CON-12345678.md#Relations"
    );
    const block = parseCuratorTarget("02_Atoms/ATM-9f8e7d6c#^abc123");
    expect(block!.subpath).toBe("#^abc123");
  });

  it("strips a defensive |alias", () => {
    const t = parseCuratorTarget("02_Atoms/ATM-9f8e7d6c|My Atom");
    expect(t).not.toBeNull();
    expect(t!.id).toBe("ATM-9f8e7d6c");
  });

  it("handles UUID-style IDs with internal hyphens", () => {
    const t = parseCuratorTarget("04_Synthesis/SYN-abcdef01-2345-6789");
    expect(t).not.toBeNull();
    expect(t!.id).toBe("SYN-abcdef01-2345-6789");
  });

  it("rejects a layer/prefix mismatch", () => {
    expect(parseCuratorTarget("02_Atoms/CON-12345678")).toBeNull();
    expect(parseCuratorTarget("01_Contexts/SYN-abcdef01")).toBeNull();
  });

  it("rejects non-curator and malformed targets", () => {
    expect(parseCuratorTarget(null)).toBeNull();
    expect(parseCuratorTarget(undefined)).toBeNull();
    expect(parseCuratorTarget("")).toBeNull();
    expect(parseCuratorTarget("PHASE:ANALYSED")).toBeNull();
    expect(parseCuratorTarget("https://example.com")).toBeNull();
    expect(parseCuratorTarget("03_Notes/Some Note")).toBeNull();
    expect(parseCuratorTarget("02_Atoms/ATM-")).toBeNull();
    expect(parseCuratorTarget("05_Assets/02_Atoms/ATM-9f8e7d6c")).toBeNull();
  });
});

// ── Minimal fake DOM (vitest runs in a node env with no DOM) ──────────────────
interface FakeAnchor {
  _attrs: Record<string, string>;
  dataset: Record<string, string>;
  _classes: Set<string>;
  classList: {
    add: (c: string) => void;
    remove: (c: string) => void;
    contains: (c: string) => boolean;
  };
  _click: ((e: { preventDefault: () => void; stopPropagation: () => void }) => void) | null;
  getAttribute: (name: string) => string | null;
  addEventListener: (
    type: string,
    h: (e: { preventDefault: () => void; stopPropagation: () => void }) => void
  ) => void;
  click: () => void;
}

function fakeAnchor(attrs: Record<string, string>): FakeAnchor {
  const classes = new Set<string>((attrs.class ?? "").split(/\s+/).filter(Boolean));
  const a: FakeAnchor = {
    _attrs: attrs,
    dataset: {},
    _classes: classes,
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
    _click: null,
    getAttribute: (name) => (name in attrs ? attrs[name] : null),
    addEventListener: (type, h) => {
      if (type === "click") a._click = h;
    },
    click: () => {
      a._click?.({ preventDefault: () => {}, stopPropagation: () => {} });
    },
  };
  return a;
}

function fakeRoot(anchors: FakeAnchor[]): HTMLElement {
  return { querySelectorAll: () => anchors } as unknown as HTMLElement;
}

describe("rewriteCuratorLinks", () => {
  function deps(existing: Set<string>): RewriteDeps & { opened: string[] } {
    const opened: string[] = [];
    return {
      opened,
      open: (lt) => opened.push(lt),
      exists: (p) => existing.has(p),
    };
  }

  it("rewrites a curator link and opens the hidden page on click", () => {
    const a = fakeAnchor({
      class: "internal-link is-unresolved",
      "data-href": "02_Atoms/ATM-9f8e7d6c",
    });
    const d = deps(new Set([".curator/Collections/02_Atoms/ATM-9f8e7d6c.md"]));
    const n = rewriteCuratorLinks(fakeRoot([a]), d);

    expect(n).toBe(1);
    expect(a.dataset.curatorTarget).toBe(".curator/Collections/02_Atoms/ATM-9f8e7d6c.md");
    expect(a.classList.contains("incurator-curator-link")).toBe(true);
    expect(a.classList.contains("is-unresolved")).toBe(false);
    expect(a.classList.contains("is-missing")).toBe(false);

    a.click();
    expect(d.opened).toEqual([".curator/Collections/02_Atoms/ATM-9f8e7d6c.md"]);
  });

  it("marks a missing target with is-missing", () => {
    const a = fakeAnchor({ class: "internal-link", "data-href": "03_Concepts/CON-12345678" });
    const d = deps(new Set());
    rewriteCuratorLinks(fakeRoot([a]), d);
    expect(a.classList.contains("is-missing")).toBe(true);
  });

  it("does not touch non-curator links", () => {
    const ext = fakeAnchor({ href: "https://example.com" });
    const vault = fakeAnchor({ class: "internal-link", "data-href": "03_Notes/My Note" });
    const phase = fakeAnchor({ class: "internal-link", "data-href": "PHASE:ANALYSED" });
    const d = deps(new Set());
    const n = rewriteCuratorLinks(fakeRoot([ext, vault, phase]), d);

    expect(n).toBe(0);
    for (const a of [ext, vault, phase]) {
      expect(a.dataset.curatorTarget).toBeUndefined();
      expect(a.classList.contains("incurator-curator-link")).toBe(false);
    }
  });

  it("is idempotent — a second pass does not re-process or double-bind", () => {
    const a = fakeAnchor({ class: "internal-link", "data-href": "02_Atoms/ATM-9f8e7d6c" });
    const d = deps(new Set([".curator/Collections/02_Atoms/ATM-9f8e7d6c.md"]));
    expect(rewriteCuratorLinks(fakeRoot([a]), d)).toBe(1);
    expect(rewriteCuratorLinks(fakeRoot([a]), d)).toBe(0);
  });
});
