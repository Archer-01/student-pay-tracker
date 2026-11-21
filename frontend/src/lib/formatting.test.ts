import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { formatDate, formatMonth, formatMonthInSentence, formatMonthShort, localIso } from "./dates";
import { formatMoney } from "./money";
import { slugify } from "./slug";
import { CLASS_LEVELS, classLabel } from "./classes";

describe("formatMoney", () => {
  it("says DH, and drops cents when there are none", () => {
    // Fees are whole dirhams; "240,00" reads as noise to the teacher, "240 DH" reads as money.
    expect(formatMoney("300")).toBe("300\u00a0DH");
    expect(formatMoney("300.00")).toBe("300\u00a0DH");
  });

  it("keeps cents when there are some", () => {
    expect(formatMoney("300.5")).toBe("300.50\u00a0DH");
    expect(formatMoney("12.05")).toBe("12.05\u00a0DH");
  });

  it("follows the active locale", async () => {
    await i18n.changeLanguage("fr");
    // A decimal comma, and digits grouped by a space the line can't break at.
    expect(formatMoney("300.50")).toBe("300,50\u00a0DH");
    expect(formatMoney("1234")).toMatch(/^1\s234\u00a0DH$/u);
  });

  it("renders zero rather than an empty string", () => {
    expect(formatMoney("0")).toBe("0\u00a0DH");
  });

  it("can leave the currency off, for a figure inside a sentence that already says it", () => {
    expect(formatMoney("240.00", { currency: false })).toBe("240");
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

describe("formatMonthShort", () => {
  // A chart's axis label: one letter left "J J" and "M M" for the teacher to tell apart.
  const schoolYear = ["09", "10", "11", "12", "01", "02", "03", "04", "05", "06", "07", "08"];

  it("tells every month apart, in French", async () => {
    await i18n.changeLanguage("fr");
    const labels = schoolYear.map((m) => formatMonthShort(`2026-${m}`));
    expect(labels).toEqual(["Sept", "Oct", "Nov", "Déc", "Janv", "Févr", "Mars", "Avr", "Mai", "Juin", "Juil", "Août"]);
  });

  it("tells every month apart, in English", async () => {
    await i18n.changeLanguage("en");
    const labels = schoolYear.map((m) => formatMonthShort(`2026-${m}`));
    expect(labels).toEqual(["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]);
  });

  it("returns the input unchanged when it cannot be parsed", () => {
    expect(formatMonthShort("nope")).toBe("nope");
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

describe("localIso", () => {
  it("gives the day where the phone is, not the UTC day", () => {
    // Half past midnight locally: in Morocco toISOString() would still say the 21st.
    expect(localIso(new Date(2026, 10, 22, 0, 30))).toBe("2026-11-22");
    expect(localIso(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });
});

describe("formatMonthInSentence", () => {
  it("is lowercase in French and keeps the year on the month's line", async () => {
    await i18n.changeLanguage("fr");
    expect(formatMonthInSentence("2026-10")).toBe("octobre\u00a02026");
    await i18n.changeLanguage("en");
    expect(formatMonthInSentence("2026-10")).toBe("October\u00a02026");
  });
});
