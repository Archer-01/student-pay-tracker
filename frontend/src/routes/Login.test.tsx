import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/render";
import { Login } from "./Login";
import { AuthContext, type AuthContextValue } from "../lib/authContext";
import { ThemeProvider } from "../lib/theme";

function renderLogin(signIn: AuthContextValue["signIn"], sessionExpired = false) {
  const value: AuthContextValue = { user: null, sessionExpired, signIn, signOut: vi.fn() };
  return renderWithProviders(
    // The login screen carries the theme and language controls, same as every other screen —
    // picking French before signing in is the point, for a teacher who reads the app in French.
    <ThemeProvider>
      <AuthContext.Provider value={value}>
        <Login />
      </AuthContext.Provider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  // ThemeProvider reads both of these to pick the initial theme, and this environment supplies
  // neither (jsdom has no matchMedia; localStorage is absent here too — which is why no other
  // test renders the theme controls).
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  );
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Login", () => {
  it("submits the trimmed username and the password as typed", async () => {
    // Trimmed because a trailing space from a phone keyboard shouldn't fail a login; the
    // password is never trimmed — leading/trailing spaces there are legitimate characters.
    const signIn = vi.fn().mockResolvedValue(undefined);
    renderLogin(signIn);

    await userEvent.type(screen.getByLabelText("Username"), "  aymen  ");
    await userEvent.type(screen.getByLabelText("Password"), " pw ");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(signIn).toHaveBeenCalledWith("aymen", " pw ");
  });

  it("asks for a username before calling the API", async () => {
    const signIn = vi.fn();
    renderLogin(signIn);

    await userEvent.type(screen.getByLabelText("Password"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your username")).toBeInTheDocument();
    expect(signIn).not.toHaveBeenCalled();
  });

  it("asks for a password before calling the API", async () => {
    const signIn = vi.fn();
    renderLogin(signIn);

    await userEvent.type(screen.getByLabelText("Username"), "aymen");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your password")).toBeInTheDocument();
    expect(signIn).not.toHaveBeenCalled();
  });

  it("rejects a whitespace-only username, which `required` would have accepted", async () => {
    const signIn = vi.fn();
    renderLogin(signIn);

    await userEvent.type(screen.getByLabelText("Username"), "   ");
    await userEvent.type(screen.getByLabelText("Password"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your username")).toBeInTheDocument();
    expect(signIn).not.toHaveBeenCalled();
  });

  it("shows the backend's message when the credentials are wrong", async () => {
    const { ApiError } = await import("../api/client");
    const signIn = vi
      .fn()
      .mockRejectedValue(new ApiError(401, "Incorrect username or password", "invalid_credentials"));
    renderLogin(signIn);

    await userEvent.type(screen.getByLabelText("Username"), "aymen");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect username or password");
  });

  it("clears the password but keeps the username after a failed attempt", async () => {
    // Retyping a username you got right is pure friction.
    const { ApiError } = await import("../api/client");
    const signIn = vi.fn().mockRejectedValue(new ApiError(401, "Incorrect username or password"));
    renderLogin(signIn);

    await userEvent.type(screen.getByLabelText("Username"), "aymen");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByLabelText("Password")).toHaveValue(""));
    expect(screen.getByLabelText("Username")).toHaveValue("aymen");
  });

  it("uses a password input so the characters aren't shown on a shared screen", () => {
    renderLogin(vi.fn());
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });
});

describe("Login — interrupted session", () => {
  it("explains why you are here when a session was cut short", async () => {
    // Being bounced to a login form with no explanation is the confusing case; arriving at one
    // normally is not.
    renderLogin(vi.fn(), true);
    expect(screen.getByRole("status")).toHaveTextContent("Your session expired");
  });

  it("says nothing when you simply arrived signed out", () => {
    renderLogin(vi.fn(), false);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("drops the expiry notice once a real error replaces it", async () => {
    // Showing "your session expired" above "incorrect password" is two explanations for one
    // event, and the second is the one that matters.
    const { ApiError } = await import("../api/client");
    const signIn = vi.fn().mockRejectedValue(new ApiError(401, "Incorrect username or password"));
    renderLogin(signIn, true);

    await userEvent.type(screen.getByLabelText("Username"), "aymen");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("marks the username field for password managers", () => {
    renderLogin(vi.fn());
    expect(screen.getByLabelText("Username")).toHaveAttribute("autocomplete", "username");
  });
});
