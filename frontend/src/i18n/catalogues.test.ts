import { describe, expect, it } from "vitest";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

type Catalogue = { [key: string]: string | Catalogue };

/** Every leaf as [dotted key, text]. */
function leaves(node: Catalogue, prefix = ""): [string, string][] {
  return Object.entries(node).flatMap(([key, value]) =>
    typeof value === "string" ? [[prefix + key, value]] : leaves(value, `${prefix}${key}.`),
  );
}

describe("translation catalogues", () => {
  it("have exactly the same keys", () => {
    // A key only in English renders English to a French user; i18next falls back silently.
    const keys = (c: Catalogue) => leaves(c).map(([k]) => k).sort();
    expect(keys(fr as Catalogue)).toEqual(keys(en as Catalogue));
  });

  it("keep French punctuation on its word with a no-break space", () => {
    // French sets a space before : ; ? ! and inside « », and an ordinary one there lets the
    // punctuation wrap onto a line of its own — common on a phone-width screen.
    const loose = / [:;?!»]|« /;
    const offenders = leaves(fr as Catalogue).filter(([, text]) => loose.test(text));
    expect(offenders).toEqual([]);
  });

  it("never glue French punctuation to the word before it", () => {
    const glued = /[\p{L}\d][;?!»]|«\p{L}|\p{L}:/u;
    const offenders = leaves(fr as Catalogue).filter(([, text]) =>
      glued.test(text.replace(/\{\{[^}]*\}\}/g, "x")),
    );
    expect(offenders).toEqual([]);
  });
});
