/**
 * Main Application Store
 * Manages dashboard data, trades, strategies, regime, and authentication
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  DashboardSummary,
  TradeList,
  StrategyResponse,
  RegimeResponse,
} from "../lib/types";

interface AppState {
  // Data
  dashboard: DashboardSummary | null;
  trades: TradeList | null;
  strategies: StrategyResponse[];
  regime: RegimeResponse | null;

  // UI State
  isLoading: boolean;
  error: string | null;

  // Authentication
  token: string | null;
  isAuthenticated: boolean;

  // Actions
  setDashboard: (data: DashboardSummary) => void;
  setTrades: (data: TradeList) => void;
  setStrategies: (data: StrategyResponse[]) => void;
  setRegime: (data: RegimeResponse) => void;
  setToken: (token: string) => void;
  clearToken: () => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Initial state
      dashboard: null,
      trades: null,
      strategies: [],
      regime: null,
      isLoading: false,
      error: null,
      token: null,
      isAuthenticated: false,

      // Actions
      setDashboard: (data: DashboardSummary) =>
        set({
          dashboard: data,
          error: null,
        }),

      setTrades: (data: TradeList) =>
        set({
          trades: data,
          error: null,
        }),

      setStrategies: (data: StrategyResponse[]) =>
        set({
          strategies: data,
          error: null,
        }),

      setRegime: (data: RegimeResponse) =>
        set({
          regime: data,
          error: null,
        }),

      setToken: (token: string) =>
        set({
          token,
          isAuthenticated: true,
          error: null,
        }),

      clearToken: () =>
        set({
          token: null,
          isAuthenticated: false,
          dashboard: null,
          trades: null,
          strategies: [],
          regime: null,
        }),

      setLoading: (isLoading: boolean) =>
        set({ isLoading }),

      setError: (error: string | null) =>
        set({ error }),

      reset: () =>
        set({
          dashboard: null,
          trades: null,
          strategies: [],
          regime: null,
          isLoading: false,
          error: null,
          token: null,
          isAuthenticated: false,
        }),
    }),
    {
      name: "app-store",
      partialize: (state) => ({
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
