/**
 * Collapse a burst of "save everything" calls into one write.
 *
 * `sessions.json` is rewritten in full on every save, and sending one chat
 * message triggers SIX `persistCurrentSession()` calls (user message, assistant
 * placeholder, materialized context refs, and the finally blocks). Each one deep
 * cloned the whole structure via `JSON.parse(JSON.stringify(...))` and then did a
 * read + parse + merge + stringify + write of the file.
 *
 * On the reference vault that file is 14.5 MB, so a single message sent moved
 * roughly a hundred megabytes of I/O and re-transmitted the whole file over
 * Syncthing several times. The measured cost was ~1.1 s per send.
 *
 * The writes are redundant rather than merely frequent: they all persist the
 * same mutable object, so the last one subsumes the ones before it. Coalescing
 * is therefore lossless, not a durability trade.
 *
 * Ordering guarantee: writes never overlap, and a call made WHILE a write is in
 * flight is not folded into it -- that write's snapshot was already taken, so
 * the newer state gets its own write.
 */
export function createCoalescedWriter<T>(
  snapshot: () => T,
  write: (value: T) => Promise<void>,
): { save: () => Promise<void>; inFlight: () => boolean } {
  let tail: Promise<void> = Promise.resolve();
  let queued: Promise<void> | null = null;
  let running = false;

  const save = (): Promise<void> => {
    // A batch is already queued and has NOT yet taken its snapshot, so it will
    // capture this caller's state too. Join it instead of adding a write.
    if (queued) return queued;

    queued = tail
      .catch(() => undefined)
      .then(() => {
        // Snapshot first, then release the slot: a save arriving after this
        // point has state this snapshot does not contain, and must not be told
        // it has been persisted.
        const value = snapshot();
        queued = null;
        running = true;
        return write(value).finally(() => {
          running = false;
        });
      });

    tail = queued.catch(() => undefined);
    return queued;
  };

  return { save, inFlight: () => running };
}
