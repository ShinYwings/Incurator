import { describe, expect, it } from "vitest";
import { accessRowOffersGrant, accessRecheckMessage } from "./accessRows";
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
    expect(accessRecheckMessage(undefined)).toContain("did not answer");
    expect(accessRecheckMessage(undefined)).not.toContain("Still denied");
  });

  it("names the responsible-process trap when it is still denied", () => {
    const msg = accessRecheckMessage(root({ state: "denied" }));
    expect(msg).toContain("Still denied");
    expect(msg).toContain("went to Obsidian");
  });

  it("confirms success, and passes other verdicts through as the backend worded them", () => {
    expect(accessRecheckMessage(root({ state: "ok" }))).toContain("can now read");
    expect(accessRecheckMessage(root({ state: "missing", detail: "gone" }))).toBe("gone");
  });
});
