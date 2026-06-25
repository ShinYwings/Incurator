/**
 * Pure source-status helpers (no Obsidian deps, unit-testable).
 *
 * `isAddedState` is the gatekeeper that makes a registered source badge inert —
 * it MUST NOT fall through to re-ingest once registration has happened, even if
 * the build is still queued/running (PLUGIN_SCHEMA §4.1.1). Kept in its own
 * module so it can be unit-tested against schema drift / fallback strings
 * without instantiating an Obsidian ItemView.
 */

/** Registered states that mean the badge must not expose Add Source again. */
export const ADDED_STATES = ["queued", "running", "l1_ready", "l2_ready", "l3_ready", "l4_ready"] as const;

export function isAddedState(state: string): boolean {
  return (ADDED_STATES as readonly string[]).includes(state);
}
