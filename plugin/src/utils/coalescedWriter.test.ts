import { describe, expect, it } from "vitest";

import { createCoalescedWriter } from "./coalescedWriter";

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("createCoalescedWriter", () => {
  it("collapses a burst of saves into a single write", async () => {
    let state = 0;
    const written: number[] = [];
    const w = createCoalescedWriter(
      () => state,
      async (v) => {
        written.push(v);
      },
    );

    // One chat message triggers six persistCurrentSession() calls.
    state = 1;
    const all = [w.save(), w.save(), w.save(), w.save(), w.save(), w.save()];
    await Promise.all(all);

    expect(written).toEqual([1]);
  });

  it("persists the LATEST state, not the state at the first call", async () => {
    let state = "a";
    const written: string[] = [];
    const w = createCoalescedWriter(
      () => state,
      async (v) => {
        written.push(v);
      },
    );

    const first = w.save();
    state = "b";
    const second = w.save();
    await Promise.all([first, second]);

    expect(written).toEqual(["b"]);
  });

  it("does not fold a save made while a write is in flight into that write", async () => {
    // The correctness boundary. That write's snapshot is already taken, so
    // telling a later caller "persisted" would be a lie.
    let state = 1;
    const written: number[] = [];
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));

    const w = createCoalescedWriter(
      () => state,
      async (v) => {
        written.push(v);
        if (v === 1) await gate;
      },
    );

    const first = w.save();
    await tick();
    expect(w.inFlight()).toBe(true);

    state = 2;
    const second = w.save();
    release();
    await Promise.all([first, second]);

    expect(written).toEqual([1, 2]);
  });

  it("never overlaps writes", async () => {
    let concurrent = 0;
    let maxConcurrent = 0;
    let state = 0;
    const w = createCoalescedWriter(
      () => state,
      async () => {
        concurrent += 1;
        maxConcurrent = Math.max(maxConcurrent, concurrent);
        await tick();
        concurrent -= 1;
      },
    );

    const runs: Promise<void>[] = [];
    for (let i = 0; i < 5; i += 1) {
      state = i;
      runs.push(w.save());
      await tick();
    }
    await Promise.all(runs);

    expect(maxConcurrent).toBe(1);
  });

  it("a failed write does not wedge later saves", async () => {
    let state = 0;
    let attempt = 0;
    const written: number[] = [];
    const w = createCoalescedWriter(
      () => state,
      async (v) => {
        attempt += 1;
        if (attempt === 1) throw new Error("disk full");
        written.push(v);
      },
    );

    state = 1;
    await expect(w.save()).rejects.toThrow("disk full");
    await tick();
    state = 2;
    await w.save();

    expect(written).toEqual([2]);
  });
});
