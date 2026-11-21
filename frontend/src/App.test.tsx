import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, within } from "@testing-library/react";
import { useLocation } from "react-router-dom";
import { renderWithProviders } from "./test/render";
import * as endpoints from "./api/endpoints";
import * as warmup from "./lib/useOfflineWarmup";
import { AuthContext, type AuthState } from "./lib/authContext";
import { ThemeProvider } from "./lib/theme";
import App from "./App";

/** Where the router ended up, so a redirect can be checked without knowing each screen's content. */
function LocationProbe() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

const teacher = { id: 1, username: "aymen", display_name: "Aymen Haddad" };

function renderApp(route: string, user: AuthState) {
  return renderWithProviders(
    <>
      <ThemeProvider>
        <AuthContext.Provider value={{ user, sessionExpired: false, signIn: vi.fn(), signOut: vi.fn() }}>
          <App />
        </AuthContext.Provider>
      </ThemeProvider>
      <LocationProbe />
    </>,
    { route },
  );
}

/** Signed in. A default parameter would also swallow an explicit `undefined`, the "still checking" state. */
const renderSignedIn = (route: string) => renderApp(route, teacher);

const location = () => screen.getByTestId("location").textContent;

beforeEach(() => {
  // Every screen stays on its loading state: these tests are about which screen is chosen, and an
  // answer that never comes means no late updates and no real request from a screen left out here.
  for (const [name, value] of Object.entries(endpoints)) {
    if (typeof value === "function") {
      vi.spyOn(endpoints, name as keyof typeof endpoints).mockReturnValue(new Promise(() => {}) as never);
    }
  }
  // The offline copy starts a timer and a round of requests on sign-in; not this file's concern.
  vi.spyOn(warmup, "useOfflineWarmup").mockImplementation(() => {});
  // ThemeProvider reads matchMedia to pick the initial theme, and jsdom has none.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("App — the sign-in gate", () => {
  it("shows only the login screen when signed out, and keeps the deep link", () => {
    // A tree swap, not a redirect: the address bar still says where the teacher was heading.
    renderApp("/students/3", null);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main navigation" })).not.toBeInTheDocument();
    expect(location()).toBe("/students/3");
    expect(endpoints.getStudent).not.toHaveBeenCalled();
  });

  it("lands on the deep-linked page once signed in", () => {
    const { rerender } = renderApp("/students/3", null);
    rerender(
      <>
        <ThemeProvider>
          <AuthContext.Provider value={{ user: teacher, sessionExpired: false, signIn: vi.fn(), signOut: vi.fn() }}>
            <App />
          </AuthContext.Provider>
        </ThemeProvider>
        <LocationProbe />
      </>,
    );
    expect(location()).toBe("/students/3");
    expect(endpoints.getStudent).toHaveBeenCalledWith(3);
  });

  it("shows neither the login form nor the app while the session is being checked", () => {
    // Showing the form here would flash it on every reload for someone already signed in.
    renderApp("/", undefined);
    expect(screen.getByText("Checking your session…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main navigation" })).not.toBeInTheDocument();
    expect(endpoints.getDashboardSummary).not.toHaveBeenCalled();
  });
});

describe("App — signed in", () => {
  it("puts the four places in the menu and the bottom bar, with Home current on /", () => {
    renderSignedIn("/");
    const navs = screen.getAllByRole("navigation", { name: "Main navigation" });
    expect(navs).toHaveLength(2);
    for (const nav of navs) {
      const links = within(nav).getAllByRole("link");
      expect(links.map((l) => l.textContent)).toEqual(["Home", "Students", "Reports", "Settings"]);
      expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    }
    expect(screen.getByText("Aymen Haddad")).toBeInTheDocument();
    expect(endpoints.getDashboardSummary).toHaveBeenCalled();
  });

  it("keeps a section current on the pages under it", () => {
    // Home is `end`, so it must not light up everywhere; Reports covers its tabs.
    renderSignedIn("/reports/annual");
    const nav = screen.getAllByRole("navigation", { name: "Main navigation" })[0];
    expect(within(nav).getByRole("link", { name: "Reports" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
  });

  it.each([
    ["/", () => expect(endpoints.getDashboardSummary).toHaveBeenCalled()],
    ["/students", () => expect(endpoints.listStudents).toHaveBeenCalledWith({ status: "active", q: undefined })],
    ["/students/new", () => expect(screen.getByRole("heading", { name: "Enroll student" })).toBeInTheDocument()],
    ["/students/3", () => expect(endpoints.getStudent).toHaveBeenCalledWith(3)],
    ["/reports/monthly", () => expect(endpoints.getMonthlyReport).toHaveBeenCalled()],
    ["/reports/annual", () => expect(endpoints.getAnnualReport).toHaveBeenCalled()],
    ["/reports/school", () => expect(endpoints.getSchoolShare).toHaveBeenCalled()],
    ["/reports/leavers", () => expect(endpoints.listLeaversWithDebt).toHaveBeenCalled()],
    ["/settings", () => expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument()],
    ["/settings/classes", () => expect(screen.getByRole("heading", { name: "Classes" })).toBeInTheDocument()],
    ["/settings/classes/5", () => expect(endpoints.getClass).toHaveBeenCalledWith(5)],
    ["/settings/packs", () => expect(endpoints.listPacks).toHaveBeenCalled()],
  ])("renders the right screen for %s", (path, check) => {
    renderSignedIn(path);
    expect(location()).toBe(path);
    check();
    expect(screen.queryByText("Page not found")).not.toBeInTheDocument();
  });

  it.each([
    ["/reports", "/reports/monthly"],
    ["/settings/prices", "/settings/packs"],
    // Where pages used to live, so bookmarks still land.
    ["/classes", "/settings/classes"],
    ["/classes/7", "/settings/classes/7"],
    ["/packs", "/settings/packs"],
    ["/debts", "/reports/leavers"],
  ])("sends %s on to %s", (from, to) => {
    renderSignedIn(from);
    expect(location()).toBe(to);
  });

  it("carries the class id through the old class link", () => {
    renderSignedIn("/classes/7");
    expect(endpoints.getClass).toHaveBeenCalledWith(7);
  });

  it("shows Page not found inside the app for an unknown path, with a way home", async () => {
    renderSignedIn("/nope");
    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(screen.getAllByRole("navigation", { name: "Main navigation" })).toHaveLength(2);

    await userEvent.click(screen.getByRole("link", { name: "Back to dashboard" }));
    expect(location()).toBe("/");
    expect(endpoints.getDashboardSummary).toHaveBeenCalled();
  });

  it("opens the payment sheet from the menu's Record payment button", async () => {
    renderSignedIn("/settings");
    await userEvent.click(screen.getByRole("button", { name: "Record payment" }));
    // Started without a student, the sheet asks who first: it loads the active students.
    expect(endpoints.listStudents).toHaveBeenCalledWith({ status: "active", q: undefined });
  });
});
