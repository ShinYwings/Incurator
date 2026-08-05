import { describe, it, expect, vi } from "vitest";
import { SyncScheduler } from "./syncScheduler";

/**
 * B1 / plugin_lifecycle-4: `dispose()` cleared the debounce timer but left
 * `pending` armed. A run already in flight re-fires from its own `finally` when
 * `pending` is set, so a sync pass could start AFTER the plugin unloaded —
 * spawning a backend subprocess against a vault the plugin no longer owns.
 */
describe("SyncScheduler.dispose", () => {
  it("does not start the queued follow-up run after disposal", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => { release = r; });
    const run = vi.fn().mockImplementation(() => gate);

    const scheduler = new SyncScheduler(run, 0);
    const inFlight = scheduler.runNow();          // run #1 starts and blocks
    await Promise.resolve();
    expect(run).toHaveBeenCalledTimes(1);

    void scheduler.runNow();                       // queues a follow-up (pending)
    scheduler.dispose();                           // unload while #1 is in flight
    release();
    await inFlight;
    await Promise.resolve();

    // Without the fix the `finally` would fire the queued pass here.
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("ignores triggers that arrive after disposal", async () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const scheduler = new SyncScheduler(run, 0);

    scheduler.dispose();
    scheduler.schedule();
    await scheduler.runNow();
    await new Promise((r) => setTimeout(r, 5));

    expect(run).not.toHaveBeenCalled();
  });

  it("still cancels a pending debounce timer", async () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const scheduler = new SyncScheduler(run, 5);

    scheduler.schedule();
    scheduler.dispose();
    await new Promise((r) => setTimeout(r, 20));

    expect(run).not.toHaveBeenCalled();
  });

  it("runs normally when not disposed", async () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const scheduler = new SyncScheduler(run, 0);

    await scheduler.runNow();

    expect(run).toHaveBeenCalledTimes(1);
  });
});
