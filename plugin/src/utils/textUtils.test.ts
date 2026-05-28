import { describe, it, expect } from "vitest";
import { normalizeLatexDelimiters, truncateToLength } from "./textUtils";

// ─── truncateToLength ────────────────────────────────────────────────────────

describe("truncateToLength", () => {
  it("returns content unchanged when under limit", () => {
    expect(truncateToLength("hello world", 100)).toBe("hello world");
  });

  it("returns content unchanged when exactly at limit", () => {
    const s = "a".repeat(100);
    expect(truncateToLength(s, 100)).toBe(s);
  });

  it("truncates and appends marker when over limit", () => {
    const s = "a".repeat(10);
    const result = truncateToLength(s, 5);
    expect(result).toBe("aaaaa\n\n[Context truncated at 5 characters]");
  });
});

// ─── normalizeLatexDelimiters ────────────────────────────────────────────────

describe("normalizeLatexDelimiters", () => {
  // ── Escaped-bracket conversions ─────────────────────────────────────────

  it("converts \\\\[ \\\\] to $$", () => {
    expect(normalizeLatexDelimiters("\\\\[E=mc^2\\\\]")).toBe("$$E=mc^2$$");
  });

  it("converts \\\\( \\\\) to $", () => {
    expect(normalizeLatexDelimiters("\\\\(E=mc^2\\\\)")).toBe("$E=mc^2$");
  });

  it("converts \\[ \\] to $$", () => {
    expect(normalizeLatexDelimiters("\\[E=mc^2\\]")).toBe("$$E=mc^2$$");
  });

  it("converts \\( \\) to $", () => {
    expect(normalizeLatexDelimiters("\\(E=mc^2\\)")).toBe("$E=mc^2$");
  });

  // ── Protection: code blocks must be untouched ────────────────────────────

  it("leaves fenced code blocks intact", () => {
    const input = "```\n\\[x^2\\]\n```";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("leaves inline code intact", () => {
    const input = "Use `\\(x\\)` for inline math";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("leaves existing $$ display math intact", () => {
    const input = "$$E = mc^2$$";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("leaves existing single-$ inline math intact", () => {
    const input = "So $x^2$ holds.";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  // ── Protection: markdown links and HTML must pass through unchanged ──────

  it("leaves markdown links intact", () => {
    const input = "See [link](https://example.com) for details.";
    expect(normalizeLatexDelimiters(input)).toBe(input);
  });

  it("protects HTML open/close tags but not their text content", () => {
    // <code> and </code> tags are protected; text between them is still transformed
    const input = "A <code>\\(x\\)</code> tag.";
    const result = normalizeLatexDelimiters(input);
    // The tags themselves are preserved
    expect(result).toContain("<code>");
    expect(result).toContain("</code>");
    // The \( \) inside is converted since only the tag tokens are shielded
    expect(result).toContain("$x$");
  });

  // ── Mixed content ────────────────────────────────────────────────────────

  it("converts delimiters outside code blocks but leaves code intact", () => {
    const input = "Before ```\\[x\\]``` after \\(y\\)";
    const result = normalizeLatexDelimiters(input);
    // Code block is untouched, outer \( \) is converted
    expect(result).toContain("```\\[x\\]```");
    expect(result).toContain("$y$");
  });

  it("is idempotent on already-normalised content", () => {
    const input = "Some $x^2$ and $$y = z$$ here.";
    expect(normalizeLatexDelimiters(normalizeLatexDelimiters(input))).toBe(
      normalizeLatexDelimiters(input)
    );
  });
});
