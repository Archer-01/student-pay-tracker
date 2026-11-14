import { describe, expect, it } from "vitest";
import { whatsappLink, whatsappNumber } from "./phone";

describe("whatsappNumber", () => {
  it.each([
    ["0612345678", "212612345678"],
    ["06 12 34 56 78", "212612345678"],
    ["06-12-34-56-78", "212612345678"],
    ["0712345678", "212712345678"],
    ["+212 6 12 34 56 78", "212612345678"],
    ["+212 (0)6 12 34 56 78", "212612345678"],
    ["00212612345678", "212612345678"],
    ["212612345678", "212612345678"],
    ["612345678", "212612345678"],
    ["+33 6 12 34 56 78", "33612345678"],
  ])("turns %s into %s", (input, expected) => {
    // Numbers are stored as the teacher typed them, almost always the Moroccan local form;
    // WhatsApp needs the international one, digits only.
    expect(whatsappNumber(input)).toBe(expected);
  });

  it.each(["", "123", "06 12", "not a number"])("gives up on %j rather than guessing", (input) => {
    expect(whatsappNumber(input)).toBeNull();
  });
});

describe("whatsappLink", () => {
  it("opens a chat with the number", () => {
    expect(whatsappLink("06 12 34 56 78")).toBe("https://wa.me/212612345678");
  });

  it("has no link for a number it can't read", () => {
    expect(whatsappLink("123")).toBeNull();
  });
});
