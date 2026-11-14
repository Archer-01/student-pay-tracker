import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, downloadFile, setUnauthorizedHandler } from "./client";
import { connectivity, resetConnectivity } from "../lib/connectivity";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiRequest", () => {
  it("calls the relative API base so requests stay same-origin", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }));
    await apiRequest("/students");
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/api/v1/students");
  });

  it("sends the active locale, so backend errors and exports come back translated", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]));
    await apiRequest("/students");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init?.headers as Record<string, string>)["Accept-Language"]).toBe("en");
  });

  it("omits undefined query parameters instead of sending the string 'undefined'", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]));
    await apiRequest("/students", { query: { status: "active", as_of: undefined } });
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("status=active");
    expect(String(url)).not.toContain("as_of");
  });

  it("returns undefined for 204 rather than trying to parse a body", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiRequest("/classes/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("throws ApiError carrying the machine code on a domain error", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: "No student with id 999", code: "student_not_found" }, 404),
    );
    await expect(apiRequest("/students/999")).rejects.toMatchObject({
      status: 404,
      code: "student_not_found",
    });
  });

  it("survives an error body that is not JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("gateway exploded", { status: 502 }));
    await expect(apiRequest("/students")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("ApiError.message", () => {
  it("passes through a domain error's already-localized detail", () => {
    expect(new ApiError(409, "Une classe existe déjà", "duplicate_class").message).toBe(
      "Une classe existe déjà",
    );
  });

  it("flattens a 422 validation array into something readable", () => {
    // The backend uses two different `detail` shapes; this is the one that would otherwise
    // render as "[object Object]".
    const err = new ApiError(422, [
      { loc: ["body", "first_name"], msg: "Field required", type: "missing" },
    ]);
    expect(err.message).toBe("first_name: Field required");
  });
});

describe("session handling", () => {
  afterEach(() => setUnauthorizedHandler(null));

  it("sends credentials so the browser attaches the HttpOnly session cookie", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]));
    await apiRequest("/students");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.credentials).toBe("include");
  });

  it("sends credentials on downloads too, so PDF exports don't 401", async () => {
    // The exports go through fetch→blob rather than a plain <a href>, which is exactly why they
    // need this: an anchor would have carried the cookie for free, a bare fetch does not.
    vi.mocked(fetch).mockResolvedValue(new Response(new Blob(["pdf"]), { status: 200 }));
    // Patch the two statics onto the real URL rather than replacing the global: `buildUrl` needs
    // `new URL(...)`, and jsdom ships no object-URL support.
    Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} });
    await downloadFile("/reports/annual.pdf", "annual.pdf");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.credentials).toBe("include");
  });

  it("notifies the unauthorized handler on a 401 so the app can show the login page", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "nope" }, 401));

    await expect(apiRequest("/students")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does not notify it for other failures, which are not a session problem", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "boom" }, 500));

    await expect(apiRequest("/students")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("still rejects with the ApiError after notifying, so callers can show the message", async () => {
    setUnauthorizedHandler(vi.fn());
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "Please sign in", code: "not_authenticated" }, 401));

    await expect(apiRequest("/students")).rejects.toMatchObject({
      status: 401,
      code: "not_authenticated",
    });
  });
});

describe("offline (service worker answers)", () => {
  // The service worker stamps a stored copy with when it was saved, and answers 503 "offline"
  // for a screen it never stored. The app reads both, to say it's showing old data.
  afterEach(() => resetConnectivity());

  it("reports stored data, with the time it was saved", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("[]", { headers: { "x-ardoise-saved-at": "2026-11-14T09:41:00.000Z" } }),
    );
    await apiRequest("/students");
    expect(connectivity()).toEqual({ mode: "stored", savedAt: "2026-11-14T09:41:00.000Z" });
  });

  it("goes back to live as soon as a fresh answer arrives", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response("[]", { headers: { "x-ardoise-saved-at": "2026-11-14T09:41:00.000Z" } }),
    );
    await apiRequest("/students");
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([]));
    await apiRequest("/students");
    expect(connectivity()).toEqual({ mode: "live" });
  });

  it("turns 'never stored' into a sentence, not 'something went wrong'", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "offline", code: "offline" }, 503));
    const err = (await apiRequest("/students").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("offline");
    expect(err.message).toMatch(/not available offline yet/i);
    expect(connectivity()).toEqual({ mode: "offline" });
  });

  it("says nothing was saved when a write finds no network", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await apiRequest("/students/1/payments", { method: "POST", body: {} }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network");
    expect(err.message).toMatch(/nothing was saved/i);
    expect(connectivity()).toEqual({ mode: "offline" });
  });
});
