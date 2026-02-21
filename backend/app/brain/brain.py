"""
PURPOSE: The Brain module for JSR Hydra — maintains a rolling internal monologue of
market analysis, trading decisions, learnings, and planned next moves.

The Brain is a lightweight singleton that runs in-process with the engine. It processes
each cycle's data, generates human-readable "thoughts" like a seasoned trader's internal
monologue, and tracks per-strategy confidence with reasoning. Enhanced with RL-based
signal overrides and Thompson Sampling confidence adjustments via BrainLearner.

Thoughts are stored in memory (max 100, FIFO). No database persistence — this is
real-time cognitive state.

CALLED BY:
    - engine/engine.py (process_cycle, process_trade_result)
    - api/routes_brain.py (get_state, get_thoughts, etc.)
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple

try:
    import redis.asyncio as redis_async
    import redis as redis_sync
except ImportError:
    import redis as redis_sync
    redis_async = None

from app.brain.analyzer import (
    analyze_trend,
    analyze_momentum,
    analyze_volatility,
    interpret_regime,
    generate_next_moves,
    assess_strategy_fitness,
)
from app.brain.auto_allocator import AutoAllocator
from app.brain.learner import BrainLearner
from app.brain.llm_brain import LLMBrain
from app.brain.strategy_xp import StrategyXP
from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger("brain")

# Maximum number of thoughts to retain in memory
MAX_THOUGHTS = 100

# Minimum interval (seconds) between periodic summary thoughts
PERIODIC_SUMMARY_INTERVAL = 300  # 5 minutes

# Strategy names for human-readable output
STRATEGY_NAMES = {
    "A": "Trend Following",
    "B": "Mean Reversion",
    "C": "Session Breakout",
    "D": "Momentum Scalper",
    "E": "Range Scalper (Sideways)",
}

LLM_SUPPORTED_PROVIDERS = ("openai", "zai")

STRATEGY_CODES = tuple(STRATEGY_NAMES.keys())
POINTS_START = 100
POINTS_MIN = 0
POINTS_MAX = 200
POINT_BLOCK_THRESHOLD = 25
POINT_TRADE_MIN_FOR_BLOCK = 5
LOSS_DIAG_INTERVAL_SECONDS = 900

LLM_MODELS_BY_PROVIDER = {
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"],
    "zai": ["glm-5", "glm-4.6", "glm-4.5-air"],
}


class Brain:
    """
    PURPOSE: The cognitive core of JSR Hydra. Maintains a rolling log of thoughts,
    tracks market analysis, strategy confidence, and planned next moves.
    Integrates BrainLearner for RL-based signal overrides and confidence adjustments.

    Attributes:
        _thoughts: Deque of thought dicts (max 100, FIFO)
        _market_analysis: Current market read (trend, momentum, volatility, regime)
        _next_moves: List of what the Brain is watching for
        _strategy_scores: Per-strategy confidence scores with reasoning
        _last_regime: Previous regime for change detection
        _last_rsi_zone: Previous RSI zone for threshold crossing detection
        _last_adx_zone: Previous ADX zone for threshold crossing detection
        _last_periodic_thought: Timestamp of last periodic summary
        _cycle_count: Total cycles processed
        _trade_history: Recent trade outcomes for learning (max 50)
        _learner: BrainLearner instance for RL-based learning
    """

    REDIS_KEY = "jsr:brain:state"
    LLM_CONFIG_REDIS_KEY = "jsr:brain:llm:config"
    LLM_CONFIG_SYNC_INTERVAL = 5.0

    def __init__(self):
        """
        PURPOSE: Initialize Brain with empty state, Redis connection, and BrainLearner.

        CALLED BY: get_brain() singleton factory
        """
        self._thoughts: deque = deque(maxlen=MAX_THOUGHTS)
        self._market_analysis: Dict[str, Any] = {
            "trend": "No data yet.",
            "momentum": "No data yet.",
            "volatility": "No data yet.",
            "regime": "UNKNOWN",
            "regime_confidence": 0.0,
            "key_levels": {},
            "summary": "Brain is warming up. Waiting for first market data.",
            "symbol": None,
            "bid": None,
            "ask": None,
            "indicators": {},
            "symbols": {},
            "last_updated": None,
        }
        self._next_moves: List[Dict] = []
        self._strategy_scores: Dict[str, Dict] = {}
        self._strategy_scores_by_symbol: Dict[str, Dict[str, Dict]] = {}
        self._symbol_market_analysis: Dict[str, Dict[str, Any]] = {}
        self._strategy_points: Dict[str, Dict[str, int]] = defaultdict(dict)
        self._last_thought_price_by_symbol: Dict[str, float] = {}
        self._last_regime: Optional[str] = None
        self._last_regime_by_symbol: Dict[str, str] = {}
        self._last_rsi_zone: Optional[str] = None
        self._last_rsi_zone_by_symbol: Dict[str, str] = {}
        self._last_adx_zone: Optional[str] = None
        self._last_adx_zone_by_symbol: Dict[str, str] = {}
        self._last_periodic_thought: float = 0.0
        self._last_loss_diagnosis_time: float = 0.0
        self._cycle_count: int = 0
        self._trade_history: deque = deque(maxlen=50)

        # Initialize RL-enhanced learner
        self._learner = BrainLearner()

        # Initialize Pokemon-style XP system
        self._strategy_xp = StrategyXP()

        # Initialize auto-allocation engine
        self._auto_allocator = AutoAllocator()

        # Initialize LLM runtime state (actual provider/model is applied
        # after Redis connection to allow cross-process config sync).
        self._llm: Optional[LLMBrain] = None
        self._llm_provider: str = "none"
        self._llm_model: str = ""
        self._llm_last_error: Optional[str] = None
        self._runtime_api_keys: Dict[str, str] = {}  # provider -> api_key set via API
        self._last_llm_config_sync: float = 0.0

        # Pending parameter updates from LLM recommendations
        # Format: {strategy_code: {param_name: new_value}}
        self._pending_parameter_updates: Dict[str, Dict[str, Any]] = {}

        # Redis for cross-process state sharing (engine writes, API reads)
        # Using synchronous redis client; writes are wrapped in executor when called from async context
        self._redis: Optional[redis_sync.Redis] = None
        try:
            self._redis = redis_sync.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            self._redis.ping()
            logger.info("brain_redis_connected")
        except Exception as e:
            logger.warning("brain_redis_unavailable", error=str(e))
            self._redis = None

        # Initialize LLM config from Redis if present, otherwise settings.
        self._initialize_llm_from_runtime_config()

        logger.info("brain_initialized", rl_trades=self._learner._rl_total_trades)

    # ════════════════════════════════════════════════════════════════
    # Redis Cross-Process Sync
    # ════════════════════════════════════════════════════════════════

    def _sync_to_redis(self) -> None:
        """Write current brain state to Redis so the API process can read it.
        
        Uses run_in_executor when an event loop is running to avoid blocking
        the async engine loop with synchronous Redis I/O.
        """
        if not self._redis:
            return
        try:
            state = self.get_state()
            serialized = json.dumps(state, default=str)
            redis_client = self._redis
            redis_key = self.REDIS_KEY

            def _do_redis_set():
                redis_client.set(redis_key, serialized, ex=30)

            try:
                loop = asyncio.get_running_loop()
                # We are inside an async context — schedule the blocking call off the main thread
                asyncio.ensure_future(
                    loop.run_in_executor(None, _do_redis_set)
                )
            except RuntimeError:
                # No running event loop — call directly (e.g. tests or startup)
                _do_redis_set()
        except Exception as e:
            logger.debug("brain_redis_sync_failed", error=str(e))

    def load_from_redis(self) -> Optional[dict]:
        """Read brain state from Redis (used by API process when local brain has no data).
        
        Synchronous read — safe to call from sync contexts. For async callers,
        the try/except prevents event loop blocking on connection errors.
        """
        if not self._redis:
            return None
        try:
            raw = self._redis.get(self.REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.debug("brain_redis_load_failed", error=str(e))
        return None

    # ════════════════════════════════════════════════════════════════
    # LLM Runtime Configuration (cross-process via Redis)
    # ════════════════════════════════════════════════════════════════

    def _normalize_provider(self, provider: Optional[str]) -> str:
        """Normalize provider name and fall back to configured default."""
        normalized = (provider or "").strip().lower()
        if normalized in LLM_SUPPORTED_PROVIDERS:
            return normalized

        configured_default = (settings.BRAIN_LLM_PROVIDER or "openai").strip().lower()
        if configured_default in LLM_SUPPORTED_PROVIDERS:
            return configured_default
        return "openai"

    def _get_provider_api_key(self, provider: str) -> str:
        # Check runtime keys (set via API) first, then fall back to env vars
        runtime_key = getattr(self, "_runtime_api_keys", {}).get(provider, "")
        if runtime_key:
            return runtime_key
        if provider == "openai":
            return settings.OPENAI_API_KEY
        if provider == "zai":
            return settings.ZAI_API_KEY
        return ""

    def _get_provider_default_model(self, provider: str) -> str:
        if provider == "openai":
            return settings.OPENAI_MODEL or "gpt-4o-mini"
        if provider == "zai":
            return settings.ZAI_MODEL or "glm-4.6"
        return ""

    def _get_provider_base_url(self, provider: str) -> str:
        if provider == "openai":
            return settings.OPENAI_BASE_URL
        if provider == "zai":
            return settings.ZAI_BASE_URL
        return ""

    def _get_supported_models(self, provider: str) -> List[str]:
        """Return known model IDs for provider with env-configured default first."""
        candidates = [
            self._get_provider_default_model(provider),
            *LLM_MODELS_BY_PROVIDER.get(provider, []),
        ]
        seen: set[str] = set()
        models: List[str] = []
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                models.append(candidate)
        return models

    def _load_llm_config_from_redis(self) -> Optional[dict]:
        """Load shared LLM runtime config from Redis."""
        if not self._redis:
            return None
        try:
            raw = self._redis.get(self.LLM_CONFIG_REDIS_KEY)
            if not raw:
                return None
            payload = json.loads(raw)
            provider = self._normalize_provider(payload.get("provider"))
            model = str(payload.get("model") or "").strip()
            if not model:
                model = self._get_provider_default_model(provider)
            # Restore runtime API key if persisted
            api_key = payload.get("api_key")
            if api_key:
                self._runtime_api_keys[provider] = api_key
            return {
                "provider": provider,
                "model": model,
            }
        except Exception as e:
            logger.warning("brain_llm_config_load_failed", error=str(e))
            return None

    def _persist_llm_config_to_redis(self, provider: str, model: str, api_key: Optional[str] = None) -> None:
        """Persist shared LLM runtime config so API + engine stay in sync."""
        if not self._redis:
            return
        try:
            payload = {
                "provider": provider,
                "model": model,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if api_key:
                payload["api_key"] = api_key
            self._redis.set(self.LLM_CONFIG_REDIS_KEY, json.dumps(payload))
        except Exception as e:
            logger.warning("brain_llm_config_persist_failed", error=str(e))

    def _apply_llm_config(self, provider: str, model: Optional[str], source: str) -> None:
        """Apply provider/model config to the in-memory LLM client."""
        normalized_provider = self._normalize_provider(provider)
        selected_model = (model or "").strip() or self._get_provider_default_model(normalized_provider)

        api_key = self._get_provider_api_key(normalized_provider)
        if not api_key:
            self._llm = None
            self._llm_provider = normalized_provider
            self._llm_model = selected_model
            self._llm_last_error = f"{normalized_provider.upper()} API key is not configured"
            logger.info(
                "brain_llm_disabled",
                provider=normalized_provider,
                model=selected_model,
                reason=self._llm_last_error,
                source=source,
            )
            return

        base_url = self._get_provider_base_url(normalized_provider)
        self._llm = LLMBrain(
            api_key=api_key,
            model=selected_model,
            provider=normalized_provider,
            base_url=base_url,
        )
        self._llm_provider = normalized_provider
        self._llm_model = selected_model
        self._llm_last_error = None
        logger.info(
            "brain_llm_initialized",
            provider=normalized_provider,
            model=selected_model,
            source=source,
        )

    def _initialize_llm_from_runtime_config(self) -> None:
        """Initialize LLM client from Redis config first, else settings defaults."""
        redis_config = self._load_llm_config_from_redis()
        if redis_config:
            self._apply_llm_config(
                provider=redis_config["provider"],
                model=redis_config["model"],
                source="redis_bootstrap",
            )
            return

        configured_provider = self._normalize_provider(settings.BRAIN_LLM_PROVIDER)
        configured_model = self._get_provider_default_model(configured_provider)
        self._apply_llm_config(
            provider=configured_provider,
            model=configured_model,
            source="settings",
        )
        self._persist_llm_config_to_redis(
            provider=configured_provider,
            model=configured_model,
        )

    def _refresh_llm_config_from_redis(self, force: bool = False) -> None:
        """Pull latest shared LLM config from Redis and apply if changed."""
        if not self._redis:
            return
        now = time.time()
        if not force and (now - self._last_llm_config_sync) < self.LLM_CONFIG_SYNC_INTERVAL:
            return
        self._last_llm_config_sync = now

        redis_config = self._load_llm_config_from_redis()
        if not redis_config:
            return

        redis_provider = redis_config["provider"]
        redis_model = redis_config["model"]
        if redis_provider == self._llm_provider and redis_model == self._llm_model:
            return

        self._apply_llm_config(
            provider=redis_provider,
            model=redis_model,
            source="redis_sync",
        )

    def get_llm_config(self) -> dict:
        """Return current and available LLM runtime options for dashboard UI."""
        self._refresh_llm_config_from_redis(force=True)
        providers = []
        for provider in LLM_SUPPORTED_PROVIDERS:
            providers.append(
                {
                    "provider": provider,
                    "configured": bool(self._get_provider_api_key(provider)),
                    "default_model": self._get_provider_default_model(provider),
                    "base_url": self._get_provider_base_url(provider),
                }
            )

        return {
            "enabled": self._llm is not None,
            "provider": self._llm_provider,
            "model": self._llm_model,
            "last_error": self._llm_last_error,
            "providers": providers,
            "models": {
                provider: self._get_supported_models(provider)
                for provider in LLM_SUPPORTED_PROVIDERS
            },
        }

    def set_llm_config(self, provider: str, model: Optional[str] = None, api_key: Optional[str] = None) -> dict:
        """Update provider/model/api_key at runtime and persist for all processes."""
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider not in LLM_SUPPORTED_PROVIDERS:
            supported = ", ".join(LLM_SUPPORTED_PROVIDERS)
            raise ValueError(f"Unsupported provider '{provider}'. Supported providers: {supported}")

        # Store runtime API key if provided
        if api_key and api_key.strip():
            self._runtime_api_keys[normalized_provider] = api_key.strip()

        selected_model = (model or "").strip() or self._get_provider_default_model(normalized_provider)
        self._apply_llm_config(
            provider=normalized_provider,
            model=selected_model,
            source="api",
        )
        self._persist_llm_config_to_redis(
            provider=normalized_provider,
            model=selected_model,
            api_key=self._runtime_api_keys.get(normalized_provider),
        )
        return self.get_llm_config()

    # ════════════════════════════════════════════════════════════════
    # Core Processing
    # ════════════════════════════════════════════════════════════════

    def _normalize_cycle_risk_checks(self, raw_risk_checks: Any) -> List[Dict[str, Any]]:
        """Normalize risk checks into a list of dict payloads."""
        if isinstance(raw_risk_checks, dict):
            raw_risk_checks = [raw_risk_checks]
        if not isinstance(raw_risk_checks, list):
            return []
        return [rc for rc in raw_risk_checks if isinstance(rc, dict)]

    def _normalize_cycle_trades(self, raw_trades: Any) -> List[Dict[str, Any]]:
        """Normalize trades into a list of dict payloads."""
        if isinstance(raw_trades, dict):
            raw_trades = [raw_trades]
        if not isinstance(raw_trades, list):
            return []
        return [trade for trade in raw_trades if isinstance(trade, dict)]

    def _build_risk_checks_by_strategy(
        self,
        risk_checks: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Index risk checks by strategy key for quick lookup in decision stage."""
        indexed: Dict[str, Dict[str, Any]] = {}
        for rc in risk_checks:
            strat_key = rc.get("strategy")
            if strat_key:
                indexed[str(strat_key)] = rc
        return indexed

    def _process_symbol_payload(
        self,
        symbol_key: str,
        symbol_payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Process one symbol/pair snapshot for this cycle.

        Returns:
            (snapshot, regime_change)
              - snapshot: normalized market snapshot for this pair
              - regime_change: optional regime transition payload
        """
        if not isinstance(symbol_payload, dict):
            return None, None

        symbol = str(symbol_key or "UNKNOWN").upper()
        symbol_indicators = symbol_payload.get("indicators", {})
        if not isinstance(symbol_indicators, dict):
            symbol_indicators = {}

        symbol_regime = symbol_payload.get("regime")
        symbol_conf = symbol_payload.get("confidence")

        snapshot = self._update_market_analysis(
            indicators=symbol_indicators,
            regime=symbol_regime,
            confidence=symbol_conf,
            symbol=symbol,
            cycle_data=symbol_payload,
        )
        self._update_strategy_scores(symbol_regime, symbol_indicators, symbol=symbol)

        regime_change: Optional[Dict[str, Any]] = None
        old_symbol_regime = self._last_regime_by_symbol.get(symbol)
        if (
            symbol_regime is not None
            and old_symbol_regime is not None
            and symbol_regime != old_symbol_regime
        ):
            regime_change = {
                "symbol": symbol,
                "old": old_symbol_regime,
                "new": symbol_regime,
                "confidence": symbol_conf,
                "indicators": symbol_indicators,
            }
        if symbol_regime is not None:
            self._last_regime_by_symbol[symbol] = symbol_regime

        # Pair-level threshold events for clearer "why" in thought stream.
        self._check_rsi_crossing(symbol_indicators.get("rsi"), symbol=symbol)
        self._check_adx_crossing(symbol_indicators.get("adx"), symbol=symbol)

        return snapshot, regime_change

    def _build_next_moves_for_symbols(
        self,
        symbol_snapshots: Dict[str, Dict[str, Any]],
        signals: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build strategy next-move watchlist across all active pairs."""
        moves: List[Dict[str, Any]] = []
        for symbol_key, snapshot in symbol_snapshots.items():
            symbol_signals = {
                key: val
                for key, val in signals.items()
                if isinstance(key, str) and key.startswith(f"{symbol_key}_")
            }
            symbol_moves = generate_next_moves(
                snapshot.get("indicators", {}),
                snapshot.get("regime"),
                symbol_signals,
                symbol_key,
            )
            for move in symbol_moves:
                if isinstance(move, dict):
                    enriched_move = move.copy()
                    enriched_move.setdefault("symbol", symbol_key)
                    moves.append(enriched_move)
        return moves[:50]

    def _emit_new_candle_thoughts(
        self,
        symbol_snapshots: Dict[str, Dict[str, Any]],
        primary_symbol: str,
        fallback_new_candle: bool,
    ) -> None:
        """Emit pair-specific candle thoughts so each symbol has its own readable section."""
        emitted = False
        for symbol_key, snapshot in symbol_snapshots.items():
            if not bool(snapshot.get("new_candle", False)):
                continue
            self._generate_candle_thought(
                snapshot.get("indicators", {}),
                snapshot.get("regime"),
                snapshot.get("regime_confidence"),
                symbol_key,
                price=snapshot.get("bid"),
                spread=snapshot.get("spread"),
            )
            emitted = True

        # Safety fallback for legacy single-symbol payloads.
        if not emitted and fallback_new_candle:
            primary_snapshot = symbol_snapshots.get(primary_symbol)
            if primary_snapshot:
                self._generate_candle_thought(
                    primary_snapshot.get("indicators", {}),
                    primary_snapshot.get("regime"),
                    primary_snapshot.get("regime_confidence"),
                    primary_symbol,
                    price=primary_snapshot.get("bid"),
                    spread=primary_snapshot.get("spread"),
                )

    def _emit_regime_change_thoughts(
        self,
        regime_changes: List[Dict[str, Any]],
        primary_symbol: str,
    ) -> Optional[Dict[str, Any]]:
        """Emit regime-shift thoughts and return the primary pair change for LLM analysis."""
        llm_regime_change: Optional[Dict[str, Any]] = None
        for change in regime_changes:
            self._generate_regime_change_thought(
                change["old"],
                change["new"],
                change.get("confidence"),
                symbol=change["symbol"],
            )
            if change["symbol"] == primary_symbol:
                llm_regime_change = change
                # Notify learner of the regime transition so it can track
                # strategy performance in the 60-minute post-transition window.
                self._learner.notify_regime_change(change["old"], change["new"])
        return llm_regime_change

    def _build_market_data_for_llm(
        self,
        symbol_snapshots: Dict[str, Dict[str, Any]],
        primary_symbol: str,
        cycle_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build detailed multi-pair payload for LLM market analysis."""
        primary_snapshot = symbol_snapshots.get(primary_symbol, {})
        indicators = primary_snapshot.get("indicators", {})
        return {
            "symbols": list(symbol_snapshots.keys()) or cycle_data.get("symbols", [primary_symbol]),
            "symbol_data": {
                sym: {
                    "regime": snap.get("regime"),
                    "regime_confidence": snap.get("regime_confidence"),
                    "bid": snap.get("bid"),
                    "ask": snap.get("ask"),
                    "spread": snap.get("spread"),
                    "indicators": snap.get("indicators", {}),
                }
                for sym, snap in symbol_snapshots.items()
            } or {primary_symbol: indicators},
            "regime": primary_snapshot.get("regime"),
            "adx": indicators.get("adx"),
            "rsi": indicators.get("rsi"),
            "balance": cycle_data.get("account", {}).get("balance", 0),
            "open_positions": len(cycle_data.get("positions", [])),
            "daily_pnl": cycle_data.get("account", {}).get("daily_pnl", 0),
        }

    def _schedule_llm_analyses(
        self,
        market_data: Dict[str, Any],
        llm_regime_change: Optional[Dict[str, Any]],
    ) -> None:
        """Run LLM jobs sequentially to avoid rate limiting on providers with tight quotas."""
        if not self._llm:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    self._run_llm_pipeline(market_data, llm_regime_change)
                )
            else:
                loop.run_until_complete(self._llm_analyze_market(market_data))
        except Exception as e:
            self._set_llm_runtime_error(str(e), context="cycle_schedule")

    async def _run_llm_pipeline(
        self,
        market_data: Dict[str, Any],
        llm_regime_change: Optional[Dict[str, Any]],
    ) -> None:
        """Run all LLM jobs sequentially so they don't compete for rate limits."""
        if llm_regime_change:
            await self._llm_analyze_regime_change(
                llm_regime_change["old"],
                llm_regime_change["new"],
                llm_regime_change.get("indicators", {}),
            )
            await asyncio.sleep(3)

        await self._llm_analyze_market(market_data)
        await asyncio.sleep(3)
        await self._llm_hourly_strategy_review()

    def process_cycle(self, cycle_data: dict) -> None:
        """
        PURPOSE: Process a single engine cycle's data and generate thoughts if warranted.

        Called by the engine at the end of each 5-second cycle. Decides whether
        conditions merit generating a thought (not every cycle needs one).
        Now includes RL signal override checks for each signal.

        Args:
            cycle_data: Dict with keys: cycle, symbol, bid, ask, spread, indicators,
                       regime, confidence, new_candle, signals, risk_check, trade, account

        CALLED BY: engine/engine.py _main_loop
        """
        self._cycle_count += 1
        self._refresh_llm_config_from_redis()

        signals = cycle_data.get("signals", {}) or {}
        if not isinstance(signals, dict):
            signals = {}
        risk_checks = self._normalize_cycle_risk_checks(cycle_data.get("risk_checks", []))
        trades_this_cycle = self._normalize_cycle_trades(cycle_data.get("trades", []))

        symbols_data = cycle_data.get("symbols_data", {})
        symbol_snapshots: Dict[str, Dict[str, Any]] = {}
        regime_changes: List[Dict[str, Any]] = []
        primary_symbol = str(cycle_data.get("symbol", "XAUUSD")).upper()

        if isinstance(symbols_data, dict) and symbols_data:
            for raw_symbol_key, symbol_payload in symbols_data.items():
                symbol_key = str(raw_symbol_key or "UNKNOWN").upper()
                snapshot, regime_change = self._process_symbol_payload(symbol_key, symbol_payload)
                if snapshot is not None:
                    symbol_snapshots[symbol_key] = snapshot
                if regime_change is not None:
                    regime_changes.append(regime_change)
            if primary_symbol not in symbol_snapshots and symbol_snapshots:
                primary_symbol = next(iter(symbol_snapshots.keys()))
            if symbol_snapshots:
                self._set_primary_market_symbol(primary_symbol)
        else:
            fallback_payload = {
                "indicators": cycle_data.get("indicators", {}),
                "regime": cycle_data.get("regime"),
                "confidence": cycle_data.get("confidence"),
                "new_candle": cycle_data.get("new_candle", False),
                "bid": cycle_data.get("bid"),
                "ask": cycle_data.get("ask"),
                "spread": cycle_data.get("spread"),
            }
            snapshot, regime_change = self._process_symbol_payload(primary_symbol, fallback_payload)
            if snapshot is not None:
                symbol_snapshots[primary_symbol] = snapshot
            if regime_change is not None:
                regime_changes.append(regime_change)

        self._next_moves = self._build_next_moves_for_symbols(symbol_snapshots, signals)

        if not symbol_snapshots:
            self._sync_to_redis()
            return

        primary_snapshot = symbol_snapshots.get(primary_symbol)
        if primary_snapshot is None:
            primary_snapshot = next(iter(symbol_snapshots.values()))
            primary_symbol = str(primary_snapshot.get("symbol", primary_symbol)).upper()

        indicators = primary_snapshot.get("indicators", {})
        regime = primary_snapshot.get("regime")
        symbol = primary_symbol
        self._strategy_scores = self._strategy_scores_by_symbol.get(primary_symbol, {})
        risk_by_strategy = self._build_risk_checks_by_strategy(risk_checks)

        logger.debug(
            "brain_cycle_start",
            cycle=self._cycle_count,
            primary_symbol=primary_symbol,
            symbols=list(symbol_snapshots.keys()),
            signal_count=len(signals),
            risk_checks=len(risk_checks),
            trades=len(trades_this_cycle),
        )

        # ── 1. New candle thoughts (per pair) ──
        self._emit_new_candle_thoughts(
            symbol_snapshots=symbol_snapshots,
            primary_symbol=primary_symbol,
            fallback_new_candle=bool(cycle_data.get("new_candle", False)),
        )

        # ── 2. Signal decisions with RL + point guard ──
        for signal_key, sig in signals.items():
            if not (isinstance(sig, dict) and "direction" in sig):
                continue

            strategy_code, signal_symbol = self._parse_signal_key(signal_key, fallback_symbol=symbol)
            symbol_ctx = symbol_snapshots.get(signal_symbol, primary_snapshot)
            signal_indicators = symbol_ctx.get("indicators", indicators)
            signal_regime = symbol_ctx.get("regime", regime)

            if signal_regime:
                should_skip, reason = self._learner.should_override_signal(
                    strategy_code, signal_regime, signal_indicators
                )
                if should_skip:
                    self._add_thought(
                        "DECISION",
                        (
                            f"RL override: Skipping {STRATEGY_NAMES.get(strategy_code, strategy_code)} "
                            f"on {signal_symbol} -- {reason}"
                        ),
                        confidence=0.75,
                        metadata={
                            "trigger": "rl_override",
                            "strategy": strategy_code,
                            "symbol": signal_symbol,
                            "reason": reason,
                        },
                    )
                    continue

            if self._should_block_signal_by_points(signal_symbol, strategy_code):
                points = self._get_strategy_points(signal_symbol, strategy_code)
                self._add_thought(
                    "DECISION",
                    (
                        f"Point guard: Skipping {STRATEGY_NAMES.get(strategy_code, strategy_code)} "
                        f"on {signal_symbol}. Score {points}/{POINTS_MAX} is below safety threshold."
                    ),
                    confidence=0.72,
                    metadata={
                        "trigger": "point_guard",
                        "strategy": strategy_code,
                        "symbol": signal_symbol,
                        "points": points,
                    },
                )
                continue

            self._generate_signal_thought(
                strategy_code,
                sig,
                risk_by_strategy.get(str(signal_key)),
                symbol=signal_symbol,
            )

        # ── 3. Trade executed thoughts from this cycle ──
        for trade in trades_this_cycle:
            if isinstance(trade, dict):
                self._generate_trade_thought(
                    trade,
                    risk_by_strategy.get(str(trade.get("strategy"))),
                )

        # ── 4. Trade rejections ──
        for rc in risk_by_strategy.values():
            if not rc.get("approved", True):
                self._generate_rejection_thought(signals, rc)

        # ── 5. Regime change thoughts ──
        llm_regime_change = self._emit_regime_change_thoughts(
            regime_changes=regime_changes,
            primary_symbol=primary_symbol,
        )
        self._last_regime = regime

        # ── 6. Periodic summary ──
        now = time.time()
        if now - self._last_periodic_thought >= PERIODIC_SUMMARY_INTERVAL:
            self._generate_periodic_summary(
                indicators,
                regime,
                symbol,
                cycle_data,
                symbol_snapshots=symbol_snapshots,
            )
            self._last_periodic_thought = now

        # ── 7. LLM analyses (non-blocking) ──
        if self._llm:
            market_data = self._build_market_data_for_llm(
                symbol_snapshots=symbol_snapshots,
                primary_symbol=primary_symbol,
                cycle_data=cycle_data,
            )
            self._schedule_llm_analyses(
                market_data=market_data,
                llm_regime_change=llm_regime_change,
            )

        # Sync state to Redis for cross-process access
        logger.debug(
            "brain_cycle_complete",
            cycle=self._cycle_count,
            primary_symbol=primary_symbol,
            regime=regime,
            thought_count=len(self._thoughts),
            next_moves=len(self._next_moves),
        )
        self._sync_to_redis()

    def process_trade_result(self, trade_data: dict) -> None:
        """
        PURPOSE: Process trade events and learn from closed trades.

        Args:
            trade_data: Dict with keys: strategy, symbol, direction, lots, entry_price,
                       exit_price, profit, net_profit, duration_seconds, regime_at_entry

        CALLED BY: engine/engine.py (when trade closes), event handlers
        """
        self._refresh_llm_config_from_redis()

        strategy_code = str(trade_data.get("strategy", "?")).split("_")[-1].upper()
        strategy_name = STRATEGY_NAMES.get(strategy_code, f"Strategy {strategy_code}")
        direction = trade_data.get("direction", "?")
        symbol = str(trade_data.get("symbol", "?"))
        entry = trade_data.get("entry_price")
        exit_price = trade_data.get("exit_price")
        regime = trade_data.get("regime_at_entry", "unknown")
        session = trade_data.get("session", "UNKNOWN")

        # Guard: engine may notify trade opens through this method.
        # Do not poison RL with pseudo-results before a trade is closed.
        if not self._is_closed_trade_payload(trade_data):
            self._add_thought(
                "DECISION",
                (
                    f"Trade opened: {strategy_name} ({strategy_code}) {direction} {symbol} "
                    f"at {entry}. Awaiting closed result before RL update."
                ),
                confidence=0.62,
                metadata={
                    "trigger": "trade_opened",
                    "strategy": strategy_code,
                    "symbol": symbol,
                    "ticket": trade_data.get("ticket"),
                },
            )
            return

        profit = trade_data.get("profit", 0)
        net_profit = trade_data.get("net_profit", profit)
        closed_trade = dict(trade_data)
        closed_trade["strategy"] = strategy_code
        closed_trade["symbol"] = symbol
        closed_trade["net_profit"] = net_profit
        self._trade_history.append(closed_trade)

        # Determine outcome
        if net_profit > 0:
            outcome = "WIN"
            emoji_word = "Profitable"
        elif net_profit < 0:
            outcome = "LOSS"
            emoji_word = "Stopped out"
        else:
            outcome = "BREAKEVEN"
            emoji_word = "Breakeven"

        # ── Feed trade to RL learner ──
        # Prepare trade_data with fields the learner expects
        learner_trade = {
            "strategy": strategy_code,
            "direction": direction,
            "entry_price": entry,
            "exit_price": exit_price,
            "profit": net_profit,
            "won": net_profit > 0,
            "sl_distance": trade_data.get("sl_distance", 1.0),
            "duration_seconds": trade_data.get("duration_seconds", 3600),
            "ticket": trade_data.get("ticket"),
            "lots": trade_data.get("lots"),
        }

        # Get current indicators from market analysis for context
        current_indicators = self._market_analysis.get("indicators", {})

        # Analyze trade with learner (updates Thompson Sampling + stats)
        learner_result = self._learner.analyze_trade(
            learner_trade, regime, session, current_indicators
        )

        # Calculate RL reward for the thought
        rl_reward = self._learner.calculate_reward(learner_trade)

        # Learner already updates Thompson Sampling internally in analyze_trade().
        preset = learner_result.get("preset", "moderate")

        # Get updated confidence for this strategy
        confidence_adjustments = self._learner.get_strategy_confidence_adjustments()
        strat_adj = confidence_adjustments.get(strategy_code, {})
        new_confidence = strat_adj.get("adjustment", 0.0)

        points_before = self._get_strategy_points(symbol, strategy_code)
        points_after, points_delta = self._update_strategy_points(
            symbol=symbol,
            strategy_code=strategy_code,
            net_profit=net_profit,
            rl_reward=rl_reward,
            duration_seconds=trade_data.get("duration_seconds", 3600),
        )

        # Build learning thought with RL insight
        content = (
            f"{emoji_word} on {strategy_name} ({strategy_code}) {direction} {symbol}. "
            f"Entry {entry}, exit {exit_price}, P&L: {net_profit:+.2f}. "
            f"Regime at entry: {regime}."
        )

        # Add RL learning insight
        content += (
            f" Trade closed: {net_profit:+.2f}. RL reward: {rl_reward:+.4f}. "
            f"{strategy_name} confidence in {regime}: {new_confidence:+.3f}."
        )
        content += (
            f" Points: {points_before} -> {points_after} ({points_delta:+d})."
        )

        # Analyze patterns from recent trade history for this strategy
        recent_for_strategy = [
            t for t in self._trade_history
            if t.get("strategy") == strategy_code
        ]
        if len(recent_for_strategy) >= 3:
            recent_outcomes = [
                "win" if t.get("net_profit", 0) > 0 else "loss"
                for t in list(recent_for_strategy)[-3:]
            ]
            if all(o == "loss" for o in recent_outcomes):
                content += (
                    f" Last 3 trades on {strategy_name} all stopped out. "
                    f"Reducing confidence -- conditions may not suit this strategy."
                )
                # Adjust strategy score downward
                if strategy_code in self._strategy_scores:
                    current = self._strategy_scores[strategy_code].get("confidence", 0.5)
                    self._strategy_scores[strategy_code]["confidence"] = max(0.1, current - 0.15)
                    self._strategy_scores[strategy_code]["reason"] += " (Penalized: 3 consecutive losses.)"
            elif all(o == "win" for o in recent_outcomes):
                content += (
                    f" {strategy_name} on a 3-win streak. Conditions are favorable -- maintaining confidence."
                )

        self._add_thought("LEARNING", content, confidence=0.7, metadata={
            "strategy": strategy_code,
            "outcome": outcome,
            "profit": net_profit,
            "regime": regime,
            "rl_reward": rl_reward,
            "rl_preset": preset,
            "rl_confidence_adjustment": new_confidence,
            "points_before": points_before,
            "points_after": points_after,
            "points_delta": points_delta,
        })

        # ── Award XP (Pokemon-style leveling) ──
        xp_trade_result = {
            "won": net_profit > 0,
            "profit": net_profit,
            "sl_distance": trade_data.get("sl_distance", 1.0),
            "duration_seconds": trade_data.get("duration_seconds", 3600),
            "symbol": symbol,
            "regime": regime,
            "has_sl": trade_data.get("sl_distance", 0) > 0,
        }
        xp_result = self._strategy_xp.award_xp(strategy_code, xp_trade_result)

        if xp_result.get("level_up"):
            self._add_thought(
                "LEARNING",
                xp_result["notification"],
                confidence=0.9,
                metadata={
                    "trigger": "level_up",
                    "strategy": strategy_code,
                    "new_level": xp_result["new_level"],
                    "old_level": xp_result["old_level"],
                    "xp_earned": xp_result["xp_earned"],
                },
            )

        # Log new badges
        for badge in xp_result.get("new_badges", []):
            self._add_thought(
                "LEARNING",
                f"Badge earned! Strategy {strategy_code} unlocked '{badge['name']}': {badge['description']}.",
                confidence=0.8,
                metadata={
                    "trigger": "badge_earned",
                    "strategy": strategy_code,
                    "badge": badge["id"],
                },
            )

        # ── Auto-Allocation Rebalance Check ──
        try:
            xp_all = self._strategy_xp.get_all_xp()
            learner_adj = self._learner.get_strategy_confidence_adjustments()
            rl_stats_data = self._learner.get_rl_stats()

            # Get current allocations from the auto-allocator's last known state
            # or default to equal distribution
            current_allocs = self._auto_allocator._last_allocations or {
                c: 25.0 for c in ("A", "B", "C", "D")
            }

            rebalance_result = self._auto_allocator.on_trade_completed(
                xp_all, learner_adj, rl_stats_data, current_allocs
            )

            if rebalance_result:
                changes = rebalance_result["changes"]
                change_parts = []
                for c, ch in changes.items():
                    if ch["delta"] != 0:
                        arrow = "+" if ch["delta"] > 0 else ""
                        change_parts.append(f"{c}: {ch['from']}% -> {ch['to']}% ({arrow}{ch['delta']}%)")

                if change_parts:
                    self._add_thought(
                        "DECISION",
                        f"Auto-rebalance #{rebalance_result['rebalance_number']}: "
                        f"Adjusting allocations based on performance. "
                        + ", ".join(change_parts),
                        confidence=0.85,
                        metadata={
                            "trigger": "auto_rebalance",
                            "allocations": rebalance_result["allocations"],
                            "fitness_scores": {
                                c: d["score"]
                                for c, d in rebalance_result["fitness_scores"].items()
                            },
                        },
                    )

                # Write new allocations to the database
                allocations = rebalance_result.get("allocations", {})
                if allocations and self._auto_allocator._enabled:
                    try:
                        import asyncio as _asyncio
                        from app.db.engine import AsyncSessionLocal
                        from app.models.strategy import Strategy
                        from sqlalchemy import update

                        async def _apply_allocations_to_db():
                            async with AsyncSessionLocal() as session:
                                for strategy_code, alloc_pct in allocations.items():
                                    await session.execute(
                                        update(Strategy)
                                        .where(Strategy.code == strategy_code)
                                        .values(allocation_pct=alloc_pct)
                                    )
                                await session.commit()
                            logger.info("auto_allocation_applied_to_db", allocations=allocations)

                        loop = _asyncio.get_event_loop()
                        if loop.is_running():
                            _asyncio.ensure_future(_apply_allocations_to_db())
                        else:
                            loop.run_until_complete(_apply_allocations_to_db())
                    except Exception as db_err:
                        logger.warning("auto_allocation_db_write_failed", error=str(db_err))
        except Exception as e:
            logger.debug("auto_allocator_error", error=str(e))

        # ── Automated loss diagnostics (point system + AI trigger) ──
        loss_snapshot = self._build_loss_diagnostics_snapshot()
        if self._is_losing_cluster(loss_snapshot):
            summary = self._format_loss_summary(loss_snapshot)
            self._add_thought(
                "LEARNING",
                summary,
                confidence=0.78,
                metadata={
                    "trigger": "loss_diagnostics",
                    "snapshot": loss_snapshot,
                },
            )

            now = time.time()
            if self._llm and (now - self._last_loss_diagnosis_time) >= LOSS_DIAG_INTERVAL_SECONDS:
                self._last_loss_diagnosis_time = now
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(self._llm_diagnose_losses(loss_snapshot))
                except Exception:
                    pass  # Do not break trade processing on LLM failures

        # ── LLM Trade Review (non-blocking) ──
        if self._llm:
            llm_trade_data = {
                "symbol": symbol,
                "direction": direction,
                "strategy": strategy_name,
                "entry_price": entry,
                "exit_price": exit_price,
                "profit": net_profit,
                "duration_minutes": round(trade_data.get("duration_seconds", 0) / 60, 1),
                "sl_price": trade_data.get("sl_price"),
                "tp_price": trade_data.get("tp_price"),
                "rsi_at_entry": current_indicators.get("rsi"),
                "regime": regime,
            }
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._llm_review_trade(llm_trade_data))
            except Exception:
                pass  # Don't let LLM errors break the engine

        # Keep API process in sync immediately after trade learning updates
        self._sync_to_redis()

    # ════════════════════════════════════════════════════════════════
    # State Accessors
    # ════════════════════════════════════════════════════════════════

    def get_state(self) -> dict:
        """
        PURPOSE: Return full brain state for API consumption.
        Falls back to Redis if local brain has no data (API process).
        Now includes RL stats for dashboard display.

        Returns:
            dict: Complete brain state with thoughts, analysis, next_moves, strategy_scores, rl_stats

        CALLED BY: api/routes_brain.py
        """
        # If this brain has processed cycles, return local state
        if self._cycle_count > 0:
            return {
                "thoughts": self.get_thoughts(limit=50),
                "market_analysis": self._market_analysis.copy(),
                "next_moves": list(self._next_moves),
                "strategy_scores": {
                    code: score.copy()
                    for code, score in self._strategy_scores.items()
                },
                "strategy_scores_by_symbol": {
                    sym: {code: score.copy() for code, score in scores.items()}
                    for sym, scores in self._strategy_scores_by_symbol.items()
                },
                "strategy_points": {
                    sym: points.copy()
                    for sym, points in self._strategy_points.items()
                },
                "cycle_count": self._cycle_count,
                "thought_count": len(self._thoughts),
                "last_updated": self._market_analysis.get(
                    "last_updated",
                    datetime.now(timezone.utc).isoformat(),
                ),
                # RL stats for dashboard
                "rl_distributions": self._learner.parameter_adapter.get_all_distributions(),
                "exploration_rate": self._learner._rl_exploration_rate,
                "total_trades_analyzed": self._learner._rl_total_trades,
                # XP and RL data for cross-process sync
                "strategy_xp": self._strategy_xp.get_all_xp(),
                "rl_stats_full": self._learner.get_rl_stats(),
                # Active LLM runtime selection
                "llm": {
                    "enabled": self._llm is not None,
                    "provider": self._llm_provider,
                    "model": self._llm_model,
                    "last_error": self._llm_last_error,
                },
                # LLM outputs for cross-process dashboard reads
                "llm_insights": self._llm.get_insights() if self._llm else [],
                "llm_stats": self._llm.get_stats() if self._llm else {
                    "provider": "none",
                    "model": "none",
                    "total_calls": 0,
                    "total_tokens_used": 0,
                    "estimated_cost_usd": 0,
                    "insights_count": 0,
                },
            }

        # Otherwise, try to load from Redis (engine writes, API reads)
        redis_state = self.load_from_redis()
        if redis_state:
            return redis_state

        # Default empty state
        return {
            "thoughts": [],
            "market_analysis": self._market_analysis.copy(),
            "next_moves": [],
            "strategy_scores": {},
            "strategy_scores_by_symbol": {},
            "strategy_points": {},
            "cycle_count": 0,
            "thought_count": 0,
            "last_updated": None,
            "rl_distributions": {},
            "exploration_rate": 0.10,
            "total_trades_analyzed": 0,
            "llm": {
                "enabled": self._llm is not None,
                "provider": self._llm_provider,
                "model": self._llm_model,
                "last_error": self._llm_last_error,
            },
            "llm_insights": [],
            "llm_stats": {
                "provider": "none",
                "model": "none",
                "total_calls": 0,
                "total_tokens_used": 0,
                "estimated_cost_usd": 0,
                "insights_count": 0,
            },
        }

    def _get_redis_state(self) -> Optional[dict]:
        """Helper: get Redis state, cached for the current call chain."""
        if self._cycle_count > 0:
            return None
        return self.load_from_redis()

    def get_thoughts(self, limit: int = 50) -> list:
        """Return recent thoughts, newest first. Falls back to Redis."""
        if self._cycle_count > 0:
            thoughts = list(self._thoughts)
            thoughts.reverse()
            return thoughts[:limit]
        rs = self.load_from_redis()
        return (rs or {}).get("thoughts", [])[:limit]

    def get_market_analysis(self) -> dict:
        """Return current market analysis. Falls back to Redis."""
        if self._cycle_count > 0:
            return self._market_analysis.copy()
        rs = self.load_from_redis()
        return (rs or {}).get("market_analysis", self._market_analysis.copy())

    def get_next_moves(self) -> list:
        """Return planned next actions. Falls back to Redis."""
        if self._cycle_count > 0:
            return list(self._next_moves)
        rs = self.load_from_redis()
        return (rs or {}).get("next_moves", [])

    def get_strategy_scores(self) -> dict:
        """Return per-strategy confidence scores. Falls back to Redis."""
        if self._cycle_count > 0:
            return {code: score.copy() for code, score in self._strategy_scores.items()}
        rs = self.load_from_redis()
        return (rs or {}).get("strategy_scores", {})

    def get_rl_stats(self) -> dict:
        """
        PURPOSE: Return comprehensive RL statistics for the brain dashboard.
        Falls back to Redis if local brain has no data (API process).

        Includes Thompson Sampling distributions, trade history stats,
        confidence adjustments, and exploration rate.

        Returns:
            dict: Full RL stats from the learner plus trade history summary.

        CALLED BY: api/routes_brain.py /rl-stats endpoint
        """
        # Fall back to Redis if this is the API process
        if self._cycle_count == 0:
            rs = self.load_from_redis()
            if rs and "rl_stats_full" in rs:
                return rs["rl_stats_full"]

        rl_stats = self._learner.get_rl_stats()

        # Add trade history summary
        trade_history = list(self._trade_history)
        total_trades = len(trade_history)
        total_wins = sum(1 for t in trade_history if t.get("net_profit", 0) > 0)
        total_profit = sum(t.get("net_profit", 0) for t in trade_history)

        rl_stats["trade_history_summary"] = {
            "total_trades": total_trades,
            "total_wins": total_wins,
            "win_rate": round(total_wins / total_trades, 3) if total_trades > 0 else 0.0,
            "total_profit": round(total_profit, 2),
        }

        # Add learner regime performance
        rl_stats["regime_performance"] = self._learner.get_regime_performance()

        # Add streaks
        rl_stats["streaks"] = self._learner.get_streaks()

        return rl_stats

    def get_strategy_xp(self) -> dict:
        """
        PURPOSE: Return XP/level data for all strategies.
        Falls back to Redis if local brain has no data (API process).

        Returns:
            dict: {strategy_code: strategy_xp_state}

        CALLED BY: api/routes_brain.py /strategy-xp endpoint
        """
        if self._cycle_count > 0:
            return self._strategy_xp.get_all_xp()
        # Fall back to Redis
        rs = self.load_from_redis()
        if rs and "strategy_xp" in rs:
            return rs["strategy_xp"]
        return self._strategy_xp.get_all_xp()

    # ════════════════════════════════════════════════════════════════
    # Auto-Allocation
    # ════════════════════════════════════════════════════════════════

    def get_auto_allocation_status(self) -> dict:
        """
        PURPOSE: Return auto-allocation status for dashboard API.

        Returns:
            dict: Full auto-allocation state including fitness scores,
                  rebalance history, and configuration.

        CALLED BY: api/routes_brain.py /auto-allocation-status endpoint
        """
        return self._auto_allocator.get_status()

    def set_auto_allocation_enabled(self, enabled: bool) -> None:
        """
        PURPOSE: Toggle auto-allocation on/off.

        CALLED BY: api/routes_brain.py PATCH /auto-allocation-status endpoint
        """
        self._auto_allocator.set_enabled(enabled)

    # ════════════════════════════════════════════════════════════════
    # Pending Parameter Updates (consumed by Engine)
    # ════════════════════════════════════════════════════════════════

    def get_pending_parameter_updates(self) -> Dict[str, Dict[str, Any]]:
        """
        PURPOSE: Return and clear pending parameter updates for the engine.

        Returns:
            dict: {strategy_code: {param: value}} — consumed once

        CALLED BY: engine.py every 60 cycles
        """
        updates = self._pending_parameter_updates.copy()
        self._pending_parameter_updates.clear()
        return updates

    def queue_parameter_update(self, strategy_code: str, param: str, value: Any) -> None:
        """
        PURPOSE: Queue a parameter update for a strategy.

        CALLED BY: LLM trade review / loss diagnosis callbacks
        """
        if strategy_code not in self._pending_parameter_updates:
            self._pending_parameter_updates[strategy_code] = {}
        self._pending_parameter_updates[strategy_code][param] = value
        logger.info(
            "brain_parameter_update_queued",
            strategy=strategy_code,
            param=param,
            value=value,
        )

    # ════════════════════════════════════════════════════════════════
    # LLM Async Helpers (fire-and-forget from sync process_cycle)
    # ════════════════════════════════════════════════════════════════

    def _normalize_error_message(self, raw_message: Optional[str], fallback: str) -> str:
        """Normalize error text to avoid blank dashboard messages."""
        message = " ".join(str(raw_message or "").strip().split())
        return message[:240] if message else fallback

    def _is_llm_error_content(self, content: str) -> bool:
        """Detect synthetic LLM error payloads emitted by LLMBrain."""
        return str(content or "").strip().startswith("[LLM Error")

    def _set_llm_runtime_error(self, raw_message: Optional[str], context: str) -> None:
        """Expose runtime LLM failures through /llm-config last_error."""
        normalized = self._normalize_error_message(raw_message, fallback="Unknown LLM runtime failure")
        self._llm_last_error = f"LLM runtime error [{context}]: {normalized}"
        logger.warning(
            "brain_llm_runtime_error",
            provider=self._llm_provider,
            model=self._llm_model,
            context=context,
            error=normalized,
        )

    def _clear_llm_runtime_error_if_needed(self) -> None:
        """Clear runtime errors after a successful LLM response."""
        if self._llm_last_error and self._llm_last_error.startswith("LLM runtime error"):
            self._llm_last_error = None

    def _ingest_llm_insight(
        self,
        insight: Optional[Dict[str, Any]],
        insight_type: str,
        success_confidence: float,
    ) -> None:
        """Normalize and publish LLM insight into thought stream + runtime status."""
        if not insight:
            return
        raw_content = insight.get("content")
        content = str(raw_content or "").strip()
        if not content:
            content = "[LLM Error][EmptyResponse] Provider returned empty content."

        is_error = bool(insight.get("is_error")) or self._is_llm_error_content(content)
        if is_error:
            self._set_llm_runtime_error(content, context=insight_type)
        else:
            self._clear_llm_runtime_error_if_needed()

        self._add_thought(
            "AI_INSIGHT",
            content,
            confidence=0.35 if is_error else success_confidence,
            metadata={
                "source": self._llm_provider or "llm",
                "model": self._llm_model,
                "type": insight_type,
                "llm_error": is_error,
            },
        )

    async def _llm_analyze_market(self, market_data: Dict) -> None:
        """Fire LLM market analysis with bull/bear debate pipeline.

        Pipeline: market analysis -> (wait) -> debate -> (wait) -> signal extraction.
        Delays between steps avoid rate limiting on providers with tight quotas (e.g. Z.AI).
        """
        try:
            # Step 1: Run the standard analysis (sentiment-aware)
            insight = await self._llm.analyze_market(market_data)
            self._ingest_llm_insight(
                insight=insight,
                insight_type="market_analysis",
                success_confidence=0.8,
            )

            # Brief pause to avoid rate limiting on low-tier providers
            await asyncio.sleep(5)

            # Step 2: Run bull/bear debate for structured signal
            debate_result = await self._llm.bull_bear_debate(market_data)
            if debate_result:
                self._ingest_llm_insight(
                    insight={"content": json.dumps(debate_result.get("verdict", {})), "type": "bull_bear_debate"},
                    insight_type="bull_bear_debate",
                    success_confidence=debate_result.get("verdict", {}).get("conviction", 0.5),
                )

                await asyncio.sleep(5)

                # Step 3: Extract actionable signal from debate
                signal_result = await self._llm.extract_signal(debate_result, market_data)
                if signal_result:
                    self._apply_llm_signal(signal_result)

        except Exception as e:
            self._set_llm_runtime_error(str(e), context="market_analysis")
            logger.warning("llm_market_analysis_failed", error=str(e))

    async def _llm_review_trade(self, trade_data: Dict) -> None:
        """Fire LLM trade review with structured reflection pipeline."""
        try:
            # Step 1: Standard review (memory-aware, sentiment-aware)
            insight = await self._llm.review_trade(trade_data)
            self._ingest_llm_insight(
                insight=insight,
                insight_type="trade_review",
                success_confidence=0.75,
            )

            # Step 2: Structured trade reflection for actionable adjustments
            reflection = await self._llm.structured_trade_review(trade_data)
            if reflection:
                self._apply_trade_reflection(reflection, trade_data)

        except Exception as e:
            self._set_llm_runtime_error(str(e), context="trade_review")
            logger.warning("llm_trade_review_failed", error=str(e))

    async def _llm_hourly_strategy_review(self) -> None:
        """Fire LLM hourly strategy review (rate-limited internally to 1h)."""
        try:
            # Build strategy stats from available brain state
            strategy_stats = {}
            for code, score in self._strategy_scores.items():
                strategy_stats[code] = {
                    "confidence": score.get("confidence", 0),
                    "reason": score.get("reason", ""),
                    "signal": score.get("signal", "none"),
                }
            # Add XP data if available
            xp_all = self._strategy_xp.get_all_xp()
            for code, xp in xp_all.items():
                if code not in strategy_stats:
                    strategy_stats[code] = {}
                strategy_stats[code]["xp"] = xp.get("xp", 0)
                strategy_stats[code]["level"] = xp.get("level", 1)
                strategy_stats[code]["win_streak"] = xp.get("win_streak", 0)
            if not strategy_stats:
                return
            insight = await self._llm.hourly_strategy_review(strategy_stats)
            self._ingest_llm_insight(
                insight=insight,
                insight_type="strategy_review",
                success_confidence=0.7,
            )
        except Exception as e:
            self._set_llm_runtime_error(str(e), context="strategy_review")
            logger.warning("llm_strategy_review_failed", error=str(e))

    async def _llm_analyze_regime_change(self, old_regime: str, new_regime: str, indicators: Dict) -> None:
        """Fire LLM regime change analysis and add result as a thought."""
        try:
            insight = await self._llm.analyze_regime_change(old_regime, new_regime, indicators)
            self._ingest_llm_insight(
                insight=insight,
                insight_type="regime_analysis",
                success_confidence=0.7,
            )
        except Exception as e:
            self._set_llm_runtime_error(str(e), context="regime_analysis")
            logger.warning("llm_regime_analysis_failed", error=str(e))

    async def _llm_diagnose_losses(self, loss_snapshot: Dict[str, Any]) -> None:
        """Run an AI loss diagnosis and add the result to thought stream."""
        try:
            insight = await self._llm.diagnose_losses(loss_snapshot)
            self._ingest_llm_insight(
                insight=insight,
                insight_type="loss_diagnosis",
                success_confidence=0.82,
            )
        except Exception as e:
            self._set_llm_runtime_error(str(e), context="loss_diagnosis")
            logger.warning("llm_loss_diagnosis_failed", error=str(e))

    # ════════════════════════════════════════════════════════════════
    # Structured LLM Signal Application
    # ════════════════════════════════════════════════════════════════

    def _apply_llm_signal(self, signal_result: Dict) -> None:
        """
        Apply a structured LLM signal to the brain's strategy scores.

        Bridges the gap between LLM analysis and actual trading decisions
        by adjusting strategy confidence based on signal_result from extract_signal().
        """
        try:
            signal = signal_result.get("signal", "HOLD")
            confidence = signal_result.get("confidence", 0)
            strategy_prefs = signal_result.get("strategy_preferences", {})
            risk_adj = signal_result.get("risk_adjustment", "NORMAL")

            # Only apply if confidence is meaningful
            if confidence < 0.3:
                logger.debug("llm_signal_low_confidence", confidence=confidence)
                return

            # Adjust strategy scores based on LLM preferences
            for code, pref in strategy_prefs.items():
                if code not in self._strategy_scores:
                    continue
                current = self._strategy_scores[code].get("confidence", 50)
                # Scale adjustment: pref is -1.0 to 1.0, map to -15 to +15 points
                adjustment = pref * 15.0 * confidence
                new_confidence = max(0, min(100, current + adjustment))
                self._strategy_scores[code]["confidence"] = round(new_confidence, 1)
                self._strategy_scores[code]["llm_signal"] = signal
                self._strategy_scores[code]["llm_pref"] = round(pref, 2)

            # Apply risk adjustment to pending parameter updates
            if risk_adj == "TIGHTEN":
                self._pending_parameter_updates["_risk"] = {"lot_scale": 0.75}
            elif risk_adj == "LOOSEN":
                self._pending_parameter_updates["_risk"] = {"lot_scale": 1.25}
            else:
                self._pending_parameter_updates.pop("_risk", None)

            # Store key levels if provided
            key_levels = signal_result.get("key_levels", {})
            if key_levels:
                self._market_analysis["key_levels"] = key_levels

            # Add thought about signal application
            self._add_thought(
                "DECISION",
                f"LLM signal: {signal} (confidence {confidence:.0%}). "
                f"Risk: {risk_adj}. "
                f"Strategy prefs: {', '.join(f'{k}={v:+.1f}' for k, v in strategy_prefs.items() if abs(v) > 0.1)}",
                confidence=confidence,
                metadata={"source": "llm_signal", "signal": signal, "risk": risk_adj},
            )

            logger.info(
                "llm_signal_applied",
                signal=signal,
                confidence=confidence,
                risk=risk_adj,
                adjustments={k: v for k, v in strategy_prefs.items() if abs(v) > 0.1},
            )
        except Exception as e:
            logger.warning("llm_signal_apply_failed", error=str(e))

    def _apply_trade_reflection(self, reflection: Dict, trade_data: Dict) -> None:
        """
        Apply structured trade reflection to strategy confidence and XP.

        Feeds the structured lesson from the LLM back into the brain's
        learning systems (strategy scores, XP adjustments).
        """
        try:
            adjustment = reflection.get("strategy_adjustment", {})
            strategy_code = adjustment.get("strategy", trade_data.get("strategy", ""))
            direction = adjustment.get("direction", "NEUTRAL")
            magnitude = adjustment.get("magnitude", 0)

            if not strategy_code or direction == "NEUTRAL" or magnitude < 0.1:
                return

            # Adjust strategy confidence
            if strategy_code in self._strategy_scores:
                current = self._strategy_scores[strategy_code].get("confidence", 50)
                if direction == "BOOST":
                    delta = magnitude * 10.0  # 0-10 point boost
                elif direction == "PENALIZE":
                    delta = -magnitude * 10.0  # 0-10 point penalty
                else:
                    delta = 0
                new_confidence = max(0, min(100, current + delta))
                self._strategy_scores[strategy_code]["confidence"] = round(new_confidence, 1)

            # Add a learning thought
            outcome = reflection.get("outcome_quality", "?")
            lesson = reflection.get("lesson", "")
            root_cause = reflection.get("root_cause", "")

            self._add_thought(
                "LEARNING",
                f"Trade reflection [{outcome}]: {root_cause} "
                f"Lesson: {lesson} "
                f"Adjustment: {strategy_code} {direction} ({magnitude:.1f})",
                confidence=0.7,
                metadata={
                    "source": "trade_reflection",
                    "strategy": strategy_code,
                    "direction": direction,
                    "magnitude": magnitude,
                    "outcome": outcome,
                },
            )

            logger.info(
                "trade_reflection_applied",
                strategy=strategy_code,
                direction=direction,
                magnitude=magnitude,
                outcome=outcome,
            )
        except Exception as e:
            logger.warning("trade_reflection_apply_failed", error=str(e))

    # ════════════════════════════════════════════════════════════════
    # Internal Thought Generation
    # ════════════════════════════════════════════════════════════════

    def _add_thought(
        self,
        thought_type: str,
        content: str,
        confidence: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        PURPOSE: Add a thought to the rolling log.

        Args:
            thought_type: ANALYSIS, DECISION, LEARNING, or PLAN
            content: Human-readable thought content
            confidence: Confidence level 0-1
            metadata: Optional additional data

        CALLED BY: Internal thought generators
        """
        thought_metadata: Dict[str, Any] = metadata.copy() if isinstance(metadata, dict) else {}

        symbol_hint = thought_metadata.get("symbol") or self._market_analysis.get("symbol")
        symbol = str(symbol_hint).upper() if symbol_hint else None
        if symbol in {"?", "UNKNOWN", "NONE", "NULL"}:
            market_symbol = self._market_analysis.get("symbol")
            symbol = str(market_symbol).upper() if market_symbol else None

        if symbol:
            thought_metadata["symbol"] = symbol

            symbol_snapshot = self._symbol_market_analysis.get(symbol)
            if not symbol_snapshot:
                all_symbols = self._market_analysis.get("symbols", {})
                if isinstance(all_symbols, dict):
                    snapshot = all_symbols.get(symbol)
                    if isinstance(snapshot, dict):
                        symbol_snapshot = snapshot

            bid = thought_metadata.get("bid")
            ask = thought_metadata.get("ask")
            try:
                bid = float(bid) if bid is not None else None
            except (TypeError, ValueError):
                bid = None
            try:
                ask = float(ask) if ask is not None else None
            except (TypeError, ValueError):
                ask = None

            if symbol_snapshot:
                if bid is None:
                    raw_bid = symbol_snapshot.get("bid")
                    try:
                        bid = float(raw_bid) if raw_bid is not None else None
                    except (TypeError, ValueError):
                        bid = None
                if ask is None:
                    raw_ask = symbol_snapshot.get("ask")
                    try:
                        ask = float(raw_ask) if raw_ask is not None else None
                    except (TypeError, ValueError):
                        ask = None
                if "regime" not in thought_metadata and symbol_snapshot.get("regime"):
                    thought_metadata["regime"] = symbol_snapshot.get("regime")

            if bid is not None:
                thought_metadata["bid"] = bid
            if ask is not None:
                thought_metadata["ask"] = ask

            price = thought_metadata.get("price")
            try:
                price = float(price) if price is not None else None
            except (TypeError, ValueError):
                price = None

            if price is None:
                if bid is not None and ask is not None:
                    price = (bid + ask) / 2.0
                else:
                    price = bid if bid is not None else ask

            if price is not None:
                thought_metadata["price"] = price
                previous_price = self._last_thought_price_by_symbol.get(symbol)
                if previous_price is not None and previous_price != 0:
                    price_change = price - previous_price
                    thought_metadata.setdefault("price_prev", previous_price)
                    thought_metadata.setdefault("price_change", price_change)
                    thought_metadata.setdefault(
                        "price_change_pct",
                        (price_change / previous_price) * 100.0,
                    )
                self._last_thought_price_by_symbol[symbol] = price

        thought = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": thought_type,
            "content": content,
            "confidence": round(confidence, 2),
            "metadata": thought_metadata,
        }
        self._thoughts.append(thought)

        logger.debug(
            "brain_thought",
            thought_type=thought_type,
            content=content[:120],
        )

    def _update_market_analysis(
        self,
        indicators: Dict,
        regime: Optional[str],
        confidence: Optional[float],
        symbol: str,
        cycle_data: dict,
    ) -> Dict[str, Any]:
        """
        PURPOSE: Update the market analysis state from current cycle data.

        The shape must match what the frontend expects:
          - trend: str (human-readable)
          - momentum: str (human-readable)
          - volatility: str (human-readable)
          - regime: str (raw regime enum like "TRENDING_UP", not the interpreted sentence)
          - regime_confidence: float (0-1)
          - key_levels: { ema_20, ema_50, current_price, ... }
          - summary: str (human-readable regime interpretation)

        CALLED BY: process_cycle
        """
        trend_text = analyze_trend(
            indicators.get("ema_20"),
            indicators.get("ema_50"),
            indicators.get("adx"),
        )
        momentum_text = analyze_momentum(
            indicators.get("rsi"),
            indicators.get("adx"),
        )
        volatility_text = analyze_volatility(
            indicators.get("atr"),
            cycle_data.get("spread"),
        )
        regime_summary = interpret_regime(regime, confidence)

        # Build key_levels dict for frontend display
        key_levels: Dict[str, float] = {}
        if indicators.get("ema_20") is not None:
            key_levels["ema_20"] = indicators["ema_20"]
        if indicators.get("ema_50") is not None:
            key_levels["ema_50"] = indicators["ema_50"]
        bid = cycle_data.get("bid")
        ask = cycle_data.get("ask")
        if bid is not None:
            key_levels["current_price"] = bid
        if indicators.get("atr") is not None:
            key_levels["atr"] = indicators["atr"]

        symbol_snapshot = {
            # Fields the frontend reads directly:
            "trend": trend_text,
            "momentum": momentum_text,
            "volatility": volatility_text,
            "regime": regime or "UNKNOWN",
            "regime_confidence": confidence or 0.0,
            "key_levels": key_levels,
            "summary": regime_summary,
            # Extra fields for internal use / other endpoints:
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": cycle_data.get("spread"),
            "indicators": indicators.copy() if indicators else {},
            "new_candle": bool(cycle_data.get("new_candle", False)),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self._symbol_market_analysis[symbol] = symbol_snapshot
        self._set_primary_market_symbol(symbol)
        return symbol_snapshot

    def _set_primary_market_symbol(self, symbol: str) -> None:
        """Set which symbol drives the top-level market_analysis payload."""
        primary = self._symbol_market_analysis.get(symbol)
        if not primary:
            return
        symbols_copy = {
            sym: data.copy() for sym, data in self._symbol_market_analysis.items()
        }
        merged = primary.copy()
        merged["symbols"] = symbols_copy
        self._market_analysis = merged

    def _update_strategy_scores(
        self,
        regime: Optional[str],
        indicators: Dict,
        symbol: str = "GLOBAL",
    ) -> None:
        """
        PURPOSE: Recalculate per-strategy confidence scores, now factoring in
        RL-based confidence adjustments from the learner.

        The frontend expects each score to have: { confidence, reason, status }
        where status is one of: IDLE | WATCHING | WARMING_UP | READY | ACTIVE

        CALLED BY: process_cycle
        """
        # Get RL confidence adjustments from the learner
        rl_adjustments = self._learner.get_strategy_confidence_adjustments()

        symbol_scores: Dict[str, Dict[str, Any]] = {}
        for code in STRATEGY_CODES:
            assessment = assess_strategy_fitness(code, regime, indicators)
            confidence = assessment["confidence"]
            reason = assessment["reason"]

            # Apply RL confidence adjustment
            rl_adj = rl_adjustments.get(code, {})
            rl_delta = rl_adj.get("adjustment", 0.0)
            rl_reason = rl_adj.get("reason", "")
            rl_preset = rl_adj.get("rl_preset", "moderate")
            rl_expected = rl_adj.get("rl_expected", 0.5)

            if rl_delta != 0.0:
                confidence = max(0.05, min(0.95, confidence + rl_delta))
                reason += f" [RL: {rl_delta:+.3f} ({rl_reason})]"

            points = self._get_strategy_points(symbol, code)
            closed_count = self._get_closed_trade_count(symbol, code, lookback=60)
            if closed_count >= 3:
                point_adj = max(-0.2, min(0.2, ((points - POINTS_START) / POINTS_START) * 0.2))
                confidence = max(0.05, min(0.95, confidence + point_adj))
                reason += f" [Points: {points}/{POINTS_MAX} ({point_adj:+.3f})]"

            # Derive a status from confidence level
            if confidence >= 0.7:
                status = "ACTIVE"
            elif confidence >= 0.55:
                status = "READY"
            elif confidence >= 0.4:
                status = "WATCHING"
            elif confidence >= 0.25:
                status = "WARMING_UP"
            else:
                status = "IDLE"

            symbol_scores[code] = {
                "name": STRATEGY_NAMES.get(code, f"Strategy {code}"),
                "confidence": round(confidence, 3),
                "reason": reason,
                "status": status,
                "rl_preset": rl_preset,
                "rl_expected": rl_expected,
                "points": points,
                "symbol": symbol,
                "trades_on_symbol": closed_count,
            }
        self._strategy_scores_by_symbol[symbol] = symbol_scores
        self._strategy_scores = symbol_scores

    def _parse_signal_key(self, signal_key: Any, fallback_symbol: str) -> tuple[str, str]:
        """Parse keys like EURUSD_A into strategy code + symbol."""
        key_str = str(signal_key or "")
        if "_" not in key_str:
            return key_str.upper() or "?", fallback_symbol
        symbol, strategy_code = key_str.rsplit("_", 1)
        strategy_code = strategy_code.upper() or "?"
        symbol = symbol or fallback_symbol
        return strategy_code, symbol

    def _is_closed_trade_payload(self, trade_data: Dict[str, Any]) -> bool:
        """Return True only when payload appears to represent a closed trade."""
        status = str(trade_data.get("status") or "").lower()
        if status == "closed":
            return True
        if trade_data.get("exit_price") is not None:
            return True
        if "net_profit" in trade_data and trade_data.get("ticket") is not None:
            return True
        if "profit" in trade_data and trade_data.get("won") is not None:
            return True
        return False

    def _get_closed_trade_count(self, symbol: str, strategy_code: str, lookback: int = 50) -> int:
        """Count closed trades for a symbol/strategy pair over a recent window."""
        if lookback <= 0:
            return 0
        symbol_upper = str(symbol).upper()
        strategy_upper = str(strategy_code).upper()
        count = 0
        for trade in list(self._trade_history)[-lookback:]:
            if not self._is_closed_trade_payload(trade):
                continue
            trade_symbol = str(trade.get("symbol", "")).upper()
            trade_strategy = str(trade.get("strategy", "")).split("_")[-1].upper()
            if trade_symbol == symbol_upper and trade_strategy == strategy_upper:
                count += 1
        return count

    def _get_strategy_points(self, symbol: str, strategy_code: str) -> int:
        """Get mutable point score for a symbol/strategy pair."""
        symbol_key = str(symbol).upper()
        strategy_key = str(strategy_code).upper()
        if strategy_key not in self._strategy_points[symbol_key]:
            self._strategy_points[symbol_key][strategy_key] = POINTS_START
        return self._strategy_points[symbol_key][strategy_key]

    def _update_strategy_points(
        self,
        symbol: str,
        strategy_code: str,
        net_profit: float,
        rl_reward: float,
        duration_seconds: int,
    ) -> tuple[int, int]:
        """
        Update point score and return (new_points, delta).

        Points reinforce profitable, efficient behavior and penalize repeated losses.
        """
        current = self._get_strategy_points(symbol, strategy_code)
        delta = 0
        if net_profit > 0:
            delta = 4 + min(4, int(round(max(0.0, rl_reward))))
            if duration_seconds and duration_seconds < 1800:
                delta += 1
        elif net_profit < 0:
            delta = -5 - min(3, int(round(abs(min(0.0, rl_reward)))))
            if duration_seconds and duration_seconds < 600:
                delta -= 1
        else:
            delta = -1

        updated = max(POINTS_MIN, min(POINTS_MAX, current + delta))
        self._strategy_points[str(symbol).upper()][str(strategy_code).upper()] = updated
        return updated, delta

    def _should_block_signal_by_points(self, symbol: str, strategy_code: str) -> bool:
        """Hard guard to prevent continued firing when symbol edge score collapses."""
        closed_count = self._get_closed_trade_count(symbol, strategy_code, lookback=60)
        if closed_count < POINT_TRADE_MIN_FOR_BLOCK:
            return False
        return self._get_strategy_points(symbol, strategy_code) <= POINT_BLOCK_THRESHOLD

    def _build_loss_diagnostics_snapshot(self, lookback: int = 40) -> Dict[str, Any]:
        """Build compact performance stats used for automated loss diagnosis."""
        closed = [
            t for t in self._trade_history
            if self._is_closed_trade_payload(t)
        ][-lookback:]
        total_trades = len(closed)
        wins = sum(1 for t in closed if t.get("net_profit", t.get("profit", 0)) > 0)
        total_profit = round(sum(t.get("net_profit", t.get("profit", 0)) for t in closed), 2)

        by_strategy: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "profit": 0.0}
        )
        by_symbol: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "profit": 0.0}
        )
        by_symbol_strategy: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "profit": 0.0}
        )

        losing_streak = 0
        for trade in reversed(closed):
            pnl = trade.get("net_profit", trade.get("profit", 0))
            if pnl < 0:
                losing_streak += 1
            else:
                break

        for trade in closed:
            strategy = str(trade.get("strategy", "?")).split("_")[-1].upper()
            symbol = str(trade.get("symbol", "?")).upper()
            pnl = float(trade.get("net_profit", trade.get("profit", 0)) or 0.0)
            won = pnl > 0

            by_strategy[strategy]["trades"] += 1
            by_strategy[strategy]["wins"] += 1 if won else 0
            by_strategy[strategy]["profit"] += pnl

            by_symbol[symbol]["trades"] += 1
            by_symbol[symbol]["wins"] += 1 if won else 0
            by_symbol[symbol]["profit"] += pnl

            combo = f"{symbol}:{strategy}"
            by_symbol_strategy[combo]["trades"] += 1
            by_symbol_strategy[combo]["wins"] += 1 if won else 0
            by_symbol_strategy[combo]["profit"] += pnl

        # Round profits for compact API payloads
        for bucket in (by_strategy, by_symbol, by_symbol_strategy):
            for stats in bucket.values():
                stats["profit"] = round(stats["profit"], 2)

        return {
            "lookback": lookback,
            "total_trades": total_trades,
            "wins": wins,
            "win_rate": round(wins / total_trades, 3) if total_trades else 0.0,
            "total_profit": total_profit,
            "losing_streak": losing_streak,
            "by_strategy": dict(by_strategy),
            "by_symbol": dict(by_symbol),
            "by_symbol_strategy": dict(by_symbol_strategy),
            "strategy_points": {
                sym: pts.copy() for sym, pts in self._strategy_points.items()
            },
        }

    def _is_losing_cluster(self, snapshot: Dict[str, Any]) -> bool:
        """Decide if current performance warrants a diagnostic action."""
        trades = snapshot.get("total_trades", 0)
        if trades < 8:
            return False
        total_profit = snapshot.get("total_profit", 0.0)
        win_rate = snapshot.get("win_rate", 0.0)
        losing_streak = snapshot.get("losing_streak", 0)
        return (total_profit < 0 and win_rate < 0.48) or losing_streak >= 4

    def _format_loss_summary(self, snapshot: Dict[str, Any]) -> str:
        """Create concise human-readable diagnostics for ongoing losses."""
        combo_stats = snapshot.get("by_symbol_strategy", {})
        worst_combo = None
        worst_profit = 0.0
        for combo, stats in combo_stats.items():
            profit = float(stats.get("profit", 0.0))
            trades = int(stats.get("trades", 0))
            if trades < 3:
                continue
            if worst_combo is None or profit < worst_profit:
                worst_combo = combo
                worst_profit = profit

        headline = (
            f"Loss diagnostics: {snapshot.get('total_trades', 0)} closed trades, "
            f"win rate {snapshot.get('win_rate', 0.0):.0%}, P&L {snapshot.get('total_profit', 0.0):+.2f}, "
            f"losing streak {snapshot.get('losing_streak', 0)}."
        )
        if worst_combo:
            combo_detail = combo_stats.get(worst_combo, {})
            headline += (
                f" Weakest edge: {worst_combo} "
                f"({combo_detail.get('wins', 0)}/{combo_detail.get('trades', 0)} wins, "
                f"{combo_detail.get('profit', 0.0):+.2f}). "
                "Reducing aggression until edge recovers."
            )
        return headline

    def _generate_candle_thought(
        self,
        indicators: Dict,
        regime: Optional[str],
        confidence: Optional[float],
        symbol: str,
        price: Optional[float] = None,
        spread: Optional[float] = None,
    ) -> None:
        """
        PURPOSE: Generate an ANALYSIS thought on new candle.

        CALLED BY: process_cycle (when new_candle is True)
        """
        def _fmt_number(value: Any, digits: int = 2) -> Optional[str]:
            try:
                return f"{float(value):.{digits}f}"
            except (TypeError, ValueError):
                return None

        price_str = _fmt_number(price, 5)
        spread_str = _fmt_number(spread, 5)
        rsi_val = indicators.get("rsi")
        adx_val = indicators.get("adx")
        atr_val = indicators.get("atr")
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")

        parts = [f"[{symbol}] Candle closed."]

        if price_str is not None:
            parts.append(f"Price: {price_str}.")
        if spread_str is not None and spread_str != "0.00000":
            parts.append(f"Spread: {spread_str}.")

        # Trend summary
        if ema_20 is not None and ema_50 is not None:
            direction = "bullish" if ema_20 > ema_50 else "bearish" if ema_20 < ema_50 else "flat"
            ema_20_str = _fmt_number(ema_20, 5) or str(ema_20)
            ema_50_str = _fmt_number(ema_50, 5) or str(ema_50)
            parts.append(f"Trend: {direction} (EMA20 {ema_20_str} vs EMA50 {ema_50_str}).")

        # Regime
        if regime:
            conf_pct = round(confidence * 100) if confidence else 0
            parts.append(f"Regime: {regime} ({conf_pct}% confidence).")

        # RSI note
        if rsi_val is not None:
            rsi_str = _fmt_number(rsi_val, 2) or str(rsi_val)
            if rsi_val <= 30:
                parts.append(f"Momentum: RSI {rsi_str} (oversold).")
            elif rsi_val >= 70:
                parts.append(f"Momentum: RSI {rsi_str} (overbought).")
            else:
                parts.append(f"Momentum: RSI {rsi_str} (neutral).")

        # ADX note
        if adx_val is not None:
            strength = "strong" if adx_val >= 25 else "weak"
            adx_str = _fmt_number(adx_val, 2) or str(adx_val)
            parts.append(f"Trend strength: ADX {adx_str} ({strength}).")

        if atr_val is not None:
            atr_str = _fmt_number(atr_val, 5) or str(atr_val)
            parts.append(f"Volatility: ATR {atr_str}.")

        content = " ".join(parts)
        self._add_thought("ANALYSIS", content, confidence=confidence or 0.5, metadata={
            "trigger": "new_candle",
            "symbol": symbol,
            "price": price,
            "spread": spread,
            "regime": regime,
            "regime_confidence": confidence,
            "indicators": indicators,
        })

    def _generate_signal_thought(
        self,
        strategy_code: str,
        signal: Dict,
        risk_check: Optional[Dict],
        symbol: Optional[str] = None,
    ) -> None:
        """
        PURPOSE: Generate a DECISION thought when a strategy produces a signal.

        CALLED BY: process_cycle (when signal detected)
        """
        strategy_name = STRATEGY_NAMES.get(strategy_code, f"Strategy {strategy_code}")
        direction = signal.get("direction", "?")
        entry = signal.get("entry")
        sl = signal.get("sl")
        tp = signal.get("tp")

        content = (
            f"{strategy_name} ({strategy_code}) generated {direction} signal"
            f"{f' on {symbol}' if symbol else ''}. "
            f"Entry: {entry}, SL: {sl}, TP: {tp}."
        )

        if risk_check:
            if risk_check.get("approved"):
                content += f" Risk check PASSED (size: {risk_check.get('position_size')} lots, risk score: {risk_check.get('risk_score')})."
            else:
                content += f" Risk check REJECTED: {risk_check.get('reason')}."

        self._add_thought("DECISION", content, confidence=0.7, metadata={
            "strategy": strategy_code,
            "symbol": symbol,
            "signal": signal,
            "risk_check": risk_check,
        })

    def _generate_trade_thought(self, trade: Dict, risk_check: Optional[Dict]) -> None:
        """
        PURPOSE: Generate a DECISION thought when a trade is executed.

        CALLED BY: process_cycle (when trade is not None)
        """
        raw_strategy_key = str(trade.get("strategy", "?"))
        strategy_code = raw_strategy_key.split("_")[-1].upper()
        strategy_name = STRATEGY_NAMES.get(strategy_code, f"Strategy {strategy_code}")
        direction = trade.get("direction", "?")
        lots = trade.get("lots")
        ticket = trade.get("ticket")
        symbol = trade.get("symbol")
        if not symbol and "_" in raw_strategy_key:
            symbol = raw_strategy_key.rsplit("_", 1)[0]
        symbol_part = f"{symbol} " if symbol else ""

        content = (
            f"Trade EXECUTED: {strategy_name} ({strategy_code}) {direction} "
            f"{symbol_part}{lots} lots. "
            f"Ticket #{ticket}."
        )

        self._add_thought("DECISION", content, confidence=0.8, metadata={
            "trigger": "trade_executed",
            "trade": trade,
            "strategy": strategy_code,
            "symbol": symbol,
        })

    def _generate_rejection_thought(self, signals: Dict, risk_check: Dict) -> None:
        """
        PURPOSE: Generate a DECISION thought when a trade is rejected by risk manager.

        CALLED BY: process_cycle (when risk_check.approved is False)
        """
        reason = risk_check.get("reason", "Unknown reason")
        content = f"Trade REJECTED by risk manager: {reason}. Signal was valid but risk parameters not met."

        self._add_thought("DECISION", content, confidence=0.6, metadata={
            "trigger": "trade_rejected",
            "risk_check": risk_check,
        })

    def _generate_regime_change_thought(
        self,
        old_regime: str,
        new_regime: str,
        confidence: Optional[float],
        symbol: Optional[str] = None,
    ) -> None:
        """
        PURPOSE: Generate an ANALYSIS thought on regime change.

        CALLED BY: process_cycle (when regime changes)
        """
        conf_pct = round(confidence * 100) if confidence else 0
        content = (
            f"Regime shift detected{f' on {symbol}' if symbol else ''}: "
            f"{old_regime} -> {new_regime} ({conf_pct}% confidence). "
            f"Adjusting strategy expectations."
        )

        # Add strategy implications
        if new_regime in ("TRENDING_UP", "TRENDING_DOWN"):
            content += " Trend-following (A) favored. Mean reversion (B) should be cautious."
        elif new_regime == "RANGING":
            content += " Mean reversion (B) and grid strategies favored. Trend following (A) should stand down."
        elif new_regime == "TRANSITIONING":
            content += " All strategies should reduce exposure until new regime stabilizes."

        self._add_thought("ANALYSIS", content, confidence=confidence or 0.5, metadata={
            "trigger": "regime_change",
            "old_regime": old_regime,
            "new_regime": new_regime,
            "symbol": symbol,
        })

    def _check_rsi_crossing(self, rsi_val: Optional[float], symbol: Optional[str] = None) -> None:
        """
        PURPOSE: Detect RSI crossing key thresholds (30, 70) and generate thoughts.

        CALLED BY: process_cycle
        """
        if rsi_val is None:
            return

        # Determine current zone
        if rsi_val <= 30:
            current_zone = "oversold"
        elif rsi_val >= 70:
            current_zone = "overbought"
        else:
            current_zone = "neutral"

        symbol_key = str(symbol or "GLOBAL").upper()
        previous_zone = self._last_rsi_zone_by_symbol.get(symbol_key, self._last_rsi_zone)

        # Check for zone transition
        if previous_zone is not None and current_zone != previous_zone:
            if current_zone == "oversold":
                content = (
                    f"RSI crossed below 30 ({rsi_val})"
                    f"{f' on {symbol}' if symbol else ''}. Entering oversold territory — "
                    "mean reversion and scalper setups are in play."
                )
                self._add_thought("ANALYSIS", content, confidence=0.65, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "into_oversold",
                    "symbol": symbol,
                })
            elif current_zone == "overbought":
                content = (
                    f"RSI crossed above 70 ({rsi_val})"
                    f"{f' on {symbol}' if symbol else ''}. Entering overbought territory — "
                    "watching for exhaustion and reversal setups."
                )
                self._add_thought("ANALYSIS", content, confidence=0.65, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "into_overbought",
                    "symbol": symbol,
                })
            elif previous_zone == "oversold":
                content = (
                    f"RSI recovered above 30 ({rsi_val})"
                    f"{f' on {symbol}' if symbol else ''}. Leaving oversold — potential bounce underway."
                )
                self._add_thought("ANALYSIS", content, confidence=0.6, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "out_of_oversold",
                    "symbol": symbol,
                })
            elif previous_zone == "overbought":
                content = (
                    f"RSI dropped below 70 ({rsi_val})"
                    f"{f' on {symbol}' if symbol else ''}. Leaving overbought — momentum fading."
                )
                self._add_thought("ANALYSIS", content, confidence=0.6, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "out_of_overbought",
                    "symbol": symbol,
                })

        self._last_rsi_zone_by_symbol[symbol_key] = current_zone
        self._last_rsi_zone = current_zone

    def _check_adx_crossing(self, adx_val: Optional[float], symbol: Optional[str] = None) -> None:
        """
        PURPOSE: Detect ADX crossing the 25 threshold and generate thoughts.

        CALLED BY: process_cycle
        """
        if adx_val is None:
            return

        current_zone = "trending" if adx_val >= 25 else "weak"

        symbol_key = str(symbol or "GLOBAL").upper()
        previous_zone = self._last_adx_zone_by_symbol.get(symbol_key, self._last_adx_zone)

        if previous_zone is not None and current_zone != previous_zone:
            if current_zone == "trending":
                content = (
                    f"ADX crossed above 25 ({adx_val})"
                    f"{f' on {symbol}' if symbol else ''}. Trend is strengthening — "
                    f"trend-following strategies should perform well."
                )
            else:
                content = (
                    f"ADX dropped below 25 ({adx_val})"
                    f"{f' on {symbol}' if symbol else ''}. Trend is weakening — "
                    f"mean reversion conditions developing."
                )
            self._add_thought("ANALYSIS", content, confidence=0.6, metadata={
                "trigger": "adx_crossing",
                "adx": adx_val,
                "direction": current_zone,
                "symbol": symbol,
            })

        self._last_adx_zone_by_symbol[symbol_key] = current_zone
        self._last_adx_zone = current_zone

    def _generate_periodic_summary(
        self,
        indicators: Dict,
        regime: Optional[str],
        symbol: str,
        cycle_data: dict,
        symbol_snapshots: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        PURPOSE: Generate a periodic PLAN thought summarizing current state.

        Generated every 5 minutes even if nothing significant happened.
        Provides a "status check" thought to show the Brain is alive and monitoring.

        CALLED BY: process_cycle (every PERIODIC_SUMMARY_INTERVAL seconds)
        """
        rsi_val = indicators.get("rsi")
        adx_val = indicators.get("adx")
        bid = cycle_data.get("bid")

        def _fmt_price(value: Any) -> Optional[str]:
            try:
                return f"{float(value):.5f}"
            except (TypeError, ValueError):
                return None

        parts = [f"Periodic check on {symbol}."]

        bid_str = _fmt_price(bid)
        if bid_str:
            parts.append(f"Price at {bid_str}.")

        if regime:
            parts.append(f"Regime: {regime}.")

        if rsi_val is not None:
            parts.append(f"RSI: {rsi_val}.")

        if adx_val is not None:
            parts.append(f"ADX: {adx_val}.")

        # Pair-by-pair snapshot summary for easier operational debugging.
        if symbol_snapshots:
            pair_summaries: List[str] = []
            for pair, snapshot in list(symbol_snapshots.items())[:6]:
                pair_regime = snapshot.get("regime", "UNKNOWN")
                pair_bid_str = _fmt_price(snapshot.get("bid"))
                if pair_bid_str:
                    pair_summaries.append(f"{pair} {pair_regime} @{pair_bid_str}")
                else:
                    pair_summaries.append(f"{pair} {pair_regime}")
            if pair_summaries:
                parts.append("Pairs: " + "; ".join(pair_summaries) + ".")

        # Summarize what we're watching
        if self._next_moves:
            first_move = self._next_moves[0]
            if isinstance(first_move, dict):
                parts.append(f"Watching: {first_move.get('action', 'market')} — {first_move.get('condition', '')}")
            else:
                parts.append(f"Watching: {first_move}")

        # Add RL summary
        parts.append(f"RL trades analyzed: {self._learner._rl_total_trades}.")

        parts.append(f"Processed {self._cycle_count} cycles.")

        content = " ".join(parts)
        self._add_thought("PLAN", content, confidence=0.5, metadata={
            "trigger": "periodic_summary",
            "symbol": symbol,
            "pair_count": len(symbol_snapshots or {}),
            "cycle_count": self._cycle_count,
            "rl_total_trades": self._learner._rl_total_trades,
        })
