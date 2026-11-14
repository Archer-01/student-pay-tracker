import { useEffect, useState, useCallback } from "react";
import { ApiError } from "../api/client";
import i18n from "../i18n";

export type AsyncState<T> =
  | { status: "loading"; data?: undefined; error?: undefined }
  | { status: "error"; data?: undefined; error: string }
  | { status: "success"; data: T; error?: undefined };

/**
 * Runs `fetcher` on mount and whenever `deps` change; exposes a `reload` to re-run it manually
 * (e.g. after a mutation). Once it has data, later loads keep that data showing until replaced.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[]): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);

  const load = useCallback(() => {
    let cancelled = false;
    // Only the first load shows as loading. A refresh (after a payment, or a new filter) keeps the
    // current data on screen until the new data lands, so rows change in place rather than the
    // page blanking to a placeholder and back.
    setState((prev) => (prev.status === "success" ? prev : { status: "loading" }));
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((err) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : i18n.t("common.error");
        setState({ status: "error", error: message });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  useEffect(() => load(), [load]);

  // Back online: fetch again, so a screen showing stored data turns live without a reload (an
  // installed app has no reload button).
  useEffect(() => {
    const onOnline = () => setTick((t) => t + 1);
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, []);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
