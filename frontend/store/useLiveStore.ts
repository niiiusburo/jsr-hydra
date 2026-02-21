/**
 * Live Updates Store
 * Manages WebSocket connection status and real-time data
 */

import { create } from "zustand";
import { LiveUpdate } from "../lib/types";
import { WsStatus } from "../lib/ws";

interface LiveState {
  // Connection status
  wsStatus: WsStatus;

  // Real-time data
  lastEvent: LiveUpdate | null;
  events: LiveUpdate[];

  // Account updates
  equity: number | null;
  balance: number | null;

  // Actions
  setWsStatus: (status: WsStatus) => void;
  addEvent: (event: LiveUpdate) => void;
  clearEvents: () => void;
  updateEquity: (value: number) => void;
  updateBalance: (value: number) => void;
  reset: () => void;
}

const MAX_EVENTS = 50;

export const useLiveStore = create<LiveState>((set) => ({
  // Initial state
  wsStatus: "disconnected",
  lastEvent: null,
  events: [],
  equity: null,
  balance: null,

  // Actions
  setWsStatus: (status: WsStatus) =>
    set({
      wsStatus: status,
    }),

  addEvent: (event: LiveUpdate) =>
    set((state) => {
      // Keep only last MAX_EVENTS
      const newEvents = [event, ...state.events].slice(0, MAX_EVENTS);

      // Update equity/balance if present in event data
      let equity = state.equity;
      let balance = state.balance;

      if (
        event.event_type === "ACCOUNT_UPDATE" &&
        typeof event.data === "object" &&
        event.data !== null
      ) {
        const data = event.data as Record<string, unknown>;
        if (typeof data.equity === "number") equity = data.equity;
        if (typeof data.balance === "number") balance = data.balance;
      }

      return {
        lastEvent: event,
        events: newEvents,
        equity,
        balance,
      };
    }),

  clearEvents: () =>
    set({
      events: [],
      lastEvent: null,
    }),

  updateEquity: (value: number) =>
    set({
      equity: value,
    }),

  updateBalance: (value: number) =>
    set({
      balance: value,
    }),

  reset: () =>
    set({
      wsStatus: "disconnected",
      lastEvent: null,
      events: [],
      equity: null,
      balance: null,
    }),
}));
