import { useEffect, useState } from "react";

/**
 * Sliders fire on every pixel of drag. Without this, dragging the minimum
 * balance across its range would queue ~200 POSTs. The debounced value is what
 * feeds the query key, so React re-renders instantly while the network waits.
 */
export function useDebounced<T>(value: T, delayMs = 250): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return settled;
}