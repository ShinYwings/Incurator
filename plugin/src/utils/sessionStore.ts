import type { SessionData } from "../types";
import {
  atomicWriteVaultText,
  readJsonObjectState,
  type VaultTextAdapter,
} from "./durableJsonStore";
import {
  mergeSessionData,
  normalizeSessionData,
  sanitizeSessionDataForSync,
} from "./sessionData";

export class SessionStoreBlockedError extends Error {
  constructor(kind: "corrupt" | "unreadable") {
    super(`canonical session store is ${kind}`);
    this.name = "SessionStoreBlockedError";
  }
}

export type SessionStoreState =
  | { kind: "missing" }
  | { kind: "valid"; value: SessionData }
  | { kind: "corrupt"; raw: string; error: unknown }
  | { kind: "unreadable"; error: unknown };

const adapterQueues = new WeakMap<object, Map<string, Promise<void>>>();

function parseSessionStoreText(raw: string): SessionData {
  const parsed = JSON.parse(raw) as unknown;
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Array.isArray((parsed as { chatSessions?: unknown }).chatSessions)
  ) {
    throw new TypeError("session store must contain a chatSessions array");
  }
  return normalizeSessionData(parsed as Partial<SessionData>);
}

function queueFor(adapter: VaultTextAdapter): Map<string, Promise<void>> {
  let queue = adapterQueues.get(adapter);
  if (!queue) {
    queue = new Map<string, Promise<void>>();
    adapterQueues.set(adapter, queue);
  }
  return queue;
}

export async function readSessionStore(
  adapter: VaultTextAdapter,
  path: string
): Promise<SessionStoreState> {
  const state = await readJsonObjectState(adapter, path);
  if (state.kind !== "valid") return state;
  try {
    return {
      kind: "valid",
      value: parseSessionStoreText(state.raw),
    };
  } catch (error) {
    return { kind: "corrupt", raw: state.raw, error };
  }
}

export function writeMergedSessionStore(
  adapter: VaultTextAdapter,
  path: string,
  local: SessionData
): Promise<SessionData> {
  const queues = queueFor(adapter);
  const previous = queues.get(path) ?? Promise.resolve();
  const localSnapshot = parseSessionStoreText(
    JSON.stringify(sanitizeSessionDataForSync(local))
  );
  let result: SessionData;
  const operation = previous
    .catch(() => undefined)
    .then(async () => {
      const canonical = await readSessionStore(adapter, path);
      if (canonical.kind === "corrupt" || canonical.kind === "unreadable") {
        throw new SessionStoreBlockedError(canonical.kind);
      }
      if (canonical.kind === "missing") {
        result = sanitizeSessionDataForSync(localSnapshot);
        await atomicWriteVaultText(adapter, path, JSON.stringify(result, null, 2));
        return;
      }

      const committedRaw = await adapter.process(path, (currentRaw) => {
        let current: SessionData;
        try {
          current = parseSessionStoreText(currentRaw);
        } catch {
          throw new SessionStoreBlockedError("corrupt");
        }
        return JSON.stringify(
          sanitizeSessionDataForSync(mergeSessionData(localSnapshot, current)),
          null,
          2
        );
      });
      try {
        result = parseSessionStoreText(committedRaw);
      } catch {
        throw new SessionStoreBlockedError("corrupt");
      }
    });

  queues.set(path, operation);
  return operation.finally(() => {
    if (queues.get(path) === operation) queues.delete(path);
  }).then(() => result!);
}
