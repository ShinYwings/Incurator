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
 * focused element? Strict allowlist: only when the focus is inside the diff's
 * own CodeMirror editor or the floating toolbar. No focus, or focus anywhere
 * else (notably the chat input), returns false.
 */
export function shouldHandleDiffShortcut(
  activeEl: unknown,
  cmEditorEl: ContainsNode | null,
  toolbarEl: ContainsNode | null
): boolean {
  if (!activeEl) return false;
  if (cmEditorEl && cmEditorEl.contains(activeEl)) return true;
  if (toolbarEl && toolbarEl.contains(activeEl)) return true;
  return false;
}
