import type { ChildProcess } from "child_process";

export interface BackendCommandResult {
  ok: boolean;
  output?: string;
  error?: string;
}

export interface BackendProcessPolicy {
  timeoutMs: number;
  maxOutputBytes: number;
  terminationGraceMs: number;
}

const NORMAL_POLICY: BackendProcessPolicy = {
  timeoutMs: 2 * 60 * 1000,
  maxOutputBytes: 16 * 1024 * 1024,
  terminationGraceMs: 1000,
};

const LONG_POLICY: BackendProcessPolicy = {
  timeoutMs: 60 * 60 * 1000,
  maxOutputBytes: 64 * 1024 * 1024,
  terminationGraceMs: 2000,
};

const LONG_TOP_LEVEL_COMMANDS = new Set([
  "add",
  "build",
  "lint",
  "reindex",
  "reset",
  "sync",
  "update",
]);

/** Select bounds from the command's actual workload rather than one global timer. */
export function backendCommandPolicy(cmdArgs: string[]): BackendProcessPolicy {
  const [root = "", action = "", operation = ""] = cmdArgs;
  const longRunning =
    LONG_TOP_LEVEL_COMMANDS.has(root) ||
    (root === "jobs" && action === "run") ||
    (root === "db" && action === "autosync") ||
    (root === "plugin" && action === "query") ||
    (root === "plugin" && action === "promote") ||
    (root === "plugin" && action === "git" && operation === "push") ||
    (root === "plugin" && action === "source" && ["import", "register"].includes(operation)) ||
    (root === "plugin" && action === "pdf" && operation === "transcribe") ||
    (root === "plugin" && action === "models" && ["refresh", "pull"].includes(operation));
  return { ...(longRunning ? LONG_POLICY : NORMAL_POLICY) };
}

/** Collect a spawned backend process with bounded output and termination. */
export function collectBackendProcess(
  child: ChildProcess,
  policy: BackendProcessPolicy,
): Promise<BackendCommandResult> {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;
    let terminationError = "";
    let forceKillTimer: ReturnType<typeof setTimeout> | null = null;
    let forcedCompletionTimer: ReturnType<typeof setTimeout> | null = null;

    const deadline = setTimeout(() => {
      terminate(`Backend command timed out after ${Math.round(policy.timeoutMs / 1000)} seconds`);
    }, policy.timeoutMs);

    const finish = (result: BackendCommandResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      if (forceKillTimer) clearTimeout(forceKillTimer);
      if (forcedCompletionTimer) clearTimeout(forcedCompletionTimer);
      resolve(result);
    };

    const failedResult = (): BackendCommandResult => ({
      ok: false,
      ...(stdout ? { output: stdout } : {}),
      error: terminationError,
    });

    function terminate(error: string): void {
      if (settled || terminationError) return;
      terminationError = error;
      child.kill("SIGTERM");
      if (settled) return;
      forceKillTimer = setTimeout(() => {
        child.kill("SIGKILL");
        if (settled) return;
        forcedCompletionTimer = setTimeout(
          () => finish(failedResult()),
          policy.terminationGraceMs,
        );
      }, policy.terminationGraceMs);
    }

    const append = (stream: "stdout" | "stderr", data: Buffer | string) => {
      if (settled || terminationError) return;
      const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
      const remaining = policy.maxOutputBytes - outputBytes;
      if (remaining > 0) {
        const accepted = buffer.subarray(0, remaining).toString("utf-8");
        if (stream === "stdout") stdout += accepted;
        else stderr += accepted;
        outputBytes += Math.min(buffer.byteLength, remaining);
      }
      if (buffer.byteLength > remaining) {
        terminate(
          `Backend command exceeded the ${Math.round(policy.maxOutputBytes / (1024 * 1024))} MiB output limit`,
        );
      }
    };

    child.stdout?.on("data", (data: Buffer | string) => append("stdout", data));
    child.stderr?.on("data", (data: Buffer | string) => append("stderr", data));
    child.on("error", (error: Error) => {
      finish(
        terminationError
          ? failedResult()
          : { ok: false, error: error.message },
      );
    });
    child.on("close", (code) => {
      if (terminationError) {
        finish(failedResult());
      } else if (code === 0) {
        finish({ ok: true, output: stdout });
      } else {
        finish({
          ok: false,
          ...(stdout ? { output: stdout } : {}),
          error: stderr || stdout || `Exit code ${code}`,
        });
      }
    });
  });
}
