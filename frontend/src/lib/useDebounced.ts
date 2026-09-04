import { useEffect, useState } from "react";

/**
 * The value, but only after it has stopped changing for `delay` ms.
 *
 * Used for lookups that fire from a text field. Without it, `useApi` re-runs on every keystroke:
 * typing "Amina Benali" sent a dozen requests to an endpoint that scans every student, and only
 * the last answer was ever shown.
 */
export function useDebounced<T>(value: T, delay = 300): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return settled;
}
