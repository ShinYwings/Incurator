import { describe, it, expect, vi } from "vitest";
import { isIncomingPeerSnapshot, SyncScheduler } from "./syncScheduler";

describe("isIncomingPeerSnapshot", () => {
  it("accepts peer and conflict snapshots but rejects the known self snapshot", () => {
    expect(isIncomingPeerSnapshot("dev-peer.jsonl", "dev-self.jsonl")).toBe(true);
    expect(
      isIncomingPeerSnapshot("dev-peer.sync-conflict-20260719.jsonl", "dev-self.jsonl")
    ).toBe(true);
    expect(isIncomingPeerSnapshot("dev-self.jsonl", "dev-self.jsonl")).toBe(false);
    expect(isIncomingPeerSnapshot("sync_state.json", "dev-self.jsonl")).toBe(false);
    expect(isIncomingPeerSnapshot("", "dev-self.jsonl")).toBe(false);
  });
});

describe("SyncScheduler", () => {
  it("coalesces a burst of schedule() calls into one run", async () => {
    vi.useFakeTimers();
    let runs = 0;
    const s = new SyncScheduler(async () => { runs += 1; }, 100);
    s.schedule();
    s.schedule();
    s.schedule();
    expect(runs).toBe(0); // debounced, not fired yet
    await vi.advanceTimersByTimeAsync(120);
    expect(runs).toBe(1); // collapsed into a single run
    vi.useRealTimers();
  });

  it("never overlaps; a trigger mid-run queues exactly one follow-up", async () => {
    let active = 0;
    let maxActive = 0;
    let runs = 0;
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });

    const s = new SyncScheduler(async () => {
      runs += 1;
      active += 1;
      maxActive = Math.max(maxActive, active);
      if (runs === 1) await gate; // hold the first run open
      active -= 1;
    }, 0);

    const first = s.runNow();      // starts and blocks on gate
    await s.runNow();              // arrives mid-run → should queue, not overlap
    await s.runNow();              // another mid-run trigger → collapses into the one pending
    release();
    await first;
    // allow queued follow-up to drain
    await new Promise((r) => setTimeout(r, 0));

    expect(maxActive).toBe(1);     // never ran concurrently
    expect(runs).toBe(2);          // first + exactly one coalesced follow-up
  });

  it("runNow cancels a pending debounce", async () => {
    vi.useFakeTimers();
    let runs = 0;
    const s = new SyncScheduler(async () => { runs += 1; }, 100);
    s.schedule();
    await s.runNow();
    expect(runs).toBe(1);
    await vi.advanceTimersByTimeAsync(200);
    expect(runs).toBe(1); // the debounced one was cancelled by runNow
    vi.useRealTimers();
  });
});
