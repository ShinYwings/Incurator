import { describe, expect, it } from "vitest";
import { hashBufferSha256 } from "./fileHash";

describe("fileHash", () => {
  it("computes sha256 content hashes for source status lookup", () => {
    expect(hashBufferSha256("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
  });
});
