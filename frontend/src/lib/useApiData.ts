"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

interface Result<T> {
  source: () => Promise<T>;
  data: T | null;
  error: string | null;
}

/**
 * Loads data for a screen. Pass a loader memoised with useCallback: a new
 * loader identity triggers a fetch. While it runs, the previous data stays on
 * screen (flagged stale) rather than flashing to empty.
 */
export function useApiData<T>(load: () => Promise<T>) {
  const [result, setResult] = useState<Result<T> | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((data) => {
        if (!cancelled) setResult({ source: load, data, error: null });
      })
      .catch((err: unknown) => {
        // A 401 has already sent the user to sign in.
        if (cancelled || (err instanceof ApiError && err.status === 401)) return;
        const message = err instanceof ApiError ? err.message : "Could not load this page.";
        setResult((prev) => ({ source: load, data: prev?.data ?? null, error: message }));
      });
    return () => {
      cancelled = true;
    };
  }, [load, nonce]);

  const current = result?.source === load;
  return {
    data: result?.data ?? null,
    error: current ? result.error : null,
    loading: !current,
    reload: () => setNonce((n) => n + 1),
  };
}

/** The value, once it has stopped changing for `delayMs`. */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return settled;
}
