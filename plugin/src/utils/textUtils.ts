/**
 * Normalise LaTeX delimiters from various source formats to standard
 * single-dollar / double-dollar markdown form, while leaving code blocks,
 * inline code, existing math spans, markdown links, and HTML tags untouched.
 */
export function normalizeLatexDelimiters(content: string): string {
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
