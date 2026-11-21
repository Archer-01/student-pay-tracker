import { useEffect } from "react";
import { shouldWarm, warmOfflineData } from "./offlineWarmup";

/**
 * Keeps every screen readable offline while the teacher is signed in: a round on opening the
 * app, when the connection comes back, and when the app returns to the front, each only once
 * the stored copy is a quarter of an hour old (see `offlineWarmup.ts`).
 */
export function useOfflineWarmup(): void {
  useEffect(() => {
    // Ask the browser to keep the stored copy rather than clear it when space runs low. An
    // installed app is usually granted this; a refusal just leaves the usual behaviour.
    void navigator.storage?.persist?.().catch(() => undefined);

    const maybeWarm = () => {
      const env = {
        hasWorker: Boolean(navigator.serviceWorker?.controller),
        visible: document.visibilityState === "visible",
      };
      if (shouldWarm(new Date(), env)) void warmOfflineData();
    };
    // Let the first screen load before asking for everything else.
    const first = setTimeout(maybeWarm, 3000);
    const onVisible = () => {
      if (document.visibilityState === "visible") maybeWarm();
    };
    window.addEventListener("online", maybeWarm);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearTimeout(first);
      window.removeEventListener("online", maybeWarm);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
}
