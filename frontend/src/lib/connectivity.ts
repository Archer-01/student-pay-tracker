import { useSyncExternalStore } from "react";

/**
 * Whether what's on screen is live, a copy stored for offline use, or nothing at all because
 * there's no connection. Fed by the API client from what the service worker answers (see
 * sw/service-worker.js): a stored copy carries the time it was saved; a fresh answer means live.
 *
 * Kept outside React so the plain API client can report into it; screens read it with
 * `useConnectivity()`.
 */
export type Connectivity =
  | { mode: "live" }
  | { mode: "stored"; savedAt: string }
  | { mode: "offline" };

let state: Connectivity = { mode: "live" };
const listeners = new Set<() => void>();

function set(next: Connectivity): void {
  if (JSON.stringify(next) === JSON.stringify(state)) return;
  state = next;
  listeners.forEach((listener) => listener());
}

export function connectivity(): Connectivity {
  return state;
}

/** A fresh answer from the server. */
export function reportLive(): void {
  set({ mode: "live" });
}

/** A stored copy, saved at `savedAt`. The oldest one on screen is the one worth showing. */
export function reportStored(savedAt: string): void {
  if (state.mode === "stored" && state.savedAt <= savedAt) return;
  set({ mode: "stored", savedAt });
}

/** No network, and nothing stored for this request. Keeps a stored time already showing. */
export function reportOffline(): void {
  if (state.mode === "stored") return;
  set({ mode: "offline" });
}

export function resetConnectivity(): void {
  set({ mode: "live" });
}

export function useConnectivity(): Connectivity {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
  );
}

/** Offline, or showing stored data: nothing can be saved, so writes are switched off. */
export function useReadOnly(): boolean {
  return useConnectivity().mode !== "live";
}
