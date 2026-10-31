import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, type Health } from "./lib/api";

const POLL_MS = 30_000;

interface HealthState {
  health: Health | null;
  /** Set when the backend itself can't be reached */
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

const HealthContext = createContext<HealthState | null>(null);

export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      setHealth(await api.health(signal));
      setError(null);
    } catch (e) {
      if (signal?.aborted) return;
      setHealth(null);
      setError(e instanceof ApiError ? e.message : "Can't reach the server.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    refresh(ctrl.signal);
    const id = setInterval(() => refresh(ctrl.signal), POLL_MS);
    return () => {
      ctrl.abort();
      clearInterval(id);
    };
  }, [refresh]);

  return (
    <HealthContext.Provider value={{ health, error, loading, refresh: () => void refresh() }}>
      {children}
    </HealthContext.Provider>
  );
}

export function useHealth(): HealthState {
  const ctx = useContext(HealthContext);
  if (!ctx) throw new Error("useHealth must be used inside HealthProvider");
  return ctx;
}
