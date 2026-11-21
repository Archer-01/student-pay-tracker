import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { act, renderWithProviders, screen } from "../test/render";
import { Settings } from "./Settings";
import { AuthContext, type AuthContextValue } from "../lib/authContext";
import { ThemeProvider } from "../lib/theme";
import { THEME_STORAGE_KEY } from "../lib/themeContext";
import { WARMUP_STORAGE_KEY } from "../lib/offlineData";
import { WARMED_EVENT } from "../lib/offlineWarmup";

const teacher = { id: 1, username: "aymen", display_name: "Aymen Haddani" };

function renderSettings(overrides: Partial<AuthContextValue> = {}) {
  const value: AuthContextValue = {
    user: teacher,
    sessionExpired: false,
    signIn: vi.fn(),
    signOut: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  renderWithProviders(
    <ThemeProvider>
      <AuthContext.Provider value={value}>
        <Routes>
          <Route path="/" element={<Settings />} />
          <Route path="/settings/packs" element={<p>Packs page</p>} />
          <Route path="/settings/classes" element={<p>Classes page</p>} />
        </Routes>
      </AuthContext.Provider>
    </ThemeProvider>,
  );
  return value;
}

/** What the teacher would have after a round of `warmOfflineData`. */
function storeWarmup(at: string) {
  localStorage.setItem(WARMUP_STORAGE_KEY, JSON.stringify({ at, stored: 42 }));
}

beforeEach(() => {
  // ThemeProvider reads matchMedia to follow the device, and jsdom has none.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "";
});

describe("Settings", () => {
  it("says who is signed in on this device", () => {
    renderSettings();
    expect(screen.getByText("Aymen Haddani")).toBeInTheDocument();
    expect(screen.getByText("Signed in on this device")).toBeInTheDocument();
  });

  it("names nobody while the session is still being checked", () => {
    renderSettings({ user: undefined });
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByText("Signed in on this device")).not.toBeInTheDocument();
  });

  it("leads to the packs", async () => {
    renderSettings();
    await userEvent.click(screen.getByRole("link", { name: "Packs" }));
    expect(screen.getByText("Packs page")).toBeInTheDocument();
  });

  it("leads to the classes", async () => {
    renderSettings();
    await userEvent.click(screen.getByRole("link", { name: "Classes" }));
    expect(screen.getByText("Classes page")).toBeInTheDocument();
  });

  it("switches the whole screen to French, and remembers it", async () => {
    renderSettings();
    const language = screen.getByRole("radiogroup", { name: "Language" });
    expect(screen.getByRole("radio", { name: "English" })).toHaveAttribute("aria-checked", "true");

    await userEvent.click(screen.getByRole("radio", { name: "Français" }));

    expect(await screen.findByRole("heading", { name: "Réglages" })).toBeInTheDocument();
    expect(language).toHaveAccessibleName("Langue");
    expect(screen.getByRole("radio", { name: "Français" })).toHaveAttribute("aria-checked", "true");
    expect(localStorage.getItem("ardoise.locale")).toBe("fr");
  });

  it("follows the device by default, and remembers an explicit theme", async () => {
    renderSettings();
    expect(screen.getByRole("radio", { name: "Match device" })).toHaveAttribute("aria-checked", "true");

    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));

    expect(screen.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Match device" })).toHaveAttribute("aria-checked", "false");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    // Back to following the device forgets the choice.
    await userEvent.click(screen.getByRole("radio", { name: "Match device" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("opens on the theme chosen last time", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    renderSettings();
    expect(screen.getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "true");
  });

  it("signs out", async () => {
    const auth = renderSettings();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(auth.signOut).toHaveBeenCalledTimes(1);
  });
});

describe("Settings › Offline", () => {
  it("says nothing has been copied yet, and how it will happen", () => {
    renderSettings();
    expect(screen.getByRole("heading", { name: "Offline" })).toBeInTheDocument();
    expect(screen.getByText("Not copied for offline use yet")).toBeInTheDocument();
    expect(
      screen.getByText("It happens on its own once Ardoise is installed and online for a moment."),
    ).toBeInTheDocument();
  });

  it("says when the last copy was made", () => {
    storeWarmup("2026-11-20T12:00:00.000Z");
    renderSettings();
    expect(screen.getByText("Every screen can be read without a connection")).toBeInTheDocument();
    expect(screen.getByText(/^Copied on Nov 20, 2026 at /)).toBeInTheDocument();
  });

  it("updates as soon as a round finishes, without leaving the screen", () => {
    renderSettings();
    expect(screen.getByText("Not copied for offline use yet")).toBeInTheDocument();

    act(() => {
      storeWarmup("2026-11-21T09:00:00.000Z");
      window.dispatchEvent(new Event(WARMED_EVENT));
    });

    expect(screen.getByText("Every screen can be read without a connection")).toBeInTheDocument();
    expect(screen.getByText(/^Copied on Nov 21, 2026 at /)).toBeInTheDocument();
  });

  it("treats an unreadable record as no copy rather than breaking the screen", () => {
    localStorage.setItem(WARMUP_STORAGE_KEY, "{not json");
    renderSettings();
    expect(screen.getByText("Not copied for offline use yet")).toBeInTheDocument();
  });
});
