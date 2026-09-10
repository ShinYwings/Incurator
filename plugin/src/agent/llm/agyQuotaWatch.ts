import { closeSync, openSync, readSync, unlinkSync, writeFileSync } from "fs";

/** The CLI hides terminal quota behind retries in print mode. Read only this
 * invocation's diagnostic records, never model prose or another run's log.
 * Incremental bounded reads keep a long-running CLI off the UI's hot path. */
export function watchAgyQuota(path: string, onQuota: (reason: string) => void): {
  poll: () => void; dispose: () => void;
} {
  writeFileSync(path, "", { flag: "wx", mode: 0o600 });
  let offset = 0;
  let partial = "";
  let disposed = false;
  let reported = false;
  const buffer = Buffer.alloc(64 * 1024);
  const poll = () => {
    if (disposed || reported) return;
    let count: number;
    try {
      const fd = openSync(path, "r");
      try { count = readSync(fd, buffer, 0, buffer.length, offset); }
      finally { closeSync(fd); }
    } catch { return; } // Optional diagnostics cannot break a valid answer.
    offset += count;
    const lines = (partial + buffer.toString("utf8", 0, count)).split("\n");
    partial = (lines.pop() || "").slice(-8192);
    for (const line of lines) {
      // A plain 429 may be transient or quoted content. Only the runtime's
      // terminal individual-quota record justifies interrupting paid work.
      const match = line.match(/^(?:ERROR: logging before google\.Init: )?[IWE]\d{4} \d{2}:\d{2}:\d{2}\.\d+\s+\d+ run\.go:\d+\] Run: attempt \d+ failed \((RESOURCE_EXHAUSTED \(code 429\): Individual quota reached\.[^\r\n]*?)\), retrying/);
      if (match) {
        reported = true;
        onQuota(match[1]);
        return;
      }
    }
  };
  // Keep draining unread bytes even after a large one-shot append. File-change
  // callbacks alone would stop after the first bounded read of that append.
  const timer = setInterval(poll, 250);
  timer.unref();
  return {
    poll,
    dispose: () => {
      if (disposed) return;
      disposed = true;
      clearInterval(timer);
      try { unlinkSync(path); } catch { /* Already removed during CLI cleanup. */ }
    },
  };
}
