import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { act, renderHook } from "@testing-library/react";
import * as warmup from "./offlineWarmup";
import { reportLive, reportOffline, resetConnectivity } from "./connectivity";
import { WARMUP_STORAGE_KEY } from "./offlineData";
import { useOfflineWarmup } from "./useOfflineWarmup";

const NOW = new Date("2026-11-21T10:00:00");
let visibility: DocumentVisibilityState;
let persist: MockInstance<() => Promise<boolean>>;

/** What a production build has: a service worker in charge of the page. */
function withWorker(controller: object | null = {}) {
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { controller } });
}

function setVisibility(state: DocumentVisibilityState) {
  visibility = state;
  document.dispatchEvent(new Event("visibilitychange"));
}

let warm: MockInstance<typeof warmup.warmOfflineData>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  warm = vi.spyOn(warmup, "warmOfflineData").mockResolvedValue(0);
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
  persist = vi.fn().mockResolvedValue(true);
  Object.defineProperty(navigator, "storage", { configurable: true, value: { persist } });
  withWorker();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  resetConnectivity();
  // Own properties shadowing jsdom's (or adding what jsdom lacks); dropping them restores it.
  delete (document as { visibilityState?: unknown }).visibilityState;
  delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  delete (navigator as { storage?: unknown }).storage;
});

describe("useOfflineWarmup", () => {
  it("lets the first screen load, then copies every screen", () => {
    renderHook(() => useOfflineWarmup());
    vi.advanceTimersByTime(2999);
    expect(warm).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(warm).toHaveBeenCalledTimes(1);
  });

  it("does nothing without a service worker, as in `vite dev`", () => {
    delete (navigator as { serviceWorker?: unknown }).serviceWorker;
    renderHook(() => useOfflineWarmup());
    vi.advanceTimersByTime(3000);
    expect(warm).not.toHaveBeenCalled();
  });

  it("does nothing on the first load of a page the worker doesn't control yet", () => {
    withWorker(null);
    renderHook(() => useOfflineWarmup());
    vi.advanceTimersByTime(3000);
    expect(warm).not.toHaveBeenCalled();
  });

  it("waits while offline, and copies when the connection comes back", () => {
    reportOffline();
    renderHook(() => useOfflineWarmup());
    vi.advanceTimersByTime(3000);
    expect(warm).not.toHaveBeenCalled();

    reportLive();
    act(() => void window.dispatchEvent(new Event("online")));
    expect(warm).toHaveBeenCalledTimes(1);
  });

  it("waits while in the background, and copies when the app returns to the front", () => {
    visibility = "hidden";
    renderHook(() => useOfflineWarmup());
    vi.advanceTimersByTime(3000);
    expect(warm).not.toHaveBeenCalled();

    setVisibility("hidden");
    expect(warm).not.toHaveBeenCalled();
    setVisibility("visible");
    expect(warm).toHaveBeenCalledTimes(1);
  });

  it("skips a round while the last copy is under a quarter of an hour old", () => {
    localStorage.setItem(
      WARMUP_STORAGE_KEY,
      JSON.stringify({ at: new Date(NOW.getTime() - 5 * 60 * 1000).toISOString(), stored: 10 }),
    );
    renderHook(() => useOfflineWarmup());
    vi.advanceTimersByTime(3000);
    expect(warm).not.toHaveBeenCalled();

    vi.setSystemTime(NOW.getTime() + warmup.WARM_EVERY_MS);
    setVisibility("visible");
    expect(warm).toHaveBeenCalledTimes(1);
  });

  it("asks the browser to keep the stored copy", () => {
    renderHook(() => useOfflineWarmup());
    expect(persist).toHaveBeenCalledTimes(1);
  });

  it("carries on when the browser refuses to keep it, or can't be asked", async () => {
    persist.mockRejectedValue(new Error("denied"));
    const { unmount } = renderHook(() => useOfflineWarmup());
    // A rejection left unhandled would fail the run; give it a turn to surface.
    await vi.advanceTimersByTimeAsync(3000);
    expect(warm).toHaveBeenCalledTimes(1);
    unmount();

    delete (navigator as { storage?: unknown }).storage;
    expect(() => renderHook(() => useOfflineWarmup())).not.toThrow();
  });

  it("stops listening once signed out (unmounted)", () => {
    const { unmount } = renderHook(() => useOfflineWarmup());
    unmount();
    vi.advanceTimersByTime(3000);
    window.dispatchEvent(new Event("online"));
    setVisibility("visible");
    expect(warm).not.toHaveBeenCalled();
  });
});
