import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, OFFLINE_CODES, type Health } from "./lib/api";

const POLL_MS = 30_000;
// While the backend is unreachable, check often so the page recovers by itself once it's started
const OFFLINE_POLL_MS = 4_000;

interface HealthState {
  health: Health | null;
  /** Set when the backend itself can't be reached */
  error: string | null;
  /** The backend isn't answering at all (not started, or another server on this address) */
  offline: boolean;
  errorCode: string | null;
  loading: boolean;
  refresh: () => void;
}

const HealthContext = createContext<HealthState | null>(null);

export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      setHealth(await api.health(signal));
      setError(null);
    } catch (e) {
      if (signal?.aborted) return;
      setHealth(null);
      setError(e instanceof ApiError ? e : new ApiError("NETWORK", 0, "Can't reach the backend."));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  const offline = !!error && OFFLINE_CODES.has(error.code);

  useEffect(() => {
    const ctrl = new AbortController();
    refresh(ctrl.signal);
    const id = setInterval(() => refresh(ctrl.signal), offline ? OFFLINE_POLL_MS : POLL_MS);
    return () => {
      ctrl.abort();
      clearInterval(id);
    };
  }, [refresh, offline]);

  return (
    <HealthContext.Provider
      value={{
        health,
        error: error?.message ?? null,
        errorCode: error?.code ?? null,
        offline,
        loading,
        refresh: () => void refresh(),
      }}
    >
      {children}
    </HealthContext.Provider>
  );
}

export function useHealth(): HealthState {
  const ctx = useContext(HealthContext);
  if (!ctx) throw new Error("useHealth must be used inside HealthProvider");
  return ctx;
}
