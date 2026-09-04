import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { ApiError } from "../api/client";
import { fieldErrors, resolveErrorMessage } from "./errors";

const t = i18n.getFixedT("en");

describe("resolveErrorMessage", () => {
  it("uses the backend's localized detail for a domain error", () => {
    const err = new ApiError(409, "A 2BAC class named 'Groupe A' already exists", "duplicate_class");
    expect(resolveErrorMessage(err, t)).toContain("already exists");
  });

  it("falls back to a generic message for a non-API failure", () => {
    expect(resolveErrorMessage(new TypeError("network down"), t)).toBe(t("errors.generic"));
  });

  it("flattens a validation error rather than showing an object", () => {
    const err = new ApiError(422, [{ loc: ["body", "price"], msg: "must be >= 0", type: "x" }]);
    expect(resolveErrorMessage(err, t)).toBe("price: must be >= 0");
  });
});

describe("fieldErrors", () => {
  it("keys messages by field so a form can show them inline", () => {
    const err = new ApiError(422, [
      { loc: ["body", "first_name"], msg: "Field required", type: "missing" },
      { loc: ["body", "custom_price"], msg: "must be >= 0", type: "value_error" },
    ]);
    expect(fieldErrors(err)).toEqual({
      first_name: "Field required",
      custom_price: "must be >= 0",
    });
  });

  it("keeps the first message when a field has several", () => {
    const err = new ApiError(422, [
      { loc: ["body", "price"], msg: "first", type: "a" },
      { loc: ["body", "price"], msg: "second", type: "b" },
    ]);
    expect(fieldErrors(err).price).toBe("first");
  });

  it("returns nothing for a domain error, which has no per-field detail", () => {
    expect(fieldErrors(new ApiError(404, "gone", "student_not_found"))).toEqual({});
  });

  it("returns nothing for a non-API error", () => {
    expect(fieldErrors(new Error("boom"))).toEqual({});
  });
});
