/** The service worker's store of each screen's last data (see sw/service-worker.js). */
export const OFFLINE_DATA_CACHE = "ardoise-data";
/** Where `offlineWarmup.ts` remembers when it last copied every screen. */
export const WARMUP_STORAGE_KEY = "ardoise.offlineWarmup";

/**
 * Drop the stored copy of the data. Called on sign-in, sign-out and an expired session, so one
 * account's students never show for another on a shared phone. Never throws: without the Cache
 * API (tests, old browsers, private modes) there is simply nothing to clear.
 */
export async function clearOfflineData(): Promise<void> {
  try {
    // Forget when the last full copy was made too, so the next account gets one straight away.
    localStorage.removeItem(WARMUP_STORAGE_KEY);
  } catch {
    // storage blocked: nothing was remembered either
  }
  try {
    if ("caches" in globalThis) await caches.delete(OFFLINE_DATA_CACHE);
  } catch {
    // nothing stored, or nothing to store into
  }
}
