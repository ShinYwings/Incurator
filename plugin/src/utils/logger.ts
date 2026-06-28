/**
 * Namespaced, level-gated logger for the Incurator plugin.
 *
 * `debug`/`info` are verbose and gated OFF by default so a user's dev console
 * stays quiet; a developer enables them by setting
 * `localStorage["incurator-debug"] = "1"` (read once at module load — toggling
 * requires an Obsidian reload). `warn`/`error` always emit so failures remain
 * visible for field triage. All output is prefixed with `[Incurator]`.
 */

const PREFIX = "[Incurator]";

function debugEnabled(): boolean {
  try {
    return localStorage.getItem("incurator-debug") === "1";
  } catch {
    // localStorage can be unavailable/throwing in some Obsidian contexts.
    return false;
  }
}

const DEBUG = debugEnabled();

export const logger = {
  debug: (...args: unknown[]): void => {
    if (DEBUG) console.debug(PREFIX, ...args);
  },
  info: (...args: unknown[]): void => {
    if (DEBUG) console.info(PREFIX, ...args);
  },
  warn: (...args: unknown[]): void => {
    console.warn(PREFIX, ...args);
  },
  error: (...args: unknown[]): void => {
    console.error(PREFIX, ...args);
  },
};
