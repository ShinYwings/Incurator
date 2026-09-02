import { describe, expect, it } from "vitest";
import {
  accessRowOffersGrant,
  accessRecheckMessage,
  accessGrantLabel,
  accessOpenedMessage,
} from "./accessRows";
import type { AccessRoot } from "../agent/incuratorClient";

const root = (over: Partial<AccessRoot>): AccessRoot => ({
  label: "R", path: "/p", state: "ok", grantFolder: "", detail: "", ...over,
});

describe("accessRowOffersGrant", () => {
  it("offers a folder only for a denial", () => {
    expect(accessRowOffersGrant(root({ state: "denied", grantFolder: "/g" }))).toBe(true);
  });

  it("offers nothing for an evicted file — a picker cannot download it", () => {
    expect(accessRowOffersGrant(root({ state: "not_downloaded", grantFolder: "/g" }))).toBe(false);
  });

  it("offers nothing for a missing folder, or a denial with no folder named", () => {
    expect(accessRowOffersGrant(root({ state: "missing", grantFolder: "/g" }))).toBe(false);
    expect(accessRowOffersGrant(root({ state: "denied" }))).toBe(false);
  });
});

describe("accessRecheckMessage", () => {
  it("does not report a silent backend as a denial", () => {
    expect(accessRecheckMessage(undefined, "darwin")).toContain("did not answer");
    expect(accessRecheckMessage(undefined, "linux")).not.toContain("Still denied");
  });

  it("names the responsible-process trap on macOS", () => {
    const msg = accessRecheckMessage(root({ state: "denied" }), "darwin");
    expect(msg).toContain("Still denied");
    expect(msg).toContain("went to Obsidian");
  });

  it("does NOT tell a Linux user to wait for a macOS prompt", () => {
    const msg = accessRecheckMessage(root({ state: "denied" }), "linux");
    expect(msg).toContain("Still denied");
    expect(msg).toContain("filesystem permission");
    expect(msg).not.toMatch(/macOS|Full Disk Access|System Settings/);
  });

  it("confirms success, and passes other verdicts through as the backend worded them", () => {
    expect(accessRecheckMessage(root({ state: "ok" }), "linux")).toContain("can now read");
    expect(accessRecheckMessage(root({ state: "missing", detail: "gone" }), "darwin")).toBe("gone");
  });
});

describe("platform-specific wording", () => {
  it("does not promise a grant on a platform that has no grant dialog", () => {
    expect(accessGrantLabel("darwin")).toBe("Grant access…");
    expect(accessGrantLabel("linux")).toBe("Open folder…");
    expect(accessGrantLabel("")).toBe("Open folder…");
  });

  it("tells a Linux user what actually fixes it after the folder opens", () => {
    expect(accessOpenedMessage("/srv/papers", "darwin")).toContain("macOS asks");
    const linux = accessOpenedMessage("/srv/papers", "linux");
    expect(linux).toContain("readable by the user");
    expect(linux).not.toContain("macOS");
  });
});

describe("accessOpenedMessage", () => {
  it("never claims a folder was opened when nothing opened it", () => {
    const msg = accessOpenedMessage("/srv/papers", "darwin", false);
    expect(msg).not.toContain("Opened");
    expect(msg).toContain("yourself");
    expect(msg).toContain("/srv/papers");
  });

  it("still says so when it did open, on both platforms", () => {
    expect(accessOpenedMessage("/p", "darwin", true)).toContain("Opened /p");
    expect(accessOpenedMessage("/p", "linux", true)).toContain("Opened /p");
  });
});
