import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useDebounced } from "./useDebounced";

describe("useDebounced", () => {
  it("holds the previous value until the input settles", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 300), {
      initialProps: { v: "A" },
    });
    rerender({ v: "Am" });
    rerender({ v: "Ami" });
    expect(result.current).toBe("A"); // nothing has settled yet

    act(() => void vi.advanceTimersByTime(300));
    expect(result.current).toBe("Ami"); // one update, not three
    vi.useRealTimers();
  });

  it("restarts the wait on every change", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 300), {
      initialProps: { v: "A" },
    });
    act(() => void vi.advanceTimersByTime(200));
    rerender({ v: "B" });
    act(() => void vi.advanceTimersByTime(200));
    expect(result.current).toBe("A"); // the second keystroke reset the clock

    act(() => void vi.advanceTimersByTime(100));
    expect(result.current).toBe("B");
    vi.useRealTimers();
  });
});
