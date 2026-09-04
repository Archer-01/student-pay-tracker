import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { formatDate, formatMonth } from "./dates";
import { formatMoney } from "./money";
import { slugify } from "./slug";
import { CLASS_LEVELS, classLabel } from "./classes";

describe("formatMoney", () => {
  it("always shows two decimal places", () => {
    expect(formatMoney("300")).toBe("300.00");
    expect(formatMoney("300.5")).toBe("300.50");
  });

  it("follows the active locale", async () => {
    await i18n.changeLanguage("fr");
    // French uses a comma for the decimal separator; the teacher reads these numbers.
    expect(formatMoney("300.00")).toContain(",");
    expect(formatMoney("300.00")).not.toContain(".");
  });

  it("renders zero rather than an empty string", () => {
    expect(formatMoney("0")).toBe("0.00");
  });
});

describe("formatDate", () => {
  it("formats an ISO date", () => {
    expect(formatDate("2023-03-05")).toMatch(/2023/);
  });

  it("returns the input unchanged when it cannot be parsed", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });

  it("does not shift the day across a timezone", () => {
    // Parsed at local midnight on purpose: naive parsing turns 2023-03-05 into the 4th for
    // anyone west of UTC, which would silently misreport due dates.
    expect(formatDate("2023-03-05")).toMatch(/5/);
  });
});

describe("formatMonth", () => {
  it("formats a YYYY-MM month", () => {
    expect(formatMonth("2023-06")).toMatch(/2023/);
  });

  it("returns the input unchanged when it cannot be parsed", () => {
    expect(formatMonth("nope")).toBe("nope");
  });
});

describe("slugify", () => {
  it.each([
    ["Amina Benali", "amina-benali"],
    ["Amïra Bénali", "amira-benali"],
    ["  spaced  out  ", "spaced-out"],
    ["2BAC — Groupe A", "2bac-groupe-a"],
  ])("slugifies %s", (input, expected) => {
    expect(slugify(input)).toBe(expected);
  });

  it("returns an empty string when there is nothing ASCII to keep", () => {
    // The caller then falls back to an id-only filename rather than emitting an empty one.
    expect(slugify("محمد")).toBe("");
  });
});

describe("CLASS_LEVELS", () => {
  it("is in school order, not alphabetical", () => {
    // Sorting the level strings would put 1BAC before 2AC, which is wrong and is exactly the
    // mistake this constant exists to prevent.
    expect(CLASS_LEVELS).toEqual(["1AC", "2AC", "3AC", "TC", "1BAC", "2BAC"]);
    expect(CLASS_LEVELS).not.toEqual([...CLASS_LEVELS].sort());
  });

  it("matches the levels the backend accepts", () => {
    expect(CLASS_LEVELS).toHaveLength(6);
  });
});

describe("classLabel", () => {
  it("composes the level and name", () => {
    expect(classLabel({ level: "2BAC", name: "Groupe A" })).toBe("2BAC — Groupe A");
  });
});
