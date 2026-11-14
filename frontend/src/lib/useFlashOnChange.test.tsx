import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useFlashOnChange } from "./useFlashOnChange";

describe("useFlashOnChange", () => {
  it("stays still on first render, so opening a screen animates nothing", () => {
    const { result } = renderHook(() => useFlashOnChange("240 DH"));
    expect(result.current.flashing).toBe(false);
  });

  it("flashes once when the value changes, until the animation ends", () => {
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v), { initialProps: { v: "240 DH" } });
    rerender({ v: "À jour" });
    expect(result.current.flashing).toBe(true);
    act(() => result.current.done());
    expect(result.current.flashing).toBe(false);
    rerender({ v: "À jour" });
    expect(result.current.flashing).toBe(false);
  });
});
