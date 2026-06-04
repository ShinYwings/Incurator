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

  it("formatCuratorQueryResult wraps answer in incurator_answer with route/trace attrs", () => {
    const out = formatCuratorQueryResult(
      { ok: true, answer: "hello", route: "global", trace_id: "QTR-1" } as never,
      "q",
    );
    expect(out).toContain('<incurator_answer query="q"');
    expect(out).toContain('route="global"');
    expect(out).toContain('trace="QTR-1"');
    expect(out).toContain("hello");
    expect(out.trim().endsWith("</incurator_answer>")).toBe(true);
  });

  it("formatCuratorQueryResult exposes input/query metadata but not stale output language", () => {
    const out = formatCuratorQueryResult(
      {
        ok: true,
        question: "이 논문의 핵심이 뭐야?",
        answer: "핵심 답변",
        input_language: "Korean",
        english_query: "What is the core idea of this paper?",
        final_output_language: "Korean",
      } as never,
      "이 논문의 핵심이 뭐야?",
    );

    expect(out).toContain('input_language="Korean"');
    expect(out).toContain('english_query="What is the core idea of this paper?"');
    expect(out).not.toContain("final_output_language");
  });
});
