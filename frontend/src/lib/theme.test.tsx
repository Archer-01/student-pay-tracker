import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import { ThemeProvider } from "./theme";
import { useTheme } from "./themeContext";

let setPreference: ReturnType<typeof useTheme>["setPreference"];
function Grab() {
  setPreference = useTheme().setPreference;
  return null;
}

const statusBar = () => document.querySelector('meta[name="theme-color"]')?.getAttribute("content");

beforeEach(() => {
  // jsdom has no matchMedia; the device is "light" here.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  );
  const meta = document.createElement("meta");
  meta.name = "theme-color";
  meta.content = "#f3f6f5";
  document.head.appendChild(meta);
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.head.querySelector('meta[name="theme-color"]')?.remove();
  document.documentElement.classList.remove("dark");
});

describe("ThemeProvider", () => {
  it("colours the status bar like the page, following an explicit choice", () => {
    // Installed as an app, the status bar is the page's top edge; a green or white band over a
    // dark page would look broken.
    render(
      <ThemeProvider>
        <Grab />
      </ThemeProvider>,
    );
    act(() => setPreference("dark"));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(statusBar()).toBe("#111615");
    act(() => setPreference("light"));
    expect(statusBar()).toBe("#f3f6f5");
  });
});
