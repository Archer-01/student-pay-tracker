import { useState } from "react";

/**
 * True for one animation after `value` changes, never on first render. Lets a pill or a tile
 * acknowledge that it just changed ("240 DH" → "À jour" after a payment) without animating every
 * time a screen opens.
 *
 * Uses React's "adjust state while rendering" pattern rather than an effect, so the flash starts
 * in the same frame as the new value. Pass `done` as the element's `onAnimationEnd`.
 */
export function useFlashOnChange<T>(value: T): { flashing: boolean; done: () => void } {
  const [seen, setSeen] = useState(value);
  const [flashing, setFlashing] = useState(false);
  if (!Object.is(value, seen)) {
    setSeen(value);
    setFlashing(true);
  }
  return { flashing, done: () => setFlashing(false) };
}
