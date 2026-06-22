/**
 * Pure focus-guard predicate for the Diff Viewer's keyboard shortcuts (v0.24.0).
 *
 * The toolbar previously registered a document-global keydown listener with NO
 * focus check, so pressing Enter in the chat input (or anywhere) fired
 * Accept-All and silently wrote the file. This predicate restricts the
 * shortcuts to when focus is genuinely inside the diff editor or its toolbar.
 *
 * Pure and DOM-light (only `.contains`) so it unit-tests without a real DOM.
 */

interface ContainsNode {
  contains(other: unknown): boolean;
}

/**
 * Should a Diff Viewer keyboard shortcut (Accept/Reject/navigate) fire for this
 * focused element?
 *
 * Allowlist: focus inside the diff's own CodeMirror editor or the floating
 * toolbar always passes. Clicking a non-focusable region of the diff (the
 * toolbar background, a header) drops `document.activeElement` to `<body>`;
 * without a fallback the shortcuts would silently die until the user clicks the
 * editor text again. So a body/no-focus state ALSO passes, but ONLY when
 * `diffLeafActive` (the diff's editor is the active workspace leaf). That keeps
 * the chat input excluded — focusing it puts `activeElement` on the input
 * element, not `<body>`, so the body branch never fires for it.
 */
export function shouldHandleDiffShortcut(
  activeEl: unknown,
  cmEditorEl: ContainsNode | null,
  toolbarEl: ContainsNode | null,
  diffLeafActive = false
): boolean {
  if (cmEditorEl && cmEditorEl.contains(activeEl)) return true;
  if (toolbarEl && toolbarEl.contains(activeEl)) return true;
  const doc = (activeEl as { ownerDocument?: Document } | null)?.ownerDocument;
  const isBodyOrNull = !activeEl || activeEl === doc?.body;
  return isBodyOrNull && diffLeafActive;
}
