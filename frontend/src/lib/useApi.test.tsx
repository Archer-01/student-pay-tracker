import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { ApiError } from "../api/client";
import { useApi } from "./useApi";
import { useMutation } from "./useMutation";

describe("useApi", () => {
  it("moves from loading to success", async () => {
    const { result } = renderHook(() => useApi(() => Promise.resolve(["a"]), []));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toEqual(["a"]);
  });

  it("surfaces an ApiError's message", async () => {
    const failing = () => Promise.reject(new ApiError(404, "No student with id 9", "x"));
    const { result } = renderHook(() => useApi(failing, []));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("No student with id 9");
  });

  it("does not leak an unexpected error's text to the user", async () => {
    const { result } = renderHook(() => useApi(() => Promise.reject(new TypeError("boom")), []));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Something went wrong");
  });

  it("refetches on reload, which is how a screen refreshes after a mutation", async () => {
    const fetcher = vi.fn().mockResolvedValue("first");
    const { result } = renderHook(() => useApi(fetcher, []));
    await waitFor(() => expect(result.current.status).toBe("success"));

    fetcher.mockResolvedValue("second");
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe("second"));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("refetches when a dependency changes", async () => {
    const fetcher = vi.fn().mockResolvedValue("x");
    const { rerender } = renderHook(({ dep }) => useApi(fetcher, [dep]), {
      initialProps: { dep: 1 },
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    rerender({ dep: 2 });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });
});

describe("useMutation", () => {
  it("reports idle, then pending, then success", async () => {
    const { result } = renderHook(() => useMutation((n: number) => Promise.resolve(n * 2)));
    expect(result.current.status).toBe("idle");
    await act(async () => {
      await result.current.mutate(21);
    });
    expect(result.current.status).toBe("success");
    expect(result.current.data).toBe(42);
  });

  it("rethrows so the caller can branch on the failure", async () => {
    const err = new ApiError(409, "already exists", "duplicate_class");
    const { result } = renderHook(() => useMutation(() => Promise.reject(err)));
    await act(async () => {
      await expect(result.current.mutate()).rejects.toBe(err);
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("already exists");
  });

  it("resolves with the result so callers can chain a reload", async () => {
    const { result } = renderHook(() => useMutation(() => Promise.resolve({ id: 7 })));
    let returned: { id: number } | undefined;
    await act(async () => {
      returned = await result.current.mutate();
    });
    expect(returned).toEqual({ id: 7 });
  });
});
