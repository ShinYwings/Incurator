import type { AccessRoot } from "../agent/incuratorClient";

/** Whether a row can offer a folder to grant.
 *
 *  Only a denial is fixable that way. A missing folder has nothing to grant,
 *  and an iCloud-evicted file needs a download, not a permission — a picker
 *  there would be a button that cannot work. Pulled out of the renderer so the
 *  decision is testable without driving a modal. */
export function accessRowOffersGrant(root: AccessRoot): boolean {
  return root.state === "denied" && Boolean(root.grantFolder);
}

/** What the re-check found, in the user's words.
 *
 *  `undefined` means the backend did not answer — which is NOT the same as a
 *  denial and must not be reported as one. */
export function accessRecheckMessage(after: AccessRoot | undefined): string {
  if (after === undefined) return "Could not re-check — the backend did not answer.";
  if (after.state === "ok") return "Incurator can now read this folder.";
  if (after.state === "denied") {
    return "Still denied. If macOS asked and you allowed it, the grant went to Obsidian "
      + "rather than to the Incurator backend. Grant Full Disk Access to your terminal "
      + "in System Settings > Privacy & Security, then press Re-check.";
  }
  return after.detail;
}
