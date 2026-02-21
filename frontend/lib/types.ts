/**
 * TypeScript interfaces for JSR Hydra Trading System
 */

// Authentication
export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// Account Information — matches backend MT5 account data
export interface AccountInfo {
  login?: number | null;
  server?: string | null;
  balance: number;
  equity: number;
  margin?: number;
  free_margin?: number;
  margin_level: number;
  profit?: number;
  currency?: string;
  leverage?: number;
  peak_equity?: number;
  drawdown_pct: number;
  daily_pnl?: number;
}

// Account data alias used in DashboardSummary
export type AccountData = AccountInfo;

// Trade Related
export interface TradeResponse {
  id: string;
  master_id: string;
  strategy_id: string | null;
  idempotency_key: string | null;
  mt5_ticket: number | null;
  symbol: string;
  direction: string;
  lots: number;
  entry_price: number;
  exit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  profit: number;
  commission: number;
  swap: number;
  net_profit: number;
  regime_at_entry: string | null;
  confidence: number | null;
  reason: string | null;
  status: string;
  is_simulated: boolean;
  opened_at: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TradeCreate {
  symbol: string;
  direction: "BUY" | "SELL";
  lots: number;
  entry_price: number;
  stop_loss?: number;
  take_profit?: number;
  reason?: string;
  strategy_code: string;
}

export interface TradeUpdate {
  exit_price?: number;
  status?: "OPEN" | "CLOSED";
}

export interface TradeList {
  trades: TradeResponse[];
  total: number;
  page: number;
  per_page: number;
}

export interface TradeStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_win?: number;
  avg_loss?: number;
  profit_factor: number;
  total_profit: number;
  avg_profit: number;
  max_drawdown: number;
  sharpe_ratio: number;
  best_trade: number;
  worst_trade: number;
}

// Trade data shape returned in dashboard recent_trades list
export interface TradeData {
  id: string;
  symbol: string;
  direction: string;
  lots: number;
  entry_price: number;
  exit_price: number | null;
  profit: number;
  net_profit: number;
  status: string;
  opened_at: string | null;
  closed_at: string | null;
}

// Strategy Related — matches backend StrategyResponse schema
export interface StrategyResponse {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  // Backend stores status as uppercase strings (e.g. "PAUSED", "RUNNING")
  // Frontend normalizes to lowercase for display
  status: string;
  allocation_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  total_profit: number;
  config: Record<string, unknown>;
  auto_allocation?: boolean;
  created_at?: string;
  updated_at?: string;
  // Optional gamification fields (returned by /api/brain endpoints)
  xp_level?: number;
  xp_points?: number;
  badge?: string;
  fitness_score?: number;
}

export interface StrategyUpdate {
  status?: string;
  allocation_pct?: number;
  config?: Record<string, unknown>;
}

// Strategy data shape returned in dashboard strategies list
export interface StrategyData {
  code: string;
  name: string;
  status: string;
  allocation_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  total_profit: number;
}

// Market Regime — matches backend regime_data shape from dashboard
export interface RegimeData {
  state: string;
  confidence: number;
  conviction: number;
  lastDetected: string | null;
}

// Legacy RegimeResponse (kept for backward compat with existing components)
export interface RegimeResponse {
  regime: string;
  confidence: number;
  conviction_score: number;
}

// Allocation
export interface AllocationResponse {
  strategy_code: string;
  allocation_pct: number;
  current_exposure: number;
  max_exposure: number;
}

export interface AllocationUpdate {
  strategy_code: string;
  allocation_pct: number;
}

// Dashboard Summary — matches the actual backend /api/system/dashboard response
export interface DashboardSummary {
  account: AccountData | null;
  positions: any[];
  floating_profit?: number;
  open_positions?: number;
  open_positions_mt5?: number;
  open_trades_db?: number;
  open_positions_source?: "mt5" | "db" | "none" | "hybrid" | "mt5+db";
  open_count_source?: "mt5" | "db" | "mt5+db";
  strategies: StrategyData[];
  recent_trades: TradeData[];
  regime: RegimeData | null;
  symbols: string[];
  system_status: string;
  version: string;
  dry_run: boolean;
  uptime_seconds: number;
  equity_curve?: any;
  error?: string;
}

// Health Check — matches the actual backend /api/system/health response
export interface HealthCheck {
  status: string;
  version: string;
  codename: string;
  uptime_seconds: number;
  services: Record<string, { status: string; error?: string; account?: number; broker?: string; balance?: number }>;
  trading: {
    dry_run: boolean;
    system_status: string;
    open_positions: number;
    open_positions_mt5?: number;
    open_trades_db?: number;
    open_positions_source?: "mt5" | "db" | "mt5+db";
  };
}

// Live Updates via WebSocket
export type LiveUpdateEventType =
  | "TRADE_OPENED"
  | "TRADE_CLOSED"
  | "PRICE_UPDATE"
  | "REGIME_CHANGE"
  | "REGIME_CHANGED"
  | "ALLOCATION_CHANGE"
  | "ALLOCATION_CHANGED"
  | "STRATEGY_UPDATE"
  | "ACCOUNT_UPDATE"
  | "KILL_SWITCH_TRIGGERED"
  | "DAILY_LIMIT_HIT"
  | "HEARTBEAT";

export interface LiveUpdate {
  event_type: LiveUpdateEventType;
  data: Record<string, unknown>;
  timestamp: string;
}

// WebSocket Messages
export interface WsMessage {
  type: string;
  payload?: Record<string, unknown>;
}
