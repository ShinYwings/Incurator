import { describe, expect, it } from "vitest";
import { isAddedState, ADDED_STATES } from "./sourceStatus";

describe("isAddedState (Plan G item 5 — re-ingest gatekeeper)", () => {
  it("returns true for every layer-ready state", () => {
    for (const s of ["l1_ready", "l2_ready", "l3_ready", "l4_ready"]) {
      expect(isAddedState(s)).toBe(true);
    }
  });

  it("returns false for in-progress / unbuilt states", () => {
    for (const s of ["queued", "running", "pending", "unknown", "untracked", "moved", "missing", "error"]) {
      expect(isAddedState(s)).toBe(false);
    }
  });

  it("returns false for empty / fallback / drifted strings", () => {
    // Guards against schema drift: a renamed or unexpected state must NOT be
    // treated as "added" (which would suppress a legitimate re-ingest action).
    for (const s of ["", " ", "added", "done", "built", "complete", "l0_ready", "l5_ready", "ready"]) {
      expect(isAddedState(s)).toBe(false);
    }
  });

  it("is case-sensitive (backend emits lowercase layer states)", () => {
    expect(isAddedState("L1_READY")).toBe(false);
    expect(isAddedState("L1_Ready")).toBe(false);
  });

  it("ADDED_STATES is the single source of truth and has exactly 4 entries", () => {
    expect([...ADDED_STATES]).toEqual(["l1_ready", "l2_ready", "l3_ready", "l4_ready"]);
  });
});
