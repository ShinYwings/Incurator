/**
 * Keys whose keyup should re-check the text selection for the Ask-AI button.
 *
 * We deliberately do NOT inspect modifier state (Shift/Ctrl/Cmd) at keyup time:
 * if the user releases the modifier a moment before the primary key, the
 * primary key's keyup reports the modifier as false and a modifier-gated check
 * would miss the selection gesture. Instead we react to the discrete keys that
 * can extend OR collapse a selection, and let `handleSelectionChange` read the
 * live selection to decide whether to show or hide the button.
 *
 * Includes collapse/edit keys (plain arrows without Shift, Escape, Backspace,
 * Delete, Enter, PageUp/Down) so a lingering button is dismissed when the user
 * collapses a selection back to a caret. `a`/`A` covers Ctrl/Cmd+A select-all.
 */
const SELECTION_RELEVANT_KEYS = new Set<string>([
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Home",
  "End",
  "PageUp",
  "PageDown",
  "Escape",
  "Backspace",
  "Delete",
  "Enter",
  "a",
  "A",
]);

export function isSelectionRelevantKey(key: string): boolean {
  return SELECTION_RELEVANT_KEYS.has(key);
}
