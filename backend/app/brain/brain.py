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
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

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
    "D": "Volatility Harvester",
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
            "last_updated": None,
        }
        self._next_moves: List[Dict] = []
        self._strategy_scores: Dict[str, Dict] = {}
        self._last_regime: Optional[str] = None
        self._last_rsi_zone: Optional[str] = None
        self._last_adx_zone: Optional[str] = None
        self._last_periodic_thought: float = 0.0
        self._cycle_count: int = 0
        self._trade_history: deque = deque(maxlen=50)

        # Initialize RL-enhanced learner
        self._learner = BrainLearner()

        # Initialize Pokemon-style XP system
        self._strategy_xp = StrategyXP()

        # Initialize auto-allocation engine
        self._auto_allocator = AutoAllocator()

        # Initialize LLM Brain (GPT-powered trading intelligence)
        self._llm: Optional[LLMBrain] = None
        if settings.OPENAI_API_KEY:
            self._llm = LLMBrain(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
            )
            logger.info("brain_llm_initialized", model=settings.OPENAI_MODEL)
        else:
            logger.info("brain_llm_disabled", reason="No OPENAI_API_KEY configured")

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
    # Core Processing
    # ════════════════════════════════════════════════════════════════

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

        indicators = cycle_data.get("indicators", {})
        regime = cycle_data.get("regime")
        confidence = cycle_data.get("confidence")
        new_candle = cycle_data.get("new_candle", False)
        signals = cycle_data.get("signals", {})
        risk_check = cycle_data.get("risk_check")
        trade = cycle_data.get("trade")
        symbol = cycle_data.get("symbol", "XAUUSD")

        # ── Always update market analysis ──
        self._update_market_analysis(indicators, regime, confidence, symbol, cycle_data)

        # ── Always update strategy scores (now RL-enhanced) ──
        self._update_strategy_scores(regime, indicators)

        # ── Always update next moves ──
        self._next_moves = generate_next_moves(indicators, regime, signals, symbol)

        # ── Decide what thoughts to generate ──

        # 1. New candle — always generate analysis thought
        if new_candle:
            self._generate_candle_thought(indicators, regime, confidence, symbol)

        # 2. Signal generated — check RL override, then generate decision thought
        for code, sig in signals.items():
            if isinstance(sig, dict) and "direction" in sig:
                # RL signal override check
                if regime:
                    should_skip, reason = self._learner.should_override_signal(
                        code, regime, indicators
                    )
                    if should_skip:
                        self._add_thought(
                            "DECISION",
                            f"RL override: Skipping {STRATEGY_NAMES.get(code, code)} signal -- {reason}",
                            confidence=0.75,
                            metadata={
                                "trigger": "rl_override",
                                "strategy": code,
                                "reason": reason,
                            },
                        )
                        continue  # Skip generating normal signal thought

                self._generate_signal_thought(code, sig, risk_check)

        # 3. Trade executed — always generate decision thought
        if trade is not None:
            self._generate_trade_thought(trade, risk_check)

        # 4. Trade rejected — generate decision thought
        if risk_check and not risk_check.get("approved", True):
            self._generate_rejection_thought(signals, risk_check)

        # 5. Regime change — always generate analysis thought
        if regime is not None and regime != self._last_regime and self._last_regime is not None:
            self._generate_regime_change_thought(self._last_regime, regime, confidence)
            # ── LLM Regime Change Analysis (non-blocking) ──
            if self._llm:
                old_regime_val = self._last_regime
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(
                            self._llm_analyze_regime_change(old_regime_val, regime, indicators)
                        )
                except Exception:
                    pass  # Don't let LLM errors break the engine
        self._last_regime = regime

        # 6. RSI threshold crossing (30/70)
        self._check_rsi_crossing(indicators.get("rsi"))

        # 7. ADX threshold crossing (25)
        self._check_adx_crossing(indicators.get("adx"))

        # 8. Periodic summary (every 5 minutes if nothing else happened)
        now = time.time()
        if now - self._last_periodic_thought >= PERIODIC_SUMMARY_INTERVAL:
            self._generate_periodic_summary(indicators, regime, symbol, cycle_data)
            self._last_periodic_thought = now

        # ── LLM Market Analysis (every 15 min, non-blocking) ──
        if self._llm:
            market_data = {
                "symbols": cycle_data.get("symbols", [symbol]),
                "symbol_data": {symbol: indicators},
                "regime": regime,
                "adx": indicators.get("adx"),
                "rsi": indicators.get("rsi"),
                "balance": cycle_data.get("account", {}).get("balance", 0),
                "open_positions": len(cycle_data.get("positions", [])),
                "daily_pnl": 0,  # TODO: track daily P&L
            }
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._llm_analyze_market(market_data))
                else:
                    loop.run_until_complete(self._llm_analyze_market(market_data))
            except Exception:
                pass  # Don't let LLM errors break the engine

        # Sync state to Redis for cross-process access
        self._sync_to_redis()

    def process_trade_result(self, trade_data: dict) -> None:
        """
        PURPOSE: Process a completed trade and generate learning insights.

        Called when a trade closes (win or loss). Analyzes the outcome,
        feeds it to the RL learner for Thompson Sampling updates,
        and generates LEARNING thoughts with RL insights for future trades.

        Args:
            trade_data: Dict with keys: strategy, symbol, direction, lots, entry_price,
                       exit_price, profit, net_profit, duration_seconds, regime_at_entry

        CALLED BY: engine/engine.py (when trade closes), event handlers
        """
        self._trade_history.append(trade_data)

        strategy_code = trade_data.get("strategy", "?")
        strategy_name = STRATEGY_NAMES.get(strategy_code, f"Strategy {strategy_code}")
        profit = trade_data.get("profit", 0)
        net_profit = trade_data.get("net_profit", profit)
        direction = trade_data.get("direction", "?")
        symbol = trade_data.get("symbol", "?")
        entry = trade_data.get("entry_price")
        exit_price = trade_data.get("exit_price")
        regime = trade_data.get("regime_at_entry", "unknown")
        session = trade_data.get("session", "UNKNOWN")

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

        # Update Thompson Sampling with trade result
        preset = learner_result.get("preset", "moderate")
        self._learner.parameter_adapter.update(strategy_code, regime, preset, rl_reward)

        # Get updated confidence for this strategy
        confidence_adjustments = self._learner.get_strategy_confidence_adjustments()
        strat_adj = confidence_adjustments.get(strategy_code, {})
        new_confidence = strat_adj.get("adjustment", 0.0)

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
            "cycle_count": 0,
            "thought_count": 0,
            "last_updated": None,
            "rl_distributions": {},
            "exploration_rate": 0.10,
            "total_trades_analyzed": 0,
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
    # LLM Async Helpers (fire-and-forget from sync process_cycle)
    # ════════════════════════════════════════════════════════════════

    async def _llm_analyze_market(self, market_data: Dict) -> None:
        """Fire LLM market analysis and add result as a thought."""
        try:
            insight = await self._llm.analyze_market(market_data)
            if insight:
                self._add_thought(
                    "AI_INSIGHT",
                    insight["content"],
                    confidence=0.8,
                    metadata={"source": "gpt", "type": "market_analysis"},
                )
        except Exception as e:
            logger.debug("llm_market_analysis_failed", error=str(e))

    async def _llm_review_trade(self, trade_data: Dict) -> None:
        """Fire LLM trade review and add result as a thought."""
        try:
            insight = await self._llm.review_trade(trade_data)
            if insight:
                self._add_thought(
                    "AI_INSIGHT",
                    insight["content"],
                    confidence=0.75,
                    metadata={"source": "gpt", "type": "trade_review"},
                )
        except Exception as e:
            logger.debug("llm_trade_review_failed", error=str(e))

    async def _llm_analyze_regime_change(self, old_regime: str, new_regime: str, indicators: Dict) -> None:
        """Fire LLM regime change analysis and add result as a thought."""
        try:
            insight = await self._llm.analyze_regime_change(old_regime, new_regime, indicators)
            if insight:
                self._add_thought(
                    "AI_INSIGHT",
                    insight["content"],
                    confidence=0.7,
                    metadata={"source": "gpt", "type": "regime_analysis"},
                )
        except Exception as e:
            logger.debug("llm_regime_analysis_failed", error=str(e))

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
        thought = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": thought_type,
            "content": content,
            "confidence": round(confidence, 2),
            "metadata": metadata or {},
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
    ) -> None:
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

        self._market_analysis = {
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
            "indicators": indicators.copy() if indicators else {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def _update_strategy_scores(self, regime: Optional[str], indicators: Dict) -> None:
        """
        PURPOSE: Recalculate per-strategy confidence scores, now factoring in
        RL-based confidence adjustments from the learner.

        The frontend expects each score to have: { confidence, reason, status }
        where status is one of: IDLE | WATCHING | WARMING_UP | READY | ACTIVE

        CALLED BY: process_cycle
        """
        # Get RL confidence adjustments from the learner
        rl_adjustments = self._learner.get_strategy_confidence_adjustments()

        for code in ("A", "B", "C", "D"):
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

            self._strategy_scores[code] = {
                "name": STRATEGY_NAMES.get(code, f"Strategy {code}"),
                "confidence": round(confidence, 3),
                "reason": reason,
                "status": status,
                "rl_preset": rl_preset,
                "rl_expected": rl_expected,
            }

    def _generate_candle_thought(
        self,
        indicators: Dict,
        regime: Optional[str],
        confidence: Optional[float],
        symbol: str,
    ) -> None:
        """
        PURPOSE: Generate an ANALYSIS thought on new candle.

        CALLED BY: process_cycle (when new_candle is True)
        """
        rsi_val = indicators.get("rsi")
        adx_val = indicators.get("adx")
        atr_val = indicators.get("atr")
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")

        parts = [f"New candle on {symbol}."]

        # Trend summary
        if ema_20 is not None and ema_50 is not None:
            direction = "bullish" if ema_20 > ema_50 else "bearish" if ema_20 < ema_50 else "flat"
            parts.append(f"Trend {direction} (EMA20: {ema_20}, EMA50: {ema_50}).")

        # RSI note
        if rsi_val is not None:
            if rsi_val <= 30:
                parts.append(f"RSI {rsi_val} — oversold.")
            elif rsi_val >= 70:
                parts.append(f"RSI {rsi_val} — overbought.")
            else:
                parts.append(f"RSI {rsi_val}.")

        # ADX note
        if adx_val is not None:
            strength = "strong" if adx_val >= 25 else "weak"
            parts.append(f"ADX {adx_val} ({strength} trend).")

        # Regime
        if regime:
            conf_pct = round(confidence * 100) if confidence else 0
            parts.append(f"Regime: {regime} ({conf_pct}%).")

        content = " ".join(parts)
        self._add_thought("ANALYSIS", content, confidence=confidence or 0.5, metadata={
            "trigger": "new_candle",
            "indicators": indicators,
        })

    def _generate_signal_thought(self, strategy_code: str, signal: Dict, risk_check: Optional[Dict]) -> None:
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
            f"{strategy_name} ({strategy_code}) generated {direction} signal. "
            f"Entry: {entry}, SL: {sl}, TP: {tp}."
        )

        if risk_check:
            if risk_check.get("approved"):
                content += f" Risk check PASSED (size: {risk_check.get('position_size')} lots, risk score: {risk_check.get('risk_score')})."
            else:
                content += f" Risk check REJECTED: {risk_check.get('reason')}."

        self._add_thought("DECISION", content, confidence=0.7, metadata={
            "strategy": strategy_code,
            "signal": signal,
            "risk_check": risk_check,
        })

    def _generate_trade_thought(self, trade: Dict, risk_check: Optional[Dict]) -> None:
        """
        PURPOSE: Generate a DECISION thought when a trade is executed.

        CALLED BY: process_cycle (when trade is not None)
        """
        strategy_code = trade.get("strategy", "?")
        strategy_name = STRATEGY_NAMES.get(strategy_code, f"Strategy {strategy_code}")
        direction = trade.get("direction", "?")
        lots = trade.get("lots")
        ticket = trade.get("ticket")

        content = (
            f"Trade EXECUTED: {strategy_name} ({strategy_code}) {direction} {lots} lots. "
            f"Ticket #{ticket}."
        )

        self._add_thought("DECISION", content, confidence=0.8, metadata={
            "trigger": "trade_executed",
            "trade": trade,
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
    ) -> None:
        """
        PURPOSE: Generate an ANALYSIS thought on regime change.

        CALLED BY: process_cycle (when regime changes)
        """
        conf_pct = round(confidence * 100) if confidence else 0
        content = (
            f"Regime shift detected: {old_regime} -> {new_regime} ({conf_pct}% confidence). "
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
        })

    def _check_rsi_crossing(self, rsi_val: Optional[float]) -> None:
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

        # Check for zone transition
        if self._last_rsi_zone is not None and current_zone != self._last_rsi_zone:
            if current_zone == "oversold":
                content = f"RSI crossed below 30 ({rsi_val}). Entering oversold territory — mean reversion and volatility harvester setups in play."
                self._add_thought("ANALYSIS", content, confidence=0.65, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "into_oversold",
                })
            elif current_zone == "overbought":
                content = f"RSI crossed above 70 ({rsi_val}). Entering overbought territory — watching for exhaustion and reversal setups."
                self._add_thought("ANALYSIS", content, confidence=0.65, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "into_overbought",
                })
            elif self._last_rsi_zone == "oversold":
                content = f"RSI recovered above 30 ({rsi_val}). Leaving oversold — potential bounce underway."
                self._add_thought("ANALYSIS", content, confidence=0.6, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "out_of_oversold",
                })
            elif self._last_rsi_zone == "overbought":
                content = f"RSI dropped below 70 ({rsi_val}). Leaving overbought — momentum fading."
                self._add_thought("ANALYSIS", content, confidence=0.6, metadata={
                    "trigger": "rsi_crossing",
                    "rsi": rsi_val,
                    "direction": "out_of_overbought",
                })

        self._last_rsi_zone = current_zone

    def _check_adx_crossing(self, adx_val: Optional[float]) -> None:
        """
        PURPOSE: Detect ADX crossing the 25 threshold and generate thoughts.

        CALLED BY: process_cycle
        """
        if adx_val is None:
            return

        current_zone = "trending" if adx_val >= 25 else "weak"

        if self._last_adx_zone is not None and current_zone != self._last_adx_zone:
            if current_zone == "trending":
                content = (
                    f"ADX crossed above 25 ({adx_val}). Trend is strengthening — "
                    f"trend-following strategies should perform well."
                )
            else:
                content = (
                    f"ADX dropped below 25 ({adx_val}). Trend is weakening — "
                    f"mean reversion conditions developing."
                )
            self._add_thought("ANALYSIS", content, confidence=0.6, metadata={
                "trigger": "adx_crossing",
                "adx": adx_val,
                "direction": current_zone,
            })

        self._last_adx_zone = current_zone

    def _generate_periodic_summary(
        self,
        indicators: Dict,
        regime: Optional[str],
        symbol: str,
        cycle_data: dict,
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

        parts = [f"Periodic check on {symbol}."]

        if bid:
            parts.append(f"Price at {bid}.")

        if regime:
            parts.append(f"Regime: {regime}.")

        if rsi_val is not None:
            parts.append(f"RSI: {rsi_val}.")

        if adx_val is not None:
            parts.append(f"ADX: {adx_val}.")

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
            "cycle_count": self._cycle_count,
            "rl_total_trades": self._learner._rl_total_trades,
        })
