import { EventEmitter } from "events";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  backendCommandPolicy,
  collectBackendProcess,
} from "./backendProcess";

class FakeBackendProcess extends EventEmitter {
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  kill = vi.fn(() => true);
}

afterEach(() => {
  vi.useRealTimers();
});

describe("backend process bounds", () => {
  it("terminates and settles a hung process after the bounded kill sequence", async () => {
    vi.useFakeTimers();
    const child = new FakeBackendProcess();
    const resultPromise = collectBackendProcess(child as never, {
      timeoutMs: 50,
      maxOutputBytes: 1024,
      terminationGraceMs: 20,
    });

    await vi.advanceTimersByTimeAsync(100);
    const result = await resultPromise;

    expect(result.ok).toBe(false);
    expect(result.error).toContain("timed out");
    expect(child.kill).toHaveBeenNthCalledWith(1, "SIGTERM");
    expect(child.kill).toHaveBeenNthCalledWith(2, "SIGKILL");
  });

  it("fails visibly when combined output crosses its byte limit", async () => {
    vi.useFakeTimers();
    const child = new FakeBackendProcess();
    const resultPromise = collectBackendProcess(child as never, {
      timeoutMs: 1000,
      maxOutputBytes: 5,
      terminationGraceMs: 10,
    });

    child.stdout.emit("data", Buffer.from("123456"));
    await vi.advanceTimersByTimeAsync(30);
    const result = await resultPromise;

    expect(result.ok).toBe(false);
    expect(result.error).toContain("output limit");
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
  });

  it("keeps legitimate long operations beyond the normal timeout alive", async () => {
    vi.useFakeTimers();
    const normal = backendCommandPolicy(["status", "--json"]);
    const long = backendCommandPolicy(["update"]);
    expect(long.timeoutMs).toBeGreaterThan(normal.timeoutMs);
    expect(long.maxOutputBytes).toBeGreaterThan(normal.maxOutputBytes);

    const child = new FakeBackendProcess();
    let settled = false;
    const resultPromise = collectBackendProcess(child as never, long).then((result) => {
      settled = true;
      return result;
    });
    await vi.advanceTimersByTimeAsync(normal.timeoutMs + 1);
    expect(settled).toBe(false);

    child.stdout.emit("data", Buffer.from("complete"));
    child.emit("close", 0);
    await expect(resultPromise).resolves.toEqual({ ok: true, output: "complete" });
  });
});
