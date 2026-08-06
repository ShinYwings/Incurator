/**
 * A record of where vault files moved to.
 *
 * Chat history stores file paths inside message text — an `ai-agent-edit` block
 * carries the path it was written against. When the user moves that file, every
 * stored reference silently points at a location that no longer exists, and the
 * only feedback is "File not found".
 *
 * Resolving that by falling back to a basename match would be wrong, and
 * `ChatSidebarView.resolveVaultFile` deliberately refuses to: a same-named file
 * in another folder is a DIFFERENT note, and retargeting an edit to it silently
 * corrupts the wrong file. This journal is not a guess — Obsidian tells us
 * exactly which file moved and where, so following it resolves the historical
 * path to the same file, never to a different one.
 */

export interface RenameEntry {
  from: string;
  to: string;
}

/** Bounded so a long-lived vault cannot grow this without limit. */
export const MAX_RENAME_ENTRIES = 500;

export class RenameJournal {
  /** oldPath -> newPath, most recent write wins. */
  private moves = new Map<string, string>();

  constructor(entries: RenameEntry[] = []) {
    for (const entry of entries) this.record(entry.from, entry.to);
  }

  /**
   * Record a move, collapsing chains as they are created.
   *
   * If A moved to B earlier and B now moves to C, every historical reference to
   * A must resolve to C — so the existing A->B entry is rewritten to A->C rather
   * than left to be walked at lookup time. Collapsing on write means `resolve`
   * is a single lookup and cannot loop.
   */
  record(from: string, to: string): void {
    if (!from || !to || from === to) return;

    for (const [oldPath, currentPath] of this.moves) {
      if (currentPath === from) this.moves.set(oldPath, to);
    }
    // A file moved back to a path we were tracking: that entry is now a no-op
    // and keeping it would resolve a live path to a stale one.
    if (this.moves.get(to) !== undefined) this.moves.delete(to);
    this.moves.set(from, to);

    while (this.moves.size > MAX_RENAME_ENTRIES) {
      const oldest = this.moves.keys().next();
      if (oldest.done) break;
      this.moves.delete(oldest.value);
    }
  }

  /** Where a historical path lives now, or null if it was never moved. */
  resolve(path: string): string | null {
    if (!path) return null;
    const to = this.moves.get(path);
    return to && to !== path ? to : null;
  }

  /**
   * Forget a path that no longer needs following.
   *
   * Called when a file is deleted: a reference to it should report the deletion
   * honestly rather than resolve to wherever the path previously pointed.
   */
  forget(path: string): void {
    this.moves.delete(path);
    for (const [oldPath, currentPath] of this.moves) {
      if (currentPath === path) this.moves.delete(oldPath);
    }
  }

  toJSON(): RenameEntry[] {
    return Array.from(this.moves, ([from, to]) => ({ from, to }));
  }

  get size(): number {
    return this.moves.size;
  }
}
