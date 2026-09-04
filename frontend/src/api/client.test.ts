import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./client";

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
