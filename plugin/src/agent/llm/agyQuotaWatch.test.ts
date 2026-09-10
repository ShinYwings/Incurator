import { appendFileSync, existsSync, mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { watchAgyQuota } from "./agyQuotaWatch";

const roots: string[] = [];
const stops: Array<() => void> = [];
const record = "I0910 13:37:18.256298     327 run.go:387] Run: attempt 1 failed (RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 144h56m54s.), retrying in 4s\n";
afterEach(() => {
  stops.splice(0).forEach(stop => stop());
  roots.splice(0).forEach(root => rmSync(root, { recursive: true, force: true }));
});
function fixture() {
  const root = mkdtempSync(join(tmpdir(), "agy-quota-test-"));
  roots.push(root);
  const path = join(root, "run.log");
  const failed = vi.fn();
  const watcher = watchAgyQuota(path, failed);
  stops.push(watcher.dispose);
  return { path, failed, watcher };
}

describe("per-invocation Antigravity terminal quota diagnostics", () => {
  it("recognizes a split runtime failure once without exposing unrelated log data", () => {
    const { path, failed, watcher } = fixture();
    appendFileSync(path, record.slice(0, 80));
    watcher.poll();
    expect(failed).not.toHaveBeenCalled();
    appendFileSync(path, record.slice(80));
    watcher.poll();
    watcher.poll();
    expect(failed).toHaveBeenCalledOnce();
    expect(failed.mock.calls[0][0]).toBe("RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 144h56m54s.");
  });
  it("ignores quoted quota prose, temporary capacity and another invocation", () => {
    const first = fixture();
    const second = fixture();
    appendFileSync(first.path, 'Answer: Individual quota reached (429)\n' + record.replace("Individual quota reached", "Temporary server capacity"));
    first.watcher.poll();
    expect(first.failed).not.toHaveBeenCalled();
    appendFileSync(second.path, record);
    second.watcher.poll();
    expect(second.failed).toHaveBeenCalledOnce();
    expect(first.failed).not.toHaveBeenCalled();
  });
  it("bounds partial lines, continues reading, and removes its log on disposal", () => {
    const { path, failed, watcher } = fixture();
    appendFileSync(path, "x".repeat(150_000) + "\n" + record);
    for (let n = 0; n < 4; n++) watcher.poll();
    expect(failed).toHaveBeenCalledOnce();
    watcher.dispose();
    expect(existsSync(path)).toBe(false);
    watcher.poll();
    expect(failed).toHaveBeenCalledOnce();
  });
  it("drains a single large append even when the runtime writes nothing more", async () => {
    const { path, failed } = fixture();
    appendFileSync(path, "x".repeat(150_000) + "\n" + record);
    await vi.waitFor(() => expect(failed).toHaveBeenCalledOnce(), { timeout: 1500 });
  });
});
