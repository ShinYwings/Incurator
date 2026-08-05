import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

/**
 * B1 / plugin_lifecycle-2: the reposition listeners are attached to
 * `this.activeWin`, which is derived from `this.activeDoc` — and `activeDoc`
 * moves whenever the user selects text in another window (a popout). Detaching
 * against the *current* `activeWin` therefore targeted the wrong window and
 * stranded a capture-phase `scroll` listener on the original one for the rest
 * of the session.
 */
const source = () =>
  readFileSync(join(__dirname, "quickQueryPopover.ts"), "utf8");

describe("Quick Query reposition listener lifetime", () => {
  it("remembers the window it attached to", () => {
    const src = source();
    expect(src).toContain("private repositionWin: Window | null = null;");
    expect(src).toContain("this.repositionWin = win;");
  });

  it("detaches from the attach-time window, not the current one", () => {
    const src = source();
    expect(src).toContain("const win = this.repositionWin ?? this.activeWin;");
    expect(src).toContain('win.removeEventListener("scroll", this.repositionHandler, true);');
    // The old shape removed against whatever window happened to be active.
    expect(src).not.toContain(
      'this.activeWin.removeEventListener("scroll", this.repositionHandler, true);'
    );
  });

  it("clears the remembered window on detach so it cannot go stale", () => {
    const src = source();
    expect(src).toContain("this.repositionWin = null;");
  });

  it("tears the old button down before activeDoc moves to another window", () => {
    const src = source();
    expect(src).toMatch(
      /if \(doc !== this\.activeDoc\) this\.removeButton\(\);\s*\n\s*this\.activeDoc = doc;/
    );
  });
});
