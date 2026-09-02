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

/** True when the backend runs on macOS.
 *
 *  This matters because the FIX for a denial is not the same everywhere. macOS
 *  denials are usually TCC, granted per responsible process through a system
 *  dialog. On Linux the identical verdict is filesystem permissions: there is no
 *  grant dialog, opening the folder grants nothing, and telling someone to
 *  "allow it when macOS asks" sends them looking for a prompt that will never
 *  come. The backend's platform decides, not the plugin's — the backend is the
 *  process that holds the permission. */
export function isMacBackend(platform: string): boolean {
  return platform === "darwin";
}

/** What the button should say before it has been pressed. */
export function accessGrantLabel(platform: string): string {
  return isMacBackend(platform) ? "Grant access…" : "Open folder…";
}

/** What to expect after the folder opens. */
export function accessOpenedMessage(folder: string, platform: string): string {
  return isMacBackend(platform)
    ? `Opened ${folder}. Allow access if macOS asks, then press Re-check.`
    : `Opened ${folder}. Make it readable by the user running the Incurator `
      + "backend, then press Re-check.";
}

/** What the re-check found, in the user's words.
 *
 *  `undefined` means the backend did not answer — which is NOT the same as a
 *  denial and must not be reported as one. */
export function accessRecheckMessage(
  after: AccessRoot | undefined,
  platform: string,
): string {
  if (after === undefined) return "Could not re-check — the backend did not answer.";
  if (after.state === "ok") return "Incurator can now read this folder.";
  if (after.state === "denied") {
    return isMacBackend(platform)
      ? "Still denied. If macOS asked and you allowed it, the grant went to Obsidian "
        + "rather than to the Incurator backend. Grant Full Disk Access to your terminal "
        + "in System Settings > Privacy & Security, then press Re-check."
      : "Still denied. This is a filesystem permission, not a prompt you missed: the "
        + "folder must be readable by the user running the Incurator backend. Check its "
        + "owner and mode, then press Re-check.";
  }
  return after.detail;
}
