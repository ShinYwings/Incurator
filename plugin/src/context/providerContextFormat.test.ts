import { describe, it, expect } from "vitest";
import {
  escapeAttribute,
  truncateForProviderContext,
  formatPdfWindow,
  formatOutline,
  formatRagHits,
  formatIncuratorHits,
  formatCuratorQueryResult,
} from "./providerContextFormat";

describe("providerContextFormat", () => {
  it("escapeAttribute escapes &, \", <", () => {
    expect(escapeAttribute('a & b "c" <d>')).toBe("a &amp; b &quot;c&quot; &lt;d>");
  });

  it("truncateForProviderContext appends marker only when over limit", () => {
    expect(truncateForProviderContext("short", 10)).toBe("short");
    expect(truncateForProviderContext("0123456789X", 10)).toBe("0123456789\n[...truncated]");
  });

  it("formatPdfWindow renders page headers", () => {
    const out = formatPdfWindow([
      { pageNum: 3, text: "alpha" },
      { pageNum: 4, text: "beta" },
    ]);
    expect(out).toBe("### Page 3\nalpha\n\n### Page 4\nbeta");
  });

  it("formatOutline indents by level and includes page", () => {
    const out = formatOutline([
      { title: "Intro", level: 0, pageNum: 1 },
      { title: "Sub", level: 1, pageNum: 2 },
    ]);
    expect(out).toBe("- Intro p.1\n  - Sub p.2");
  });

  it("formatRagHits respects topK and shows score", () => {
    const hits = [
      { pageNum: 1, score: 0.9, snippet: "one" },
      { pageNum: 2, score: 0.8, snippet: "two" },
      { pageNum: 3, score: 0.7, snippet: "three" },
    ];
    const out = formatRagHits(hits, 2);
    expect(out).toContain("p.1");
    expect(out).toContain("p.2");
    expect(out).not.toContain("p.3");
  });

  it("formatIncuratorHits builds label from title/path", () => {
    const out = formatIncuratorHits([
      { title: "T", path: "02_Atoms/ATM-1.md", snippet: "s", score: 0.5 },
    ]);
    expect(out).toContain("T");
    expect(out).toContain("02_Atoms/ATM-1.md");
    expect(out).toContain("score=0.5");
  });

  it("formatCuratorQueryResult wraps answer in incurator_answer with cache attr", () => {
    const out = formatCuratorQueryResult(
      { ok: true, answer: "hello", cache_hit: true, exhibition_id: "EXH-1" } as never,
      "q",
    );
    expect(out).toContain('<incurator_answer query="q"');
    expect(out).toContain('cache="hit"');
    expect(out).toContain('exhibition="EXH-1"');
    expect(out).toContain("hello");
    expect(out.trim().endsWith("</incurator_answer>")).toBe(true);
  });
});
