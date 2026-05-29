import { describe, expect, it } from "vitest";
import {
  normalizeFileScrollPosition,
  normalizeLastMarkdownScrollPosition,
  upsertFileScrollPosition,
} from "./scrollPositions";

describe("scrollPositions", () => {
  it("normalizes existing scroll positions without updatedAt", () => {
    expect(normalizeFileScrollPosition({ scroll: 120, line: 8, ch: 3 })).toEqual({
      scroll: 120,
      line: 8,
      ch: 3,
      updatedAt: 0,
    });
  });

  it("rejects invalid scroll positions", () => {
    expect(normalizeFileScrollPosition({ scroll: -1, line: 8, ch: 3 })).toBeNull();
    expect(normalizeFileScrollPosition({ scroll: 1, line: "8", ch: 3 })).toBeNull();
  });

  it("normalizes the last markdown shutdown position", () => {
    expect(
      normalizeLastMarkdownScrollPosition({
        path: "03_Notes/Papers/paper.md",
        scroll: 400,
        line: 30,
        ch: 2,
        updatedAt: 12,
      })
    ).toEqual({
      path: "03_Notes/Papers/paper.md",
      scroll: 400,
      line: 30,
      ch: 2,
      updatedAt: 12,
    });
  });

  it("rejects a last markdown position without a path", () => {
    expect(
      normalizeLastMarkdownScrollPosition({ scroll: 400, line: 30, ch: 2 })
    ).toBeNull();
  });

  it("upserts the latest position and caps old entries", () => {
    const positions = upsertFileScrollPosition(
      {
        "old.md": { scroll: 1, line: 1, ch: 0, updatedAt: 1 },
        "older.md": { scroll: 2, line: 2, ch: 0, updatedAt: 0 },
      },
      "new.md",
      { scroll: 300, line: 20, ch: 4 },
      2,
      10
    );

    expect(Object.keys(positions)).toEqual(["new.md", "old.md"]);
    expect(positions["new.md"]).toMatchObject({
      scroll: 300,
      line: 20,
      ch: 4,
      updatedAt: 10,
    });
  });
});
