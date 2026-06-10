/**
 * Normalise LaTeX delimiters from various source formats to standard
 * single-dollar / double-dollar markdown form, while leaving code blocks,
 * inline code, existing math spans, markdown links, and HTML tags untouched.
 */
export function normalizeLatexDelimiters(content: string): string {
  // Fix LLMs that wrap a whole math span in inline-code backticks
  // (e.g. `$x^2$` or `$$y = z$$`), often mimicking prompt examples. Obsidian
  // then renders the raw LaTeX as monospace text instead of a formula, so the
  // backticks must be stripped. Only unwrap when the span actually looks like
  // math (contains a LaTeX command or sub/superscript/brace) to avoid touching
  // legitimate inline code such as a `$5 and $10` price range.
  content = content.replace(
    /`(\$\$?[^`\n]*?\$\$?)`/g,
    (match, span: string) => (/[\\^_{}]/.test(span) ? span : match)
  );

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
 * Hide code-edit blocks from a streaming assistant message so the chat never
 * floods with raw SEARCH/REPLACE code while the answer is still generating.
 *
 * The LLM commonly emits several `ai-agent-edit` blocks in one answer. We cut
 * from the FIRST edit marker (the fenced ```` ```ai-agent-edit ```` opener or a
 * bare `<<<< SEARCH` line) and replace everything after it with a single
 * placeholder. The post-stream render later swaps the blocks for compact
 * diff-review pills, so the full code only ever lives against the real file.
 */
export function collapseStreamingEditBlocks(content: string): string {
  const fenceIdx = content.indexOf("```ai-agent-edit");
  // Tolerate spacing variants of the bare opener (e.g. `<<<<SEARCH`, `<<<< SEARCH`).
  const searchMatch = content.match(/<{3,}\s*SEARCH/i);
  const searchIdx = searchMatch ? searchMatch.index ?? -1 : -1;
  const markers = [fenceIdx, searchIdx].filter((i) => i !== -1);
  if (markers.length === 0) return content;
  const cut = Math.min(...markers);
  return content.slice(0, cut).trimEnd() + "\n\n*[Generating code edit…]*";
}

/**
 * Remove orphan `ai-agent-edit` markers (`<<<< SEARCH`, `==== REPLACE`, `>>>>`)
 * that survived a failed parse, so they never render as note text (e.g. the
 * reported `### heading` followed by a bare `>>>>`). Safety rules:
 *   - acts only when the message actually contains marker evidence;
 *   - strips only lines that are EXACTLY a marker (on their own line);
 *   - is fenced-code-block aware — markers inside ``` / ~~~ fences are preserved
 *     (a user may legitimately document conflict markers);
 *   - is meant for the RENDERED display string only; never mutate stored
 *     `msg.content`, so "Copy as Markdown" stays byte-faithful.
 */
export function stripDanglingEditMarkers(rendered: string): string {
  const hasEvidence =
    /<{3,}\s*SEARCH/i.test(rendered) ||
    /={3,}\s*REPLACE/i.test(rendered) ||
    /^>{3,}(\s+\w+)?\s*$/m.test(rendered);
  if (!hasEvidence) return rendered;

  const out: string[] = [];
  let fence = ""; // "" = outside; otherwise the active fence char (` or ~)
  for (const line of rendered.split("\n")) {
    const trimmed = line.trim();
    const fenceMatch = trimmed.match(/^(```+|~~~+)/);
    if (fenceMatch) {
      const ch = fenceMatch[1][0];
      if (!fence) fence = ch;
      else if (fence === ch) fence = "";
      out.push(line);
      continue;
    }
    if (!fence) {
      if (/^<{3,}\s*SEARCH\s*$/i.test(trimmed)) continue;
      if (/^={3,}\s*REPLACE\s*$/i.test(trimmed)) continue;
      if (/^>{3,}(\s+\w+)?\s*$/.test(trimmed)) continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

/**
 * Truncate text to `maxLength` characters, appending a note if trimmed.
 */
export function truncateToLength(content: string, maxLength: number): string {
  if (content.length <= maxLength) return content;
  return `${content.slice(0, maxLength)}\n\n[Context truncated at ${maxLength} characters]`;
}

function getLatexFromMathEl(el: Element): { source: string; isBlock: boolean } | null {
  const annotation = el.querySelector('annotation[encoding="application/x-tex"]');
  if (annotation?.textContent) {
    const isBlock =
      el.classList.contains("math-block") ||
      el.getAttribute("display") === "true" ||
      !!el.closest(".math-block");
    return { source: annotation.textContent.trim(), isBlock };
  }
  const scriptBlock = el.querySelector('script[type="math/tex; mode=display"]');
  if (scriptBlock?.textContent) return { source: scriptBlock.textContent.trim(), isBlock: true };
  const scriptInline = el.querySelector('script[type="math/tex"]');
  if (scriptInline?.textContent) return { source: scriptInline.textContent.trim(), isBlock: false };
  return null;
}

function extractTextWithLatex(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  const el = node as Element;
  const tag = el.tagName?.toLowerCase() ?? "";
  if (tag === "span" && el.classList.contains("math")) {
    const result = getLatexFromMathEl(el);
    if (result) return result.isBlock ? `$$${result.source}$$` : `$${result.source}$`;
    return el.textContent ?? "";
  }
  if (tag === "mjx-container") {
    const result = getLatexFromMathEl(el);
    if (result) return result.isBlock ? `$$${result.source}$$` : `$${result.source}$`;
    return "";
  }
  if (tag === "svg") return "";
  const blockTags = new Set(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre"]);
  const text = Array.from(node.childNodes)
    .map((c) => extractTextWithLatex(c))
    .join("");
  return blockTags.has(tag) ? `\n${text}\n` : text;
}

/**
 * Serialize a `Selection` to text, preserving rendered MathJax formulas as
 * `$...$` / `$$...$$` LaTeX. Reads the formula's `annotation[encoding=
 * "application/x-tex"]` source, which is present whether MathJax shows the SVG
 * or has swapped it back to markdown text — so the captured LaTeX does not
 * depend on Obsidian Live Preview's swap timing (the cause of the Ask-AI
 * "formula disappears on drag" bug).
 *
 * Non-math selections take the fast path and return `selection.toString()`
 * unchanged, so ordinary text capture is byte-identical to before.
 */
export function selectionToTextWithLatex(selection: Selection | null): string {
  // A collapsed selection (caret) has no text and no math; bail before the
  // expensive cloneContents()/querySelector, which would otherwise run on every
  // keyup/caret move now that keyboard navigation also triggers the check.
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return "";
  const fragment = selection.getRangeAt(0).cloneContents();
  if (!fragment.querySelector("mjx-container, span.math")) {
    return selection.toString();
  }
  return extractTextWithLatex(fragment).replace(/\n{3,}/g, "\n\n");
}

/**
 * Attach a copy-event interceptor to `el` so that when the user's selection
 * contains rendered MathJax elements, the clipboard receives LaTeX source
 * (`$...$` for inline, `$$...$$` for block) instead of empty SVG content.
 */
export function attachLatexCopyHandler(el: HTMLElement): void {
  el.addEventListener("copy", (e: ClipboardEvent) => {
    if (!e.clipboardData) return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    const fragment = selection.getRangeAt(0).cloneContents();
    if (!fragment.querySelector("mjx-container, span.math")) return;
    e.preventDefault();
    const text = extractTextWithLatex(fragment).replace(/\n{3,}/g, "\n\n").trim();
    e.clipboardData.setData("text/plain", text);
  });
}
