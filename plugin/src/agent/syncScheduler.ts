/**
 * Coalescing scheduler for cross-device auto-sync.
 *
 * Multiple triggers (Obsidian load, fs.watch peer-file events, the fallback poll,
 * the manual ribbon button) all funnel through one scheduler so that:
 *  - rapid bursts (Syncthing delivers a file in chunks) collapse into one run
 *    (debounce), and
 *  - two sync passes never overlap; a trigger arriving mid-run queues exactly one
 *    follow-up run.
 */
export function isIncomingPeerSnapshot(
  filename: string,
  ownSnapshot: string | null
): boolean {
  if (!filename || !filename.endsWith(".jsonl")) return false;
  return !ownSnapshot || filename !== ownSnapshot;
}

export class SyncScheduler {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private pending = false;

  constructor(
    private readonly run: () => Promise<void>,
    private readonly debounceMs: number = 4000
  ) {}

  /** Debounced trigger — coalesces a burst into a single delayed run. */
  schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.fire();
    }, this.debounceMs);
  }

  /** Immediate trigger (manual button / on-load). Cancels any pending debounce. */
  async runNow(): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    await this.fire();
  }

  private async fire(): Promise<void> {
    if (this.running) {
      this.pending = true;
      return;
    }
    this.running = true;
    try {
      await this.run();
    } finally {
      this.running = false;
      if (this.pending) {
        this.pending = false;
        void this.fire();
      }
    }
  }

  dispose(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
