/**
 * Normalise LaTeX delimiters from various source formats to standard
 * single-dollar / double-dollar markdown form, while leaving code blocks,
 * inline code, existing math spans, markdown links, and HTML tags untouched.
 */
export function normalizeLatexDelimiters(content: string): string {
  // Fix LLMs that output $$...$$ for inline math.
  // If $$...$$ does not contain newlines and has non-whitespace characters on the same line, convert it to $...$.
  content = content.replace(/\$\$([^\n]+?)\$\$/g, (match, math, offset, string) => {
    const before = string.substring(0, offset);
    const after = string.substring(offset + match.length);
    const isLineStart = /(^|\n)[ \t]*$/.test(before);
    const isLineEnd = /^[ \t]*(\n|$)/.test(after);
    if (isLineStart && isLineEnd) {
      return match; // It's on its own line, keep as block math
    }
    return `$${math}$`; // It's inline
  });

  const protectedBlocks: string[] = [];
  // Protect: fenced code blocks, display math, inline math, inline code, markdown links, HTML tags
  let processed = content.replace(
    /```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]*?\$\$|\$(?!\$)[^\n$]+\$|\[[^\]]*\]\([^)]*\)|<[^>]+>/g,
    (match) => {
      const token = `@@AI_AGENT_PROTECTED_${protectedBlocks.length}@@`;
      protectedBlocks.push(match);
      return token;
    }
  );

  // In JS replace(), "$" is a special marker — "$$" inserts one literal "$".
  // Use "$$$$" to insert two dollar signs (display math "$$").
  processed = processed
    .replace(/\\\\\[/g, "$$$$")
    .replace(/\\\\\]/g, "$$$$")
    .replace(/\\\\\(/g, "$$")
    .replace(/\\\\\)/g, "$$")
    .replace(/\\\[/g, "$$$$")
    .replace(/\\\]/g, "$$$$")
    .replace(/\\\(/g, "$$")
    .replace(/\\\)/g, "$$");

  const latexSpan =
    /(^|[\s([{,:;>])((?:\\?[A-Za-zΑ-ω∞][A-Za-z0-9Α-ω∞\\{}]*|[A-Z])(?:\s*(?:[_^]\s*(?:\{[^{}\n]+\}|[A-Za-z0-9Α-ω∞\\*'+-]+)))+(?:\s*(?:[=+\-~]\s*)?(?:\\?[A-Za-zΑ-ω∞][A-Za-z0-9Α-ω∞\\{}]*|[A-Z])(?:\s*(?:[_^]\s*(?:\{[^{}\n]+\}|[A-Za-z0-9Α-ω∞\\*'+-]+)))*)*)/g;
  processed = processed.replace(latexSpan, (_match, prefix: string, expr: string) => {
    if (!/[\\_^]/.test(expr)) return `${prefix}${expr}`;
    return `${prefix}$${expr.trim()}$`;
  });

  return processed.replace(/@@AI_AGENT_PROTECTED_(\d+)@@/g, (_match, index) => {
    return protectedBlocks[Number(index)] ?? "";
  });
}

/**
 * Truncate text to `maxLength` characters, appending a note if trimmed.
 */
export function truncateToLength(content: string, maxLength: number): string {
  if (content.length <= maxLength) return content;
  return `${content.slice(0, maxLength)}\n\n[Context truncated at ${maxLength} characters]`;
}
