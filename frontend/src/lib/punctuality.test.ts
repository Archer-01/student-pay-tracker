import { describe, expect, it } from "vitest";
import { punctualityOf } from "./punctuality";

describe("punctualityOf", () => {
  it.each([
    [0, "on_time"],
    [2, "on_time"], // a day or two is normal life
    [3, "bit_late"],
    [7, "bit_late"],
    [8, "often_late"],
    [30, "often_late"],
  ] as const)("an average of %i days late reads as %s", (days, group) => {
    expect(punctualityOf(days)).toBe(group);
  });

  it("says nothing about a student with no payment due yet", () => {
    expect(punctualityOf(null)).toBeNull();
  });
});
