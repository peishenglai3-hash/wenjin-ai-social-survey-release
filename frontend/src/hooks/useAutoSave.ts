import { useRef, useEffect } from "react";
import { useApp } from "./useApp";

/**
 * Parses an auto_save_interval string like "30s", "60s", "120s", "300s"
 * into milliseconds. Returns null if parsing fails or interval is 0.
 */
function parseIntervalMs(interval: string | undefined): number | null {
  if (!interval) return null;
  const match = interval.match(/^(\d+)\s*s$/i);
  if (!match) return null;
  const seconds = parseInt(match[1], 10);
  if (seconds <= 0) return null;
  return seconds * 1000;
}

/**
 * useAutoSave — periodically invokes a save callback when there is
 * unsaved content, driven by the user's auto_save_interval setting.
 *
 * Usage:
 *   const [dirty, setDirty] = useState(false);
 *   useAutoSave(dirty, () => saveMyContent());
 *
 * The hook reads auto_save_interval from the global profile context
 * and only fires when dirty === true.
 */
export function useAutoSave(
  dirty: boolean,
  saveFn: () => Promise<void> | void,
) {
  const { profile } = useApp();
  const saveFnRef = useRef(saveFn);
  const dirtyRef = useRef(dirty);
  const lastSavedRef = useRef<string | null>(null);

  // Keep refs in sync so the interval callback never captures stale closures
  useEffect(() => { saveFnRef.current = saveFn; }, [saveFn]);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);

  const intervalMs = parseIntervalMs(profile?.auto_save_interval);

  useEffect(() => {
    if (!intervalMs) return;

    const id = setInterval(() => {
      if (!dirtyRef.current) return;
      try {
        const result = saveFnRef.current();
        if (result instanceof Promise) {
          result.catch(() => {});
        }
        lastSavedRef.current = new Date().toISOString();
      } catch {
        // swallow — auto-save must never throw to the console
      }
    }, intervalMs);

    return () => clearInterval(id);
  }, [intervalMs]);

  return {
    /** ISO timestamp of the last auto-save, or null if never saved. */
    lastSaved: lastSavedRef,
  };
}
