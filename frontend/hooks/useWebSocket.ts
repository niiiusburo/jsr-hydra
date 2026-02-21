/**
 * WebSocket Connection Hook
 * Manages WebSocket lifecycle and real-time updates
 */

import { useEffect, useCallback, useRef } from "react";
import {
  WebSocketClient,
  createWebSocketClient,
  closeWebSocketClient,
} from "../lib/ws";
import { useLiveStore } from "../store/useLiveStore";
import { useAppStore } from "../store/useAppStore";
import { LiveUpdate } from "../lib/types";
// Derive the WebSocket base URL from the browser's current origin,
// converting http(s) to ws(s). This ensures it goes through Caddy.
function getWsBaseUrl(): string {
  if (typeof window === "undefined") return "ws://localhost:8000";
  return window.location.origin.replace(/^http/, "ws");
}

interface UseWebSocketResult {
  status: "connecting" | "connected" | "disconnected";
  lastEvent: LiveUpdate | null;
  events: LiveUpdate[];
}

/**
 * Custom hook for WebSocket connection management
 */
export function useWebSocket(): UseWebSocketResult {
  const wsStatus = useLiveStore((state) => state.wsStatus);
  const lastEvent = useLiveStore((state) => state.lastEvent);
  const events = useLiveStore((state) => state.events);
  const isAuthenticated = useAppStore((state) => state.isAuthenticated);
  const setWsStatus = useLiveStore((state) => state.setWsStatus);
  const addEvent = useLiveStore((state) => state.addEvent);

  const wsRef = useRef<WebSocketClient | null>(null);
  const messageCallbackRef = useRef<((event: LiveUpdate) => void) | null>(null);
  const statusCallbackRef = useRef<
    ((status: "connecting" | "connected" | "disconnected") => void) | null
  >(null);

  // Initialize WebSocket connection
  useEffect(() => {
    if (!isAuthenticated) {
      // Disconnect if not authenticated
      if (wsRef.current) {
        wsRef.current.disconnect();
        wsRef.current = null;
      }
      setWsStatus("disconnected");
      return;
    }

    // Construct WebSocket URL
    // /ws/* is routed to jsr-backend:8000 by Caddy (not under /api)
    const wsUrl = `${getWsBaseUrl()}/ws/live`;

    // Create or reuse WebSocket client
    if (!wsRef.current) {
      wsRef.current = createWebSocketClient({
        url: wsUrl,
        heartbeatInterval: 30000, // 30 seconds
        maxReconnectAttempts: 10,
        baseReconnectDelay: 1000,
        maxReconnectDelay: 30000,
      });
    }

    // Register message callback
    messageCallbackRef.current = (event: LiveUpdate) => {
      addEvent(event);
    };

    // Register status callback
    statusCallbackRef.current = (status) => {
      setWsStatus(status);
    };

    wsRef.current.onMessage(messageCallbackRef.current);
    wsRef.current.onStatus(statusCallbackRef.current);

    // Connect to WebSocket
    wsRef.current.connect();

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        if (messageCallbackRef.current) {
          wsRef.current.offMessage(messageCallbackRef.current);
        }
        if (statusCallbackRef.current) {
          wsRef.current.offStatus(statusCallbackRef.current);
        }
        // Don't close the connection here as it might be reused
        // just remove callbacks
      }
    };
  }, [isAuthenticated, setWsStatus, addEvent]);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      // Optionally close WebSocket when hook unmounts
      // Uncomment if you want to fully disconnect
      // closeWebSocketClient();
    };
  }, []);

  return {
    status: wsStatus,
    lastEvent,
    events,
  };
}

/**
 * Helper function to get WebSocket client instance
 * for sending messages directly
 */
export function useWebSocketClient(): WebSocketClient | null {
  const wsRef = useRef<WebSocketClient | null>(null);
  const isAuthenticated = useAppStore((state) => state.isAuthenticated);

  useEffect(() => {
    if (isAuthenticated) {
      const wsUrl = `${getWsBaseUrl()}/ws/live`;
      if (!wsRef.current) {
        wsRef.current = createWebSocketClient({
          url: wsUrl,
          heartbeatInterval: 30000,
          maxReconnectAttempts: 10,
          baseReconnectDelay: 1000,
          maxReconnectDelay: 30000,
        });
        wsRef.current.connect();
      }
    }

    return () => {
      // Keep the connection alive, don't close on unmount
    };
  }, [isAuthenticated]);

  return wsRef.current;
}
