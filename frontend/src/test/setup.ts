import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
// The app's real i18n singleton, so tests assert on the copy the teacher actually sees and a
// missing translation key fails a test rather than rendering its own name.
import i18n from "../i18n";

beforeEach(async () => {
  // Locale leaks between tests otherwise: one that switches to French would change every
  // assertion after it.
  await i18n.changeLanguage("en");
});

afterEach(cleanup);
