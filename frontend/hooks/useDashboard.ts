/**
 * Dashboard Data Hook
 * Fetches dashboard summary with auto-refresh
 */

import { useEffect, useCallback, useRef } from "react";
import { getDashboard } from "../lib/api";
import { useAppStore } from "../store/useAppStore";
import { DashboardSummary } from "../lib/types";

interface UseDashboardResult {
  dashboard: DashboardSummary | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const REFRESH_INTERVAL = 30000; // 30 seconds

/**
 * Custom hook for dashboard data with auto-refresh
 */
export function useDashboard(): UseDashboardResult {
  const dashboard = useAppStore((state) => state.dashboard);
  const isLoading = useAppStore((state) => state.isLoading);
  const error = useAppStore((state) => state.error);
  const isAuthenticated = useAppStore((state) => state.isAuthenticated);
  const setDashboard = useAppStore((state) => state.setDashboard);
  const setLoading = useAppStore((state) => state.setLoading);
  const setError = useAppStore((state) => state.setError);

  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getDashboard();
      setDashboard(data);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to fetch dashboard";
      setError(errorMessage);
      console.error("[useDashboard] Error:", err);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, setDashboard, setLoading, setError]);

  // Initial fetch and setup auto-refresh on mount
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    // Fetch immediately
    refresh();

    // Setup auto-refresh interval
    refreshIntervalRef.current = setInterval(() => {
      refresh();
    }, REFRESH_INTERVAL);

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
    };
  }, [isAuthenticated, refresh]);

  return {
    dashboard,
    isLoading,
    error,
    refresh,
  };
}
