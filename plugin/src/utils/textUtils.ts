import { parseMathSources } from "./mathSource";

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
  // Reading-view path: Obsidian's reading-view MathJax (CHTML) keeps NO source in
  // the DOM (no annotation / assistive MathML — verified live), so our markdown
  // post-processor stamps the source onto the `.math` wrapper as `data-tex`
  // (+ `data-tex-display`). Read that first; it is the only source available in
  // reading view. `closest` covers being handed either the wrapper or its
  // `mjx-container` child.
  const stamped = (el.closest?.("[data-tex]") ?? null) as HTMLElement | null;
  const stampedTex = stamped?.dataset?.tex;
  if (stampedTex) {
    return { source: stampedTex.trim(), isBlock: stamped?.dataset?.texDisplay === "block" };
  }
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
/**
 * Serialize a chat / answer selection to **Markdown**, preserving BOTH inline
 * formatting (bold, headings, lists, links, tables…) via Obsidian's
 * `htmlToMarkdown` AND rendered math as LaTeX source (`$...$` / `$$...$$`).
 *
 * Math is protected from `htmlToMarkdown`'s escaping (which would turn `\frac`
 * into `\\frac`) by swapping each rendered formula for a placeholder token BEFORE
 * conversion and restoring the LaTeX AFTER. The formula source comes from
 * `getLatexFromMathEl` (the `data-tex` stamp in the chat / reading view).
 *
 * `htmlToMarkdown` is injected (the Obsidian API) so this module stays free of an
 * `obsidian` runtime import and remains unit-testable. Returns `null` for an
 * empty/collapsed selection (caller leaves the native copy untouched) or if
 * conversion throws.
 */
export function selectionToMarkdownWithLatex(
  selection: Selection | null,
  htmlToMarkdown: (input: HTMLElement) => string
): string | null {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  try {
    const wrapper = document.createElement("div");
    wrapper.appendChild(selection.getRangeAt(0).cloneContents());
    const placeholders: string[] = [];
    for (const m of Array.from(wrapper.querySelectorAll<HTMLElement>(".math, mjx-container"))) {
      // An ancestor `.math` was already replaced (its mjx-container detached) → skip.
      if (!wrapper.contains(m)) continue;
      const info = getLatexFromMathEl(m);
      if (!info) continue;
      const token = `@@LATEX${placeholders.length}@@`;
      placeholders.push(info.isBlock ? `$$${info.source}$$` : `$${info.source}$`);
      m.replaceWith(wrapper.ownerDocument.createTextNode(token));
    }
    const md = htmlToMarkdown(wrapper).replace(
      /@@LATEX(\d+)@@/g,
      (_match, i: string) => placeholders[Number(i)] ?? ""
    );
    return md.trim();
  } catch {
    return null;
  }
}

/**
 * Stamp the LaTeX source onto rendered MathJax elements as `data-tex` /
 * `data-tex-display`, so a later copy of a selection can recover `$...$`/`$$...$$`.
 *
 * Why this is needed: Obsidian renders math (in the chat sidebar via
 * `MarkdownRenderer`, and in reading view) as CHTML and keeps NO source in the
 * DOM — no `annotation[x-tex]`, no assistive MathML, no attribute (verified live).
 * So `getLatexFromMathEl` has nothing to read. Wherever we render markdown from a
 * source string we DO have, we call this right after the render to put the source
 * back, in document order, onto the `.math` wrappers.
 *
 * `source` MUST be the exact string that was rendered into `container`. The Nth
 * parsed formula maps to the Nth rendered `.math` element. As a correctness guard
 * we ONLY stamp when the parsed count EXACTLY equals the rendered count — so a
 * mis-parse can never produce a WRONG source; it just skips this container.
 */
export function stampMathSourceData(container: HTMLElement, source: string): void {
  const mathEls = container.querySelectorAll<HTMLElement>(".math");
  if (mathEls.length === 0) return;
  const formulas = parseMathSources(source);
  if (formulas.length !== mathEls.length) return; // never stamp a wrong source
  mathEls.forEach((m, i) => {
    m.dataset.tex = formulas[i].tex;
    m.dataset.texDisplay = formulas[i].display ? "block" : "inline";
  });
}

/**
 * True when the selection is anchored inside a Markdown **reading view** (rendered,
 * read-only). Only there does a copy need our `data-tex` extraction: Live Preview /
 * source mode (CodeMirror) already copy the document source — including `$...$` —
 * natively, so they are deliberately excluded. Null-safe. This also excludes the
 * chat / quick-query surfaces (they are not reading views and own their own copy
 * handler), so the document-level note handler never double-processes them.
 */
export function isSelectionInReadingView(selection: Selection | null): boolean {
  const node = selection?.anchorNode ?? null;
  if (!node) return false;
  const el = node instanceof Element ? node : node.parentElement;
  return Boolean(el?.closest(".markdown-reading-view"));
}

/**
 * True when the cloned selection range contains a rendered math element. The math
 * node is included in `cloneContents()` even when MathJax's `user-select:none`
 * stops it from *visually* highlighting — which is exactly why a reading-view copy
 * can still recover the formula. Null/collapsed-safe.
 */
export function selectionContainsRenderedMath(selection: Selection | null): boolean {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return false;
  return Boolean(
    selection.getRangeAt(0).cloneContents().querySelector("mjx-container, span.math")
  );
}

/**
 * Attach a copy-event interceptor to `el` so a selection is copied as **Markdown**
 * (formatting + LaTeX source) instead of the browser's plain text / empty math SVG.
 * `htmlToMarkdown` is the injected Obsidian API. A non-collapsed selection that
 * converts to empty falls through to the native copy.
 */
export function attachLatexCopyHandler(
  el: HTMLElement,
  htmlToMarkdown: (input: HTMLElement) => string
): void {
  el.addEventListener("copy", (e: ClipboardEvent) => {
    if (!e.clipboardData) return;
    // Use the element's OWN document selection, not window's — in an Obsidian
    // pop-out window `window` is the main window, so window.getSelection() would
    // miss (or mis-read) the pop-out's selection.
    const selection = el.ownerDocument.getSelection();
    const md = selectionToMarkdownWithLatex(selection, htmlToMarkdown);
    if (!md) return;
    e.preventDefault();
    e.clipboardData.setData("text/plain", md);
  });
}

/**
 * Extract lines `[lineStart, lineEnd]` (0-indexed, inclusive) from `text` by walking
 * newline indices — equivalent to
 * `text.split("\n").slice(lineStart, lineEnd + 1).join("\n")` but WITHOUT splitting
 * the whole string into an array. Used by the reading-view math post-processor,
 * which runs per math block on every render; full-document splits there cause lag on
 * large notes.
 */
export function sliceLinesByIndex(text: string, lineStart: number, lineEnd: number): string {
  let start = 0;
  for (let l = 0; l < lineStart; l++) {
    const nl = text.indexOf("\n", start);
    if (nl === -1) return "";
    start = nl + 1;
  }
  let cursor = start;
  for (let l = lineStart; l <= lineEnd; l++) {
    const nl = text.indexOf("\n", cursor);
    if (nl === -1) return text.slice(start);
    if (l === lineEnd) return text.slice(start, nl);
    cursor = nl + 1;
  }
  return text.slice(start);
}
