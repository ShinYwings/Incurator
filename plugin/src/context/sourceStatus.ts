/**
 * Pure source-status helpers (no Obsidian deps, unit-testable).
 *
 * `isAddedState` is the gatekeeper that makes a built source's "Added" badge
 * inert — it MUST NOT fall through to re-ingest (PLUGIN_SCHEMA §4.1.1). Kept in
 * its own module so it can be unit-tested against schema drift / fallback
 * strings without instantiating an Obsidian ItemView.
 */

/** Layer-ready states that mean the source is built/added and the badge is inert. */
export const ADDED_STATES = ["l1_ready", "l2_ready", "l3_ready", "l4_ready"] as const;

export function isAddedState(state: string): boolean {
  return (ADDED_STATES as readonly string[]).includes(state);
}
