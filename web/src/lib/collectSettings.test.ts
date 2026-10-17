import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, sanitize } from "./collectSettings";

describe("sanitize", () => {
  it("空なら初期値", () => expect(sanitize({})).toEqual(DEFAULT_SETTINGS));
  it("範囲外は丸める", () => {
    expect(sanitize({ threshold: 5, stillSec: 0, maxSec: 99 })).toEqual({ threshold: 0.05, stillSec: 0.5, maxSec: 15 });
  });
  it("数値以外は初期値", () => {
    expect(sanitize({ threshold: "x", stillSec: NaN, maxSec: null })).toEqual(DEFAULT_SETTINGS);
  });
});
