/**
 * Fitting a turn's supporting blocks around the thing the reader pointed at.
 *
 * Every optional block had its own independent cap and none of them knew about
 * the others. Stack them all near their limits — a whole bibliography, a PDF
 * window, a twelve-item evidence pack, pinned sources, follow-ups — and a
 * measured worst case put the reader's own selection at 102 characters inside a
 * 53,000-character turn: 0.19%, outweighed by the vault evidence alone by more
 * than two hundred times.
 *
 * A popover question is usually deictic — "이게 뭐야", "what does this mean" — so
 * the selection IS the subject and is short by construction. Nothing shrank the
 * supporting material when the selection was small, and nothing reserved any
 * share for it.
 *
 * So the blocks are fitted against ONE budget, in priority order, and the
 * selection and the question are never trimmed. Priority is by how directly the
 * reader asked for the thing: what they highlighted, then what they pointed at,
 * then the document around it, then what the vault volunteered.
 */

export interface TurnBlock {
  /** The rendered block. Empty blocks cost nothing and are dropped. */
  text: string;
  /**
   * Lower is kept longer. The reader's own selection is 0; material the vault
   * volunteered without being asked is last.
   */
  priority: number;
  /** A block that must never be trimmed, however tight the budget. */
  pinned?: boolean;
  /** Shown in the elision marker so the model knows what is missing. */
  label: string;
}

/**
 * Trim the lowest-priority blocks until the turn fits.
 *
 * Blocks are dropped whole rather than sliced: half an evidence pack reads as a
 * complete one that happens to be wrong, while an absent one is visibly absent.
 * The exception is the single block that straddles the limit, which is cut with
 * its own elision marker so the model can see it was cut.
 */
export function fitTurnBudget(blocks: TurnBlock[], budget: number): string[] {
  const present = blocks.filter((b) => b.text && b.text.trim());
  const total = present.reduce((n, b) => n + b.text.length, 0);
  if (total <= budget) return present.map((b) => b.text);

  const pinned = present.filter((b) => b.pinned);
  const optional = present
    .filter((b) => !b.pinned)
    .sort((a, b) => a.priority - b.priority);

  let room = budget - pinned.reduce((n, b) => n + b.text.length, 0);
  const keep = new Set<TurnBlock>(pinned);
  const trimmed = new Map<TurnBlock, string>();
  const dropped: string[] = [];

  for (const b of optional) {
    if (b.text.length <= room) {
      keep.add(b);
      room -= b.text.length;
      continue;
    }
    // The block that straddles the limit is worth keeping in part when there is
    // real room left; below that a fragment is noise, so it goes whole.
    if (room > 600) {
      keep.add(b);
      trimmed.set(
        b,
        `${b.text.slice(0, room)}\n[${b.label} truncated to fit this turn]`
      );
      room = 0;
      continue;
    }
    dropped.push(b.label);
  }

  const out = present
    .filter((b) => keep.has(b))
    .map((b) => trimmed.get(b) ?? b.text);

  if (dropped.length > 0) {
    out.push(
      `[Omitted to fit this turn, in order of least relevance to the ` +
        `selection: ${dropped.join(", ")}. Answer from what is present; do not ` +
        `assume the omitted material contradicts it.]`
    );
  }
  return out;
}
