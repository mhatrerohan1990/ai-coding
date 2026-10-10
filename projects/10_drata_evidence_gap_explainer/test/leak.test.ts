import { describe, expect, it } from "vitest";
import { findLeaks } from "../src/gap/leak.js";

describe("findLeaks", () => {
  it("returns a secret that appears in the text", () => {
    expect(findLeaks("Your key is sk-live-12345, please rotate it.", ["sk-live-12345"])).toEqual([
      "sk-live-12345",
    ]);
  });

  it("returns [] when no secret appears", () => {
    expect(findLeaks("MFA is not enforced for all users.", ["sk-live-12345"])).toEqual([]);
  });

  it("ignores secrets shorter than 4 characters", () => {
    expect(findLeaks("The abc service is down.", ["abc"])).toEqual([]);
  });

  it("keeps a secret of exactly 4 characters", () => {
    expect(findLeaks("The pass is wxyz.", ["wxyz"])).toEqual(["wxyz"]);
  });

  it("ignores empty secrets", () => {
    expect(findLeaks("anything at all", [""])).toEqual([]);
  });

  it("detects a secret that appears inside a longer word", () => {
    expect(findLeaks("The value hunter2000x was exposed.", ["hunter2"])).toEqual(["hunter2"]);
  });

  it("matches case-sensitively", () => {
    expect(findLeaks("token is ABCD1234", ["abcd1234"])).toEqual([]);
  });

  it("dedupes repeated secrets and repeated occurrences", () => {
    expect(findLeaks("sk-live-1 and sk-live-1 again", ["sk-live-1", "sk-live-1"])).toEqual(["sk-live-1"]);
  });
});
