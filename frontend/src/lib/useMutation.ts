import { useCallback, useState } from "react";
import { ApiError } from "../api/client";

type MutationState<T> =
  | { status: "idle"; data?: undefined; error?: undefined }
  | { status: "pending"; data?: undefined; error?: undefined }
  | { status: "error"; data?: undefined; error: string }
  | { status: "success"; data: T; error?: undefined };

/**
 * The write counterpart to `useApi`: wraps an async mutation (POST/PATCH) and tracks
 * idle → pending → success | error. `mutate` resolves with the result (or throws) so callers
 * can chain a `reload()` on success. Errors are flattened to a string via `ApiError.message`.
 */
export function useMutation<TArgs extends unknown[], TResult>(fn: (...args: TArgs) => Promise<TResult>) {
  const [state, setState] = useState<MutationState<TResult>>({ status: "idle" });

  const mutate = useCallback(
    async (...args: TArgs): Promise<TResult> => {
      setState({ status: "pending" });
      try {
        const data = await fn(...args);
        setState({ status: "success", data });
        return data;
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong";
        setState({ status: "error", error: message });
        throw err;
      }
    },
    [fn],
  );

  const reset = useCallback(() => setState({ status: "idle" }), []);

  return { ...state, mutate, reset };
}
