import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider } from "./auth";
import { useAuth } from "./authContext";
import { apiRequest } from "../api/client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TEACHER = { id: 1, username: "aymen", display_name: "Aymen" };

/** Surfaces the three auth states as text so tests assert on behaviour, not internals. */
function Probe() {
  const { user, sessionExpired, signIn, signOut } = useAuth();
  return (
    <div>
      <span data-testid="state">
        {user === undefined ? "checking" : user === null ? "signed-out" : user.display_name}
      </span>
      <span data-testid="expired">{sessionExpired ? "expired" : "-"}</span>
      <button onClick={() => void signIn("aymen", "pw").catch(() => {})}>in</button>
      <button onClick={() => void signOut()}>out</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AuthProvider", () => {
  it("starts in a checking state so the login form doesn't flash on reload", async () => {
    // A probe that never settles: the point is what renders *before* the answer arrives.
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
    renderProbe();
    expect(screen.getByTestId("state")).toHaveTextContent("checking");
  });

  it("resolves to the signed-in user when the session cookie is valid", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(TEACHER));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));
  });

  it("treats a 401 from the probe as 'signed out', not as an error", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "no", code: "not_authenticated" }, 401));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));
  });

  it("signs in and keeps the returned user", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: "no" }, 401)) // the mount probe
      .mockResolvedValueOnce(jsonResponse(TEACHER)); // the login
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));

    await userEvent.click(screen.getByText("in"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));
  });

  it("signs out locally even when the logout request fails", async () => {
    // Otherwise a network blip would leave the teacher looking at a signed-in UI that 401s on
    // every action — worse than simply showing the login page.
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(TEACHER))
      .mockRejectedValueOnce(new Error("network down"));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));

    await userEvent.click(screen.getByText("out"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));
  });

  it("drops to signed-out when any request 401s, e.g. a session revoked from the CLI", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(TEACHER));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));

    // An unrelated call — this is the centrally registered interceptor doing the work.
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "expired" }, 401));
    await act(async () => {
      await apiRequest("/students").catch(() => {});
    });

    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));
  });

  it("leaves the user signed in when a request fails for a non-401 reason", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(TEACHER));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));

    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "boom" }, 500));
    await act(async () => {
      await apiRequest("/students").catch(() => {});
    });

    expect(screen.getByTestId("state")).toHaveTextContent("Aymen");
  });
});

describe("AuthProvider — distinguishing an interrupted session from being signed out", () => {
  it("flags an interruption when a signed-in session 401s", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(TEACHER));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));

    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "expired" }, 401));
    await act(async () => {
      await apiRequest("/students").catch(() => {});
    });

    await waitFor(() => expect(screen.getByTestId("expired")).toHaveTextContent("expired"));
  });

  it("does not flag one when the mount probe 401s — that is just being signed out", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "no" }, 401));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));
    expect(screen.getByTestId("expired")).toHaveTextContent("-");
  });

  it("does not flag one when a failed login 401s", async () => {
    // Otherwise mistyping a password would claim your session expired.
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: "no" }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: "wrong" }, 401));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));

    await userEvent.click(screen.getByText("in"));
    await waitFor(() => expect(screen.getByTestId("expired")).toHaveTextContent("-"));
  });

  it("clears the flag once you sign back in", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(TEACHER));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401));
    await act(async () => {
      await apiRequest("/students").catch(() => {});
    });
    await waitFor(() => expect(screen.getByTestId("expired")).toHaveTextContent("expired"));

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(TEACHER));
    await userEvent.click(screen.getByText("in"));
    await waitFor(() => expect(screen.getByTestId("expired")).toHaveTextContent("-"));
  });

  it("does not flag one when you sign out on purpose", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(TEACHER))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("Aymen"));

    await userEvent.click(screen.getByText("out"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signed-out"));
    expect(screen.getByTestId("expired")).toHaveTextContent("-");
  });
});
