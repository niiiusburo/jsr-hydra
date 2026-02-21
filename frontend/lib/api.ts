/**
 * API Client for JSR Hydra Trading System
 * Handles HTTP communication with backend
 */

import {
  LoginRequest,
  TokenResponse,
  DashboardSummary,
  TradeList,
  TradeResponse,
  StrategyResponse,
  StrategyUpdate,
  HealthCheck,
} from "./types";

// Use relative URLs so requests go through Caddy reverse proxy (same origin).
// NEXT_PUBLIC_API_URL gets baked at build time and defaults to localhost:8000
// which breaks when the browser is on a different machine than the server.
const BASE_URL = "";

/**
 * Helper function to fetch from API with auth header
 */
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;

  // Get token from localStorage if available
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("auth_token")
      : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    // Handle 401 Unauthorized
    if (response.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("auth_token");
        // Clear Zustand persisted auth state so it doesn't restore stale isAuthenticated
        localStorage.removeItem("app-store");
        window.location.href = "/login";
      }
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API Error: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Authentication APIs
 */
export async function login(
  username: string,
  password: string
): Promise<TokenResponse> {
  return fetchApi<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/**
 * Dashboard APIs
 */
export async function getDashboard(): Promise<DashboardSummary> {
  return fetchApi<DashboardSummary>("/api/system/dashboard");
}

/**
 * Health Check API (public, no auth required)
 */
export async function getHealth(): Promise<HealthCheck> {
  return fetchApi<HealthCheck>("/api/system/health");
}

/**
 * Trade APIs
 */
export interface TradeFilters {
  status?: string;
  symbol?: string;
  strategy_code?: string;
  page?: number;
  per_page?: number;
  days_ago?: number;
}

export async function getTrades(filters: TradeFilters = {}): Promise<TradeList> {
  const params = new URLSearchParams();

  if (filters.status) params.append("status_filter", filters.status);
  if (filters.symbol) params.append("symbol_filter", filters.symbol);
  if (filters.strategy_code) params.append("strategy_filter", filters.strategy_code);
  if (filters.page) params.append("page", filters.page.toString());
  if (filters.per_page) params.append("per_page", filters.per_page.toString());
  if (filters.days_ago !== undefined) params.append("days_ago", filters.days_ago.toString());

  const query = params.toString();
  const endpoint = `/api/trades${query ? `?${query}` : ""}`;

  return fetchApi<TradeList>(endpoint);
}

export async function getTrade(tradeId: string): Promise<TradeResponse> {
  return fetchApi<TradeResponse>(`/api/trades/${tradeId}`);
}

/**
 * Strategy APIs
 */
export async function getStrategies(): Promise<StrategyResponse[]> {
  return fetchApi<StrategyResponse[]>("/api/strategies");
}

export async function getStrategy(code: string): Promise<StrategyResponse> {
  return fetchApi<StrategyResponse>(`/api/strategies/${code}`);
}

export async function updateStrategy(
  code: string,
  data: StrategyUpdate
): Promise<StrategyResponse> {
  return fetchApi<StrategyResponse>(`/api/strategies/${code}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

/**
 * Kill Switch APIs
 */
export async function triggerKillSwitch(): Promise<void> {
  return fetchApi<void>("/api/system/kill-switch", {
    method: "POST",
  });
}

export async function resetKillSwitch(): Promise<void> {
  return fetchApi<void>("/api/system/kill-switch/reset", {
    method: "POST",
  });
}

/**
 * Positions API
 */
export async function getPositions(): Promise<any[]> {
  return fetchApi<any[]>("/api/system/positions");
}

/**
 * Live Tick API
 */
export async function getTick(symbol: string): Promise<any> {
  return fetchApi<any>(`/api/system/tick/${symbol}`);
}

/**
 * Trading Symbols Settings
 */
export interface TradingSymbolsConfig {
  active_symbols: string[]
  available_symbols: string[]
  symbol_configs: Record<string, { lot_size: number; sl_atr_mult: number; tp_atr_mult: number }>
}

export async function getTradingSymbols(): Promise<TradingSymbolsConfig> {
  return fetchApi<TradingSymbolsConfig>("/api/settings/trading-symbols")
}

export async function updateTradingSymbols(activeSymbols: string[]): Promise<TradingSymbolsConfig> {
  return fetchApi<TradingSymbolsConfig>("/api/settings/trading-symbols", {
    method: "PATCH",
    body: JSON.stringify({ active_symbols: activeSymbols }),
  })
}

/**
 * LLM Configuration
 */
export interface LLMProviderInfo {
  provider: string
  configured: boolean
  default_model: string
  base_url: string
}

export interface LLMConfig {
  enabled: boolean
  provider: string
  model: string
  last_error: string | null
  providers: LLMProviderInfo[]
  models: Record<string, string[]>
}

export async function getLLMConfig(): Promise<LLMConfig> {
  return fetchApi<LLMConfig>("/api/brain/llm-config")
}

export async function updateLLMConfig(provider: string, model?: string, apiKey?: string): Promise<LLMConfig> {
  const payload: Record<string, string | undefined> = { provider, model }
  if (apiKey) payload.api_key = apiKey
  return fetchApi<LLMConfig>("/api/brain/llm-config", {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

// Runtime Settings
export interface RuntimeSettings {
  learning: {
    exploration_rate: number
    min_trades_for_adjustment: number
    max_trade_history: number
    streak_warning_threshold: number
    confidence_lookback: number
    learning_speed: string
    automation_level: string
  }
  allocator: {
    rebalance_interval: number
    max_change_per_rebalance: number
    min_allocation_pct: number
    max_allocation_pct: number
  }
  risk: {
    max_drawdown_pct: number
    daily_loss_limit_pct: number
    per_trade_risk_pct: number
    max_lots: number
  }
  patterns: {
    hour_filter_enabled: boolean
    dow_filter_enabled: boolean
    min_trades_for_pattern: number
  }
  exploration_decay: {
    exploration_decay_enabled: boolean
    exploration_decay_after_trades: number
    exploration_decay_target: number
  }
}

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  return fetchApi<RuntimeSettings>("/api/settings/runtime")
}

export async function updateRuntimeSettings(settings: Partial<any>): Promise<RuntimeSettings> {
  return fetchApi<RuntimeSettings>("/api/settings/runtime", {
    method: "PATCH",
    body: JSON.stringify(settings),
  })
}

export async function resetRuntimeSettings(): Promise<RuntimeSettings> {
  return fetchApi<RuntimeSettings>("/api/settings/runtime/reset", {
    method: "POST",
  })
}

export async function getHourPerformance(): Promise<any> {
  return fetchApi<any>("/api/brain/hour-performance")
}

export async function getDowPerformance(): Promise<any> {
  return fetchApi<any>("/api/brain/dow-performance")
}

/**
 * Chart Vision Analysis
 */
export async function analyzeChart(image: File, context?: string): Promise<any> {
  const formData = new FormData()
  formData.append("image", image)
  if (context) formData.append("context", context)

  const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null
  const headers: Record<string, string> = {}
  if (token) headers["Authorization"] = `Bearer ${token}`

  // Do NOT set Content-Type — the browser sets it automatically with the
  // correct multipart boundary when sending FormData.
  const response = await fetch("/api/chart-vision/analyze", {
    method: "POST",
    headers,
    body: formData,
  })

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("auth_token")
      localStorage.removeItem("app-store")
      window.location.href = "/login"
    }
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `API Error: ${response.statusText}`)
  }

  return response.json()
}

export async function getChartVisionHistory(): Promise<any[]> {
  const data = await fetchApi<{ history: any[]; count: number }>("/api/chart-vision/history")
  return data.history
}

/**
 * Strategy Builder APIs
 */
export async function parseStrategy(input: string, symbol?: string): Promise<any> {
  return fetchApi<any>("/api/strategy-builder/parse", {
    method: "POST",
    body: JSON.stringify({ input, symbol: symbol || "BTCUSD" }),
  })
}

export async function refineStrategy(strategyId: string, feedback: string): Promise<any> {
  return fetchApi<any>("/api/strategy-builder/refine", {
    method: "POST",
    body: JSON.stringify({ strategy_id: strategyId, feedback }),
  })
}

export async function getStrategyBuilderHistory(): Promise<any[]> {
  return fetchApi<{ strategies: any[]; count: number }>("/api/strategy-builder/history").then(
    (res) => res.strategies
  )
}

export async function deployStrategy(strategyId: string, deployAs?: string): Promise<any> {
  return fetchApi<any>("/api/strategy-builder/deploy", {
    method: "POST",
    body: JSON.stringify({ strategy_id: strategyId, deploy_as: deployAs }),
  })
}

export { BASE_URL };
