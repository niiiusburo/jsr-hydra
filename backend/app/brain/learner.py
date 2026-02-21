"""
PURPOSE: Trade Learning Engine for JSR Hydra Brain with Reinforcement Learning.

BrainLearner tracks strategy performance across market regimes, sessions,
and indicator conditions. It builds an in-memory statistical model of
what works and what doesn't, generating actionable insights that influence
future trading decisions. Uses Thompson Sampling for parameter selection
and RL-based confidence adjustments. Periodically persists state to disk
via memory.py, with separate RL state persistence.

CALLED BY: brain/brain.py — on every trade close, periodic review, and signal evaluation
"""

import json
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from app.brain import memory
from app.brain import patterns
from app.brain.paths import resolve_brain_state_path
from app.config.runtime_settings import runtime_settings
from app.utils.logger import get_logger

logger = get_logger("brain.learner")

# Default constants — kept for documentation and as static fallback values.
# Actual runtime values are read from runtime_settings (Redis-backed) at call-time
# so they can be tuned via the settings API without restarting the process.
MAX_TRADE_HISTORY = 200
MAX_INSIGHTS = 100
MIN_TRADES_FOR_ADJUSTMENT = 5
STREAK_WARNING_THRESHOLD = 3
RL_EXPLORATION_RATE = 0.10

# Win rate thresholds (not yet exposed as runtime settings — kept hardcoded)
STRONG_WIN_RATE = 0.65
WEAK_WIN_RATE = 0.35

# RL-specific thresholds (not yet exposed as runtime settings — kept hardcoded)
RL_OVERRIDE_WIN_RATE = 0.25
RL_OVERRIDE_MIN_TRADES = 5
RL_LOSS_STREAK_OVERRIDE = 4

# RL state persistence path
RL_STATE_PATH = resolve_brain_state_path("rl_state.json")

# Strategy descriptions for insight generation
STRATEGY_NAMES = {
    "A": "Trend Following",
    "B": "Mean Reversion",
    "C": "Session Breakout",
    "D": "Momentum Scalper",
    "E": "Range Scalper (Sideways)",
}
STRATEGY_CODES = tuple(STRATEGY_NAMES.keys())


def _rsi_zone(rsi: Optional[float]) -> str:
    """Classify RSI into a human-readable zone."""
    if rsi is None:
        return "unknown"
    if rsi < 30:
        return "oversold"
    if rsi > 70:
        return "overbought"
    return "neutral"


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division that returns default on zero denominator."""
    if denominator == 0:
        return default
    return numerator / denominator


# ══════════════════════════════════════════════════════════════
# Thompson Sampling Parameter Adapter
# ══════════════════════════════════════════════════════════════


class ParameterAdapter:
    """
    For each (strategy, regime) context, maintain Beta distributions
    over parameter presets: conservative, moderate, aggressive.
    Use Thompson Sampling to select the best preset.

    Thompson Sampling balances exploration and exploitation naturally:
    - Each preset has a Beta(alpha, beta) distribution representing
      our belief about its success rate.
    - On each decision, we sample from each distribution and pick
      the highest sample — this explores uncertain options while
      exploiting known good ones.

    CALLED BY: BrainLearner — on signal evaluation and trade result processing
    """

    def __init__(self):
        self._distributions: dict = {}  # {(strategy, regime): {preset: [alpha, beta]}}

    def _get_dist(self, strategy: str, regime: str) -> dict:
        """Get or initialize Beta distributions for a (strategy, regime) pair."""
        key = (strategy, regime)
        if key not in self._distributions:
            self._distributions[key] = {
                "conservative": [1.0, 1.0],
                "moderate": [2.0, 1.0],  # Slight prior toward moderate
                "aggressive": [1.0, 1.0],
            }
        return self._distributions[key]

    def select_preset(self, strategy: str, regime: str) -> str:
        """
        Use Thompson Sampling to select the best parameter preset.

        Draws a sample from each preset's Beta distribution and returns
        the preset with the highest sample value.

        Args:
            strategy: Strategy code (A, B, C, D, E).
            regime: Current market regime string.

        Returns:
            str: Selected preset name ("conservative", "moderate", or "aggressive").
        """
        dist = self._get_dist(strategy, regime)
        samples = {}
        for preset, (alpha, beta) in dist.items():
            samples[preset] = random.betavariate(alpha, beta)
        return max(samples, key=samples.get)

    def update(self, strategy: str, regime: str, preset: str, reward: float) -> None:
        """
        Update the Beta distribution for a preset based on trade outcome.

        Positive rewards increment alpha (successes), negative rewards
        increment beta (failures). Updates are capped at 2.0 per trade
        to prevent single outlier trades from dominating the distribution.

        Args:
            strategy: Strategy code.
            regime: Market regime at trade entry.
            preset: The parameter preset that was active.
            reward: The calculated RL reward (positive = good, negative = bad).
        """
        dist = self._get_dist(strategy, regime)
        if preset not in dist:
            return
        if reward > 0:
            dist[preset][0] += min(reward, 2.0)  # Cap alpha update
        else:
            dist[preset][1] += min(abs(reward), 2.0)  # Cap beta update

    def get_expected_value(self, strategy: str, regime: str, preset: str) -> float:
        """Return the expected value (alpha / (alpha + beta)) for a specific preset."""
        dist = self._get_dist(strategy, regime)
        if preset not in dist:
            return 0.5
        alpha, beta = dist[preset]
        return alpha / (alpha + beta)

    def get_best_expected(self, strategy: str, regime: str) -> tuple:
        """Return the preset with the highest expected value and its score."""
        dist = self._get_dist(strategy, regime)
        best_preset = None
        best_ev = 0.0
        for preset, (alpha, beta) in dist.items():
            ev = alpha / (alpha + beta)
            if ev > best_ev:
                best_ev = ev
                best_preset = preset
        return best_preset, best_ev

    def get_all_distributions(self) -> dict:
        """
        Return all distributions for brain dashboard display.

        Returns:
            dict: Keyed by "strategy_regime", value is dict of presets
                  with alpha, beta, and expected values.
        """
        result = {}
        for (strat, regime), presets in self._distributions.items():
            result[f"{strat}_{regime}"] = {
                preset: {
                    "alpha": round(a, 3),
                    "beta": round(b, 3),
                    "expected": round(a / (a + b), 3),
                }
                for preset, (a, b) in presets.items()
            }
        return result

    def to_dict(self) -> dict:
        """Serialize distributions to a JSON-safe dict."""
        return {
            f"{strat}|{regime}": presets
            for (strat, regime), presets in self._distributions.items()
        }

    def from_dict(self, data: dict) -> None:
        """Restore distributions from a serialized dict."""
        self._distributions = {}
        for key_str, presets in data.items():
            parts = key_str.split("|", 1)
            if len(parts) == 2:
                strat, regime = parts
                self._distributions[(strat, regime)] = presets


class BrainLearner:
    """
    PURPOSE: Tracks strategy performance and generates actionable learning insights.

    Maintains a rolling window of trade history with full market context
    (regime, session, indicators) and produces statistical insights about
    what strategies work best under which conditions. Enhanced with
    Thompson Sampling for parameter adaptation and RL-based signal overrides.

    CALLED BY:
        - brain/brain.py -> analyze_trade() on each closed trade
        - brain/brain.py -> get_regime_performance() for allocation decisions
        - brain/brain.py -> should_override_signal() before signal execution
        - brain/brain.py -> periodic review cycles

    Attributes:
        _state: The full in-memory learning state dictionary
        parameter_adapter: Thompson Sampling parameter selector
        _rl_total_trades: Total trades analyzed by RL system
        _rl_total_reward: Cumulative RL reward
    """

    def __init__(self):
        """
        PURPOSE: Initialize BrainLearner with empty or restored state.

        Attempts to load previous state from disk via memory.py.
        Falls back to a clean state if no persisted data exists.
        Also loads RL state from separate persistence file.

        CALLED BY: brain/brain.py — on startup
        """
        saved = memory.load_state()
        if saved:
            self._state = saved
            # Backfill hour_stats and dow_stats for states persisted before this feature
            self._state.setdefault("hour_stats", {})
            self._state.setdefault("dow_stats", {})
            # Backfill transition_stats and total_trade_count for states persisted before this feature
            self._state.setdefault("transition_stats", {})
            self._state.setdefault("total_trade_count", 0)
            logger.info(
                "brain_learner_restored",
                trade_count=len(self._state.get("trade_history", [])),
                insight_count=len(self._state.get("insights", [])),
            )
        else:
            self._state = self._empty_state()
            logger.info("brain_learner_initialized", message="Starting fresh")

        # Initialize Thompson Sampling parameter adapter
        self.parameter_adapter = ParameterAdapter()

        # RL tracking counters
        self._rl_total_trades = 0
        self._rl_total_reward = 0.0
        self._rl_exploration_rate = runtime_settings.get("exploration_rate")

        # Regime transition tracking
        self._last_regime_change_time: Optional[str] = None
        self._last_regime_transition: Optional[tuple] = None  # (from_regime, to_regime)

        # Load RL state if it exists
        self._load_rl_state()

    @staticmethod
    def _empty_state() -> dict:
        """Return a clean initial state dictionary."""
        return {
            "trade_history": [],
            "regime_stats": {},
            "session_stats": {},
            "rsi_zone_stats": {},
            "hour_stats": {},
            "dow_stats": {},
            "transition_stats": {},
            "insights": [],
            "confidence_adjustments": {
                code: 0.0 for code in STRATEGY_CODES
            },
            "total_trade_count": 0,
            "current_exploration_rate": runtime_settings.get("exploration_rate"),
        }

    @property
    def state(self) -> dict:
        """
        PURPOSE: Return the full learning state for persistence or inspection.

        Returns:
            dict: The complete brain learning state.

        CALLED BY: brain/brain.py, memory.save_state()
        """
        return self._state

    # ------------------------------------------------------------------ #
    #  RL Reward Calculation
    # ------------------------------------------------------------------ #

    def calculate_reward(self, trade_result: dict) -> float:
        """
        PURPOSE: Calculate RL reward from a completed trade result.

        Uses risk-adjusted return (R-multiple) as the primary signal,
        with bonuses for time efficiency and win consistency.

        Args:
            trade_result: Dict with keys: profit, sl_distance, duration_seconds, won

        Returns:
            float: Calculated reward value. Positive = good trade, negative = bad.

        CALLED BY: analyze_trade(), brain/brain.py process_trade_result()
        """
        profit = trade_result.get("profit", 0)
        sl_distance = trade_result.get("sl_distance", 1.0)
        duration = trade_result.get("duration_seconds", 3600)

        # R-multiple (risk-adjusted return)
        r_multiple = profit / sl_distance if sl_distance > 0 else 0

        # Time efficiency bonus (scalps rewarded)
        time_bonus = 0.1 if duration < 1800 else 0  # Bonus for < 30min trades

        # Win consistency bonus
        win_bonus = 0.2 if profit > 0 else -0.1

        reward = r_multiple + win_bonus + time_bonus

        return round(reward, 4)

    # ------------------------------------------------------------------ #
    #  Core: Analyze a completed trade
    # ------------------------------------------------------------------ #

    def analyze_trade(
        self,
        trade_data: dict,
        regime: str,
        session: str,
        indicators: dict,
    ) -> dict:
        """
        PURPOSE: Analyze a completed trade and extract learning insights.

        Records the trade in history, updates aggregated stats, detects
        patterns, calculates RL reward, updates Thompson Sampling
        distributions, and generates an actionable insight.

        Args:
            trade_data: Dict with keys: strategy, direction, entry_price,
                        exit_price, profit, lots, ticket, won.
            regime: Market regime at trade entry (e.g., "TRENDING_DOWN").
            session: Trading session at entry (e.g., "LONDON").
            indicators: Dict with indicator values at entry: rsi, adx, atr, ema20, ema50.

        Returns:
            dict: {"insight": str, "confidence_adjustment": float, "strategy": str,
                   "rl_reward": float, "preset": str}

        CALLED BY: brain/brain.py — on TRADE_CLOSED event
        """
        strategy = trade_data.get("strategy", "?")
        profit = trade_data.get("profit", 0.0)
        won = trade_data.get("won", profit > 0)
        rsi = indicators.get("rsi")
        adx = indicators.get("adx")
        atr = indicators.get("atr")

        # Build enriched trade record
        record = {
            "strategy": strategy,
            "regime": regime,
            "session": session,
            "rsi": rsi,
            "adx": adx,
            "atr": atr,
            "profit": profit,
            "won": won,
            "direction": trade_data.get("direction"),
            "entry_price": trade_data.get("entry_price"),
            "exit_price": trade_data.get("exit_price"),
            "ticket": trade_data.get("ticket"),
            "sl_distance": trade_data.get("sl_distance", 1.0),
            "duration_seconds": trade_data.get("duration_seconds", 3600),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add to history (rolling window — size controlled by runtime setting)
        _max_trade_history = runtime_settings.get("max_trade_history")
        self._state["trade_history"].append(record)
        if len(self._state["trade_history"]) > _max_trade_history:
            self._state["trade_history"] = self._state["trade_history"][-_max_trade_history:]

        # Update aggregated stats
        self._update_regime_stats(strategy, regime, profit, won)
        self._update_session_stats(strategy, session, profit, won)
        self._update_rsi_zone_stats(strategy, rsi, profit, won)
        self._update_hour_stats(record)
        self._update_dow_stats(record)

        # Update transition stats (if within 60 min of a regime change)
        self._update_transition_stats(record)

        # Increment total trade count and apply exploration decay
        self._state["total_trade_count"] = self._state.get("total_trade_count", 0) + 1
        self._apply_exploration_decay()

        # Calculate RL reward
        rl_reward = self.calculate_reward(trade_data)
        self._rl_total_trades += 1
        self._rl_total_reward += rl_reward

        # Get current preset and update Thompson Sampling
        preset = self.parameter_adapter.select_preset(strategy, regime)
        self.parameter_adapter.update(strategy, regime, preset, rl_reward)

        # Recalculate confidence adjustments (now RL-enhanced)
        self._recalculate_confidence_adjustments()

        # Generate insight
        insight = self._generate_trade_insight(strategy, regime, session, rsi, adx, profit, won)
        insight["rl_reward"] = rl_reward
        insight["preset"] = preset

        # Store insight
        insight_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": insight["insight"],
            "confidence": abs(insight["confidence_adjustment"]),
            "strategy": strategy,
            "type": "TRADE_ANALYSIS",
            "rl_reward": rl_reward,
        }
        self._state["insights"].append(insight_record)
        if len(self._state["insights"]) > MAX_INSIGHTS:
            self._state["insights"] = self._state["insights"][-MAX_INSIGHTS:]

        # Persist RL state
        self._save_rl_state()

        logger.info(
            "trade_analyzed",
            strategy=strategy,
            regime=regime,
            session=session,
            profit=profit,
            won=won,
            rl_reward=rl_reward,
            preset=preset,
            confidence_adjustment=insight["confidence_adjustment"],
        )

        return insight

    # ------------------------------------------------------------------ #
    #  Aggregated stats updates
    # ------------------------------------------------------------------ #

    def _update_regime_stats(self, strategy: str, regime: str, profit: float, won: bool) -> None:
        """Update per-strategy per-regime aggregated stats."""
        stats = self._state.setdefault("regime_stats", {})
        strat_stats = stats.setdefault(strategy, {})
        regime_bucket = strat_stats.setdefault(regime, {"wins": 0, "losses": 0, "total_profit": 0.0})

        if won:
            regime_bucket["wins"] += 1
        else:
            regime_bucket["losses"] += 1
        regime_bucket["total_profit"] += profit

    def _update_session_stats(self, strategy: str, session: str, profit: float, won: bool) -> None:
        """Update per-strategy per-session aggregated stats."""
        stats = self._state.setdefault("session_stats", {})
        strat_stats = stats.setdefault(strategy, {})
        session_bucket = strat_stats.setdefault(session, {"wins": 0, "losses": 0, "total_profit": 0.0})

        if won:
            session_bucket["wins"] += 1
        else:
            session_bucket["losses"] += 1
        session_bucket["total_profit"] += profit

    def _update_rsi_zone_stats(self, strategy: str, rsi: Optional[float], profit: float, won: bool) -> None:
        """Update per-strategy per-RSI-zone aggregated stats."""
        zone = _rsi_zone(rsi)
        stats = self._state.setdefault("rsi_zone_stats", {})
        strat_stats = stats.setdefault(strategy, {})
        zone_bucket = strat_stats.setdefault(zone, {"wins": 0, "losses": 0, "total_profit": 0.0})

        if won:
            zone_bucket["wins"] += 1
        else:
            zone_bucket["losses"] += 1
        zone_bucket["total_profit"] += profit

    def _update_hour_stats(self, trade_record: dict) -> None:
        """
        Update per-strategy per-symbol per-hour aggregated stats.

        Extracts the UTC hour (0-23) from the trade's closed_at or opened_at
        timestamp, falling back to the record's own timestamp field.

        Args:
            trade_record: Enriched trade dict with strategy, won, profit, and
                          optionally closed_at / opened_at / timestamp fields.
        """
        strategy = trade_record.get("strategy", "?")
        symbol = trade_record.get("symbol", "UNKNOWN")
        won = trade_record.get("won", False)
        profit = trade_record.get("profit", 0.0)

        # Determine the hour from the best available timestamp field
        hour: Optional[int] = None
        for ts_key in ("closed_at", "opened_at", "timestamp"):
            raw_ts = trade_record.get(ts_key)
            if raw_ts:
                try:
                    dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    hour = dt.hour
                    break
                except (ValueError, TypeError):
                    continue

        if hour is None:
            # Last resort: use current UTC hour
            hour = datetime.now(timezone.utc).hour

        stats = self._state.setdefault("hour_stats", {})
        strat_stats = stats.setdefault(strategy, {})
        symbol_stats = strat_stats.setdefault(symbol, {})
        bucket = symbol_stats.setdefault(
            str(hour),
            {"wins": 0, "losses": 0, "total": 0, "profit": 0.0},
        )

        bucket["total"] += 1
        bucket["profit"] += profit
        if won:
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1

    def _update_dow_stats(self, trade_record: dict) -> None:
        """
        Update per-strategy per-symbol per-day-of-week aggregated stats.

        Extracts the UTC weekday (0=Monday … 6=Sunday) from the trade's
        closed_at or opened_at timestamp, falling back to the record's own
        timestamp field.

        Args:
            trade_record: Enriched trade dict with strategy, won, profit, and
                          optionally closed_at / opened_at / timestamp fields.
        """
        strategy = trade_record.get("strategy", "?")
        symbol = trade_record.get("symbol", "UNKNOWN")
        won = trade_record.get("won", False)
        profit = trade_record.get("profit", 0.0)

        # Determine the day-of-week from the best available timestamp field
        dow: Optional[int] = None
        for ts_key in ("closed_at", "opened_at", "timestamp"):
            raw_ts = trade_record.get(ts_key)
            if raw_ts:
                try:
                    dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dow = dt.weekday()  # 0=Monday, 6=Sunday
                    break
                except (ValueError, TypeError):
                    continue

        if dow is None:
            dow = datetime.now(timezone.utc).weekday()

        stats = self._state.setdefault("dow_stats", {})
        strat_stats = stats.setdefault(strategy, {})
        symbol_stats = strat_stats.setdefault(symbol, {})
        bucket = symbol_stats.setdefault(
            str(dow),
            {"wins": 0, "losses": 0, "total": 0, "profit": 0.0},
        )

        bucket["total"] += 1
        bucket["profit"] += profit
        if won:
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1

    # ------------------------------------------------------------------ #
    #  Regime Transition Tracking
    # ------------------------------------------------------------------ #

    def notify_regime_change(self, old_regime: str, new_regime: str) -> None:
        """
        PURPOSE: Record a regime transition event with timestamp.

        Called by brain.py whenever a regime change is detected for the
        primary symbol. Stores the transition time and pair for later
        use in transition-aware performance analysis.

        Args:
            old_regime: The previous market regime string.
            new_regime: The new market regime string.

        CALLED BY: brain/brain.py — when regime change is detected
        """
        now_str = datetime.now(timezone.utc).isoformat()
        self._last_regime_change_time = now_str
        self._last_regime_transition = (old_regime, new_regime)
        logger.info(
            "regime_transition_recorded",
            from_regime=old_regime,
            to_regime=new_regime,
            timestamp=now_str,
        )

    def _update_transition_stats(self, trade_record: dict) -> None:
        """
        PURPOSE: Record trade outcome against the last regime transition if within 60 minutes.

        If the trade was executed within 60 minutes of the last regime change,
        the outcome is attributed to the transition context. This allows the
        learner to assess how strategies perform immediately after regime shifts.

        Args:
            trade_record: Enriched trade dict with strategy, won, profit, and timestamp.

        CALLED BY: analyze_trade() — after updating aggregated stats
        """
        if self._last_regime_change_time is None or self._last_regime_transition is None:
            return

        # Parse the regime change time
        try:
            change_dt = datetime.fromisoformat(
                self._last_regime_change_time.replace("Z", "+00:00")
            )
            if change_dt.tzinfo is None:
                change_dt = change_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return

        # Parse the trade timestamp
        raw_ts = trade_record.get("timestamp")
        if not raw_ts:
            return
        try:
            trade_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            if trade_dt.tzinfo is None:
                trade_dt = trade_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return

        # Only track if within 60 minutes of the regime change
        elapsed_seconds = (trade_dt - change_dt).total_seconds()
        if elapsed_seconds < 0 or elapsed_seconds > 3600:
            return

        from_regime, to_regime = self._last_regime_transition
        transition_key = f"{from_regime}->{to_regime}"
        strategy = trade_record.get("strategy", "?")
        won = trade_record.get("won", False)
        profit = trade_record.get("profit", 0.0)

        transition_stats = self._state.setdefault("transition_stats", {})
        transition_bucket = transition_stats.setdefault(transition_key, {})
        strat_bucket = transition_bucket.setdefault(
            strategy,
            {"wins": 0, "losses": 0, "total": 0, "profit": 0.0},
        )

        strat_bucket["total"] += 1
        strat_bucket["profit"] += profit
        if won:
            strat_bucket["wins"] += 1
        else:
            strat_bucket["losses"] += 1

        logger.debug(
            "transition_stat_updated",
            transition=transition_key,
            strategy=strategy,
            won=won,
            profit=profit,
        )

    def get_transition_performance(self) -> dict:
        """
        PURPOSE: Return transition statistics for API/dashboard consumption.

        Returns the full transition_stats dict, enriched with computed win_rate
        and avg_profit per (transition, strategy) pair.

        Returns:
            dict: {
                "transition_stats": {
                    "RANGING->TRENDING_UP": {
                        "A": {wins, losses, total, profit, win_rate, avg_profit}
                    }
                },
                "last_regime_change_time": str or None,
                "last_regime_transition": [from, to] or None,
                "within_transition_window": bool,
            }

        CALLED BY: API route GET /api/brain/transition-performance
        """
        raw_stats = self._state.get("transition_stats", {})
        enriched: dict = {}

        for transition_key, strategies in raw_stats.items():
            enriched[transition_key] = {}
            for strategy, data in strategies.items():
                total = data.get("total", 0)
                wins = data.get("wins", 0)
                profit = data.get("profit", 0.0)
                enriched[transition_key][strategy] = {
                    "wins": wins,
                    "losses": data.get("losses", 0),
                    "total": total,
                    "profit": round(profit, 2),
                    "win_rate": round(_safe_div(wins, total), 3),
                    "avg_profit": round(_safe_div(profit, total), 2),
                }

        # Determine if we are currently within the 60-minute transition window
        within_window = False
        if self._last_regime_change_time is not None:
            try:
                change_dt = datetime.fromisoformat(
                    self._last_regime_change_time.replace("Z", "+00:00")
                )
                if change_dt.tzinfo is None:
                    change_dt = change_dt.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - change_dt).total_seconds()
                within_window = 0 <= elapsed <= 3600
            except (ValueError, TypeError):
                pass

        last_transition = None
        if self._last_regime_transition is not None:
            last_transition = list(self._last_regime_transition)

        return {
            "transition_stats": enriched,
            "last_regime_change_time": self._last_regime_change_time,
            "last_regime_transition": last_transition,
            "within_transition_window": within_window,
        }

    # ------------------------------------------------------------------ #
    #  Exploration Decay
    # ------------------------------------------------------------------ #

    def _apply_exploration_decay(self) -> None:
        """Gradually reduce exploration rate as the system gains experience."""
        # Check if exploration decay is enabled (from runtime settings or hardcoded default)
        # Try to import runtime_settings, fall back to defaults if not available
        try:
            from app.config.runtime_settings import runtime_settings as _rs
            decay_enabled = _rs.get("exploration_decay_enabled")
            decay_after = _rs.get("exploration_decay_after_trades")
            decay_target = _rs.get("exploration_decay_target")
        except ImportError:
            decay_enabled = False
            decay_after = 500
            decay_target = 0.02

        if not decay_enabled:
            return

        total_trades = self._state.get("total_trade_count", 0)
        if total_trades < decay_after:
            return

        import math
        initial_rate = 0.10  # Starting exploration rate
        decay_constant = 300  # How fast to decay
        trades_since = total_trades - decay_after

        new_rate = decay_target + (initial_rate - decay_target) * math.exp(-trades_since / decay_constant)

        # Store the decayed rate
        self._state["current_exploration_rate"] = round(new_rate, 4)

        logger.info("exploration_decay", total_trades=total_trades, new_rate=round(new_rate, 4))

    # ------------------------------------------------------------------ #
    #  Insight generation
    # ------------------------------------------------------------------ #

    def _generate_trade_insight(
        self,
        strategy: str,
        regime: str,
        session: str,
        rsi: Optional[float],
        adx: Optional[float],
        profit: float,
        won: bool,
    ) -> dict:
        """Generate an actionable insight from a single trade result."""
        strat_name = STRATEGY_NAMES.get(strategy, f"Strategy {strategy}")
        outcome = "won" if won else "lost"
        rsi_str = f" with RSI {rsi:.0f}" if rsi is not None else ""
        adx_str = f" (ADX {adx:.0f})" if adx is not None else ""

        # Base insight text
        insight_text = (
            f"Strategy {strategy} {outcome} in {regime} during {session}{rsi_str}{adx_str}. "
        )

        # Contextual explanation
        adjustment = 0.0

        if not won:
            # Loss analysis
            if strategy == "B" and regime in ("TRENDING_UP", "TRENDING_DOWN"):
                insight_text += "Mean reversion underperforms in strong trends."
                adjustment = -0.1
            elif strategy == "A" and regime == "RANGING":
                insight_text += "Trend following struggles in ranging conditions."
                adjustment = -0.1
            elif strategy == "C" and regime == "QUIET":
                insight_text += "Breakout strategies fail in low-volatility environments."
                adjustment = -0.08
            elif adx is not None and adx < 20:
                insight_text += f"Weak trend strength (ADX {adx:.0f}) didn't support the setup."
                adjustment = -0.05
            elif rsi is not None and rsi < 25:
                insight_text += "Deeply oversold RSI didn't produce the expected reversal."
                adjustment = -0.05
            else:
                insight_text += f"${abs(profit):.2f} loss recorded. Monitoring for pattern."
                adjustment = -0.03
        else:
            # Win analysis
            if strategy == "A" and regime in ("TRENDING_UP", "TRENDING_DOWN"):
                insight_text += "Trend following shines in directional markets."
                adjustment = 0.05
            elif strategy == "B" and regime == "RANGING":
                insight_text += "Mean reversion works well in range-bound conditions."
                adjustment = 0.05
            elif strategy == "D" and rsi is not None and (rsi < 30 or rsi > 70):
                insight_text += "Volatility harvesting at RSI extremes paid off."
                adjustment = 0.05
            else:
                insight_text += f"+${profit:.2f} profit. Reinforcing confidence."
                adjustment = 0.03

        # Factor in streaks
        _streak_threshold = runtime_settings.get("streak_warning_threshold")
        streaks = patterns.detect_streaks(self._state["trade_history"])
        strat_streak = streaks.get(strategy, {})
        if strat_streak.get("type") == "loss" and strat_streak.get("current_streak", 0) >= _streak_threshold:
            streak_len = strat_streak["current_streak"]
            insight_text += f" WARNING: {streak_len} consecutive losses for Strategy {strategy}."
            adjustment = min(adjustment, -0.1)
        elif strat_streak.get("type") == "win" and strat_streak.get("current_streak", 0) >= _streak_threshold:
            streak_len = strat_streak["current_streak"]
            insight_text += f" Hot streak: {streak_len} wins in a row for Strategy {strategy}."
            adjustment = max(adjustment, 0.05)

        return {
            "insight": insight_text,
            "confidence_adjustment": round(adjustment, 3),
            "strategy": strategy,
        }

    # ------------------------------------------------------------------ #
    #  Performance queries
    # ------------------------------------------------------------------ #

    def get_regime_performance(self) -> dict:
        """
        PURPOSE: Return the full performance matrix by strategy and regime.

        Returns a nested dict: {strategy: {regime: {wins, losses, avg_profit, win_rate, total_profit}}}

        Returns:
            dict: Performance matrix.

        CALLED BY: brain/brain.py, API endpoints
        """
        result = {}
        regime_stats = self._state.get("regime_stats", {})

        for strategy, regimes in regime_stats.items():
            result[strategy] = {}
            for regime, data in regimes.items():
                wins = data.get("wins", 0)
                losses = data.get("losses", 0)
                total = wins + losses
                total_profit = data.get("total_profit", 0.0)

                result[strategy][regime] = {
                    "wins": wins,
                    "losses": losses,
                    "total_trades": total,
                    "total_profit": round(total_profit, 2),
                    "avg_profit": round(_safe_div(total_profit, total), 2),
                    "win_rate": round(_safe_div(wins, total), 3),
                }

        return result

    def get_session_performance(self) -> dict:
        """
        PURPOSE: Return performance matrix by strategy and session.

        Returns:
            dict: {strategy: {session: {wins, losses, avg_profit, win_rate}}}

        CALLED BY: brain/brain.py, API endpoints
        """
        result = {}
        session_stats = self._state.get("session_stats", {})

        for strategy, sessions in session_stats.items():
            result[strategy] = {}
            for session, data in sessions.items():
                wins = data.get("wins", 0)
                losses = data.get("losses", 0)
                total = wins + losses
                total_profit = data.get("total_profit", 0.0)

                result[strategy][session] = {
                    "wins": wins,
                    "losses": losses,
                    "total_trades": total,
                    "total_profit": round(total_profit, 2),
                    "avg_profit": round(_safe_div(total_profit, total), 2),
                    "win_rate": round(_safe_div(wins, total), 3),
                }

        return result

    def get_rsi_zone_performance(self) -> dict:
        """
        PURPOSE: Return performance matrix by strategy and RSI zone.

        Returns:
            dict: {strategy: {rsi_zone: {wins, losses, avg_profit, win_rate}}}

        CALLED BY: brain/brain.py, API endpoints
        """
        result = {}
        rsi_stats = self._state.get("rsi_zone_stats", {})

        for strategy, zones in rsi_stats.items():
            result[strategy] = {}
            for zone, data in zones.items():
                wins = data.get("wins", 0)
                losses = data.get("losses", 0)
                total = wins + losses
                total_profit = data.get("total_profit", 0.0)

                result[strategy][zone] = {
                    "wins": wins,
                    "losses": losses,
                    "total_trades": total,
                    "total_profit": round(total_profit, 2),
                    "avg_profit": round(_safe_div(total_profit, total), 2),
                    "win_rate": round(_safe_div(wins, total), 3),
                }

        return result

    def get_hour_performance(self) -> dict:
        """
        PURPOSE: Return performance matrix by strategy, symbol, and UTC hour.

        Returns a nested dict:
        {strategy: {symbol: {hour_str: {wins, losses, total, profit, win_rate, avg_profit}}}}

        Returns:
            dict: Hour-of-day performance matrix.

        CALLED BY: API endpoints, frontend hour-performance panel
        """
        result = {}
        hour_stats = self._state.get("hour_stats", {})

        for strategy, symbols in hour_stats.items():
            result[strategy] = {}
            for symbol, hours in symbols.items():
                result[strategy][symbol] = {}
                for hour_str, data in hours.items():
                    wins = data.get("wins", 0)
                    losses = data.get("losses", 0)
                    total = data.get("total", wins + losses)
                    profit = data.get("profit", 0.0)

                    result[strategy][symbol][hour_str] = {
                        "wins": wins,
                        "losses": losses,
                        "total": total,
                        "profit": round(profit, 2),
                        "win_rate": round(_safe_div(wins, total), 3),
                        "avg_profit": round(_safe_div(profit, total), 2),
                    }

        return result

    def get_dow_performance(self) -> dict:
        """
        PURPOSE: Return performance matrix by strategy, symbol, and day of week.

        Returns a nested dict:
        {strategy: {symbol: {dow_str: {wins, losses, total, profit, win_rate, avg_profit}}}}

        Day-of-week keys: "0"=Monday … "6"=Sunday.

        Returns:
            dict: Day-of-week performance matrix.

        CALLED BY: API endpoints, frontend dow-performance panel
        """
        result = {}
        dow_stats = self._state.get("dow_stats", {})

        for strategy, symbols in dow_stats.items():
            result[strategy] = {}
            for symbol, days in symbols.items():
                result[strategy][symbol] = {}
                for dow_str, data in days.items():
                    wins = data.get("wins", 0)
                    losses = data.get("losses", 0)
                    total = data.get("total", wins + losses)
                    profit = data.get("profit", 0.0)

                    result[strategy][symbol][dow_str] = {
                        "wins": wins,
                        "losses": losses,
                        "total": total,
                        "profit": round(profit, 2),
                        "win_rate": round(_safe_div(wins, total), 3),
                        "avg_profit": round(_safe_div(profit, total), 2),
                    }

        return result

    # ------------------------------------------------------------------ #
    #  Learned insights
    # ------------------------------------------------------------------ #

    def get_learned_insights(self, limit: int = 20) -> list[str]:
        """
        PURPOSE: Return a list of learned patterns as human-readable strings.

        Combines regime bias, time patterns, indicator patterns, and
        recent trade insights into a consolidated list.

        Args:
            limit: Maximum number of insights to return.

        Returns:
            list[str]: Human-readable insight strings, most recent first.

        CALLED BY: brain/brain.py, API endpoints, prompts.py
        """
        history = self._state.get("trade_history", [])

        all_insights = []

        # Pattern-based insights
        all_insights.extend(patterns.detect_regime_bias(history))
        all_insights.extend(patterns.detect_time_patterns(history))
        all_insights.extend(patterns.detect_indicator_patterns(history))

        # Hour-of-day and day-of-week pattern insights
        current_dt = datetime.now(timezone.utc)
        all_insights.extend(
            patterns.detect_hour_patterns(
                self._state.get("hour_stats", {}),
                current_dt.hour,
            )
        )
        all_insights.extend(
            patterns.detect_dow_patterns(
                self._state.get("dow_stats", {}),
                current_dt.weekday(),
            )
        )

        # Streak insights
        _streak_threshold = runtime_settings.get("streak_warning_threshold")
        streaks = patterns.detect_streaks(history)
        for strat, streak_data in streaks.items():
            streak_len = streak_data.get("current_streak", 0)
            streak_type = streak_data.get("type", "none")
            if streak_len >= _streak_threshold:
                if streak_type == "loss":
                    all_insights.append(
                        f"Strategy {strat} is on a {streak_len}-trade losing streak. "
                        "Consider pausing or reducing allocation."
                    )
                elif streak_type == "win":
                    all_insights.append(
                        f"Strategy {strat} is hot with {streak_len} consecutive wins. "
                        "Confidence elevated."
                    )

        # RL Thompson Sampling insights
        ts_distributions = self.parameter_adapter.get_all_distributions()
        for context_key, presets in ts_distributions.items():
            best_preset = max(presets, key=lambda p: presets[p]["expected"])
            best_ev = presets[best_preset]["expected"]
            if best_ev >= 0.65:
                all_insights.append(
                    f"RL: {context_key} strongly favors '{best_preset}' preset "
                    f"(expected value: {best_ev:.0%})"
                )
            elif best_ev <= 0.35:
                all_insights.append(
                    f"RL: {context_key} shows poor performance across all presets "
                    f"(best EV: {best_ev:.0%}). Consider regime avoidance."
                )

        # Transition-based insights
        current_transition: Optional[str] = None
        if self._last_regime_transition is not None:
            _from, _to = self._last_regime_transition
            current_transition = f"{_from}->{_to}"
        transition_insights = patterns.detect_transition_patterns(
            self._state.get("transition_stats", {}),
            current_transition,
        )
        all_insights.extend(transition_insights)

        # Recent trade-level insights (most recent first)
        stored_insights = self._state.get("insights", [])
        recent_texts = [i["text"] for i in reversed(stored_insights)]
        all_insights.extend(recent_texts)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for insight in all_insights:
            if insight not in seen:
                seen.add(insight)
                unique.append(insight)

        return unique[:limit]

    # ------------------------------------------------------------------ #
    #  Confidence adjustments (RL-enhanced)
    # ------------------------------------------------------------------ #

    def _recalculate_confidence_adjustments(self) -> None:
        """
        Recalculate confidence adjustments based on recent performance
        and Thompson Sampling expected values.
        """
        history = self._state.get("trade_history", [])
        adjustments = {
            code: 0.0 for code in STRATEGY_CODES
        }

        if not history:
            self._state["confidence_adjustments"] = adjustments
            return

        # Use the most recent N trades per strategy (lookback from runtime settings)
        _lookback = runtime_settings.get("confidence_lookback")
        _min_trades = runtime_settings.get("min_trades_for_adjustment")
        _streak_threshold = runtime_settings.get("streak_warning_threshold")
        recent_by_strategy = defaultdict(list)
        for trade in reversed(history):
            strat = trade.get("strategy", "?")
            if strat in adjustments and len(recent_by_strategy[strat]) < _lookback:
                recent_by_strategy[strat].append(trade)

        for strat in adjustments:
            trades = recent_by_strategy.get(strat, [])
            if len(trades) < _min_trades:
                continue

            wins = sum(1 for t in trades if t.get("won", False))
            total = len(trades)
            win_rate = _safe_div(wins, total)

            # Base adjustment from win rate deviation from 50%
            adj = (win_rate - 0.5) * 0.4  # Scale: 70% WR -> +0.08, 30% WR -> -0.08

            # Streak modifier
            streaks = patterns.detect_streaks(history)
            streak_data = streaks.get(strat, {})
            streak_len = streak_data.get("current_streak", 0)
            streak_type = streak_data.get("type", "none")

            if streak_type == "loss" and streak_len >= _streak_threshold:
                adj -= 0.05 * min(streak_len - 2, 3)  # Progressive penalty
            elif streak_type == "win" and streak_len >= _streak_threshold:
                adj += 0.02 * min(streak_len - 2, 3)  # Modest boost

            # RL Thompson Sampling factor: use expected value from best preset
            # to further adjust confidence based on learned performance
            current_regime = self._get_current_regime()
            if current_regime:
                _, best_ev = self.parameter_adapter.get_best_expected(strat, current_regime)
                # Scale TS expected value to adjustment: 0.5 EV = neutral, >0.5 = boost, <0.5 = penalty
                ts_adj = (best_ev - 0.5) * 0.2
                adj += ts_adj

            # Clamp to [-0.3, +0.3]
            adjustments[strat] = round(max(-0.3, min(0.3, adj)), 3)

        self._state["confidence_adjustments"] = adjustments

    def _get_current_regime(self) -> Optional[str]:
        """Get the regime from the most recent trade, or None if no trades."""
        history = self._state.get("trade_history", [])
        if history:
            return history[-1].get("regime")
        return None

    def get_strategy_confidence_adjustments(self) -> dict:
        """
        PURPOSE: Return recommended confidence adjustments per strategy.

        Based on recent win rates, streaks, regime performance, and Thompson
        Sampling expected values, suggests how much to adjust each strategy's
        confidence score.

        Returns:
            dict: {strategy_code: {"adjustment": float, "reason": str, "rl_preset": str, "rl_expected": float}}

        CALLED BY: brain/brain.py — meta-controller, signal evaluation
        """
        adjustments = self._state.get("confidence_adjustments", {})
        history = self._state.get("trade_history", [])
        streaks = patterns.detect_streaks(history)
        current_regime = self._get_current_regime() or "UNKNOWN"
        _min_trades = runtime_settings.get("min_trades_for_adjustment")
        _streak_threshold = runtime_settings.get("streak_warning_threshold")

        result = {}

        for strat in STRATEGY_CODES:
            adj = adjustments.get(strat, 0.0)
            streak_data = streaks.get(strat, {})

            # Build reason
            reasons = []

            # Recent performance in current regime
            regime_trades = [
                t for t in history[-50:]
                if t.get("strategy") == strat and t.get("regime") == current_regime
            ]
            if regime_trades:
                wins = sum(1 for t in regime_trades if t.get("won", False))
                total = len(regime_trades)
                rate = _safe_div(wins, total)

                if rate > 0.60 and total >= _min_trades:
                    reasons.append(f"strong in {current_regime} ({wins}/{total} wins)")
                    adj = max(adj, adj + 0.2)  # Boost for >60% win rate in regime
                elif rate < 0.35 and total >= _min_trades:
                    reasons.append(f"weak in {current_regime} ({wins}/{total} wins)")
                    adj = min(adj, adj - 0.2)  # Reduce for <35% win rate in regime
                else:
                    reasons.append(f"moderate in {current_regime} ({wins}/{total} wins)")
            else:
                reasons.append(f"no trades in {current_regime} yet (exploring)")

            # Recent overall performance
            recent = [t for t in history[-30:] if t.get("strategy") == strat]
            if recent:
                wins = sum(1 for t in recent if t.get("won", False))
                total = len(recent)
                rate = _safe_div(wins, total)

                if rate >= STRONG_WIN_RATE:
                    reasons.append(f"strong overall ({wins}/{total} wins)")
                elif rate <= WEAK_WIN_RATE:
                    reasons.append(f"poor overall ({wins}/{total} wins)")

            # Streak
            streak_len = streak_data.get("current_streak", 0)
            streak_type = streak_data.get("type", "none")
            if streak_len >= _streak_threshold:
                if streak_type == "loss":
                    reasons.append(f"{streak_len}-trade losing streak")
                else:
                    reasons.append(f"{streak_len}-trade winning streak")

            # Hour-of-day awareness: penalise strategies with <30% win rate in current hour
            current_dt = datetime.now(timezone.utc)
            hour_key = str(current_dt.hour)
            dow_key = str(current_dt.weekday())
            hour_stats = self._state.get("hour_stats", {})
            dow_stats = self._state.get("dow_stats", {})

            # Aggregate across all symbols for the current strategy + hour
            hour_wins = 0
            hour_total = 0
            for sym_data in hour_stats.get(strat, {}).values():
                bucket = sym_data.get(hour_key, {})
                hour_wins += bucket.get("wins", 0)
                hour_total += bucket.get("total", 0)

            if hour_total >= 8:
                hour_rate = _safe_div(hour_wins, hour_total)
                if hour_rate < 0.30:
                    adj -= 0.1
                    reasons.append(
                        f"poor at hour {current_dt.hour:02d}:00 UTC "
                        f"({hour_wins}/{hour_total} wins, {hour_rate:.0%})"
                    )

            # Aggregate across all symbols for the current strategy + day-of-week
            dow_wins = 0
            dow_total = 0
            for sym_data in dow_stats.get(strat, {}).values():
                bucket = sym_data.get(dow_key, {})
                dow_wins += bucket.get("wins", 0)
                dow_total += bucket.get("total", 0)

            if dow_total >= 8:
                dow_rate = _safe_div(dow_wins, dow_total)
                _dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                dow_name = _dow_names[current_dt.weekday()]
                if dow_rate < 0.30:
                    adj -= 0.1
                    reasons.append(
                        f"poor on {dow_name} ({dow_wins}/{dow_total} wins, {dow_rate:.0%})"
                    )

            # Transition-period penalty: check if currently within 60 min of a regime change
            # and if historical data shows <35% win rate for this strategy in this transition
            if (
                self._last_regime_change_time is not None
                and self._last_regime_transition is not None
            ):
                try:
                    _change_dt = datetime.fromisoformat(
                        self._last_regime_change_time.replace("Z", "+00:00")
                    )
                    if _change_dt.tzinfo is None:
                        _change_dt = _change_dt.replace(tzinfo=timezone.utc)
                    _elapsed = (datetime.now(timezone.utc) - _change_dt).total_seconds()
                    if 0 <= _elapsed <= 3600:
                        _from, _to = self._last_regime_transition
                        _tkey = f"{_from}->{_to}"
                        _trans_data = (
                            self._state.get("transition_stats", {})
                            .get(_tkey, {})
                            .get(strat, {})
                        )
                        _trans_total = _trans_data.get("total", 0)
                        _trans_wins = _trans_data.get("wins", 0)
                        if _trans_total >= 5:
                            _trans_rate = _safe_div(_trans_wins, _trans_total)
                            if _trans_rate < 0.35:
                                adj -= 0.15
                                reasons.append(
                                    f"transition penalty: {_trans_wins}/{_trans_total} wins "                                    f"after {_tkey} ({_trans_rate:.0%})"                                )
                except (ValueError, TypeError):
                    pass

            # Thompson Sampling info
            best_preset, best_ev = self.parameter_adapter.get_best_expected(strat, current_regime)
            if best_preset:
                reasons.append(f"RL favors '{best_preset}' (EV: {best_ev:.0%})")

            reason = "; ".join(reasons) if reasons else "insufficient data"

            # Clamp final adjustment
            adj = round(max(-0.3, min(0.3, adj)), 3)

            result[strat] = {
                "adjustment": adj,
                "reason": reason.capitalize(),
                "rl_preset": best_preset or "moderate",
                "rl_expected": round(best_ev, 3) if best_preset else 0.5,
            }

        return result

    # ------------------------------------------------------------------ #
    #  Signal override decision (RL-enhanced)
    # ------------------------------------------------------------------ #

    def should_override_signal(
        self,
        strategy_code: str,
        regime: str,
        indicators: dict,
    ) -> tuple[bool, str]:
        """
        PURPOSE: Decide whether to skip a strategy's signal based on learned patterns
        and RL reasoning.

        Checks:
        1. Win rate < 25% in current regime with > 5 trades -> override
        2. Recent streak of 4+ losses -> override
        3. 10% exploration rate -> DON'T override (allow exploration)
        4. RSI zone performance -> override if historically terrible

        Args:
            strategy_code: Strategy code (A, B, C, D, E).
            regime: Current market regime.
            indicators: Current indicator values dict (rsi, adx, etc.).

        Returns:
            tuple[bool, str]: (should_skip, reason)
                should_skip: True if the signal should be skipped.
                reason: Human-readable explanation.

        CALLED BY: brain/brain.py — before executing a signal
        """
        # Exploration override — rate is read from runtime settings at call-time
        _exploration_rate = runtime_settings.get("exploration_rate")
        if random.random() < _exploration_rate:
            return False, "RL exploration: allowing signal despite potential concerns (exploration rate)"

        history = self._state.get("trade_history", [])

        # Filter recent trades for this strategy in this regime
        relevant = [
            t for t in history[-50:]
            if t.get("strategy") == strategy_code and t.get("regime") == regime
        ]

        # Not enough data — don't override
        _min_trades = runtime_settings.get("min_trades_for_adjustment")
        if len(relevant) < _min_trades:
            return False, "Insufficient data to override"

        wins = sum(1 for t in relevant if t.get("won", False))
        total = len(relevant)
        win_rate = _safe_div(wins, total)

        # RL Override: win rate < 25% in current regime with enough trades
        if win_rate < RL_OVERRIDE_WIN_RATE and total >= RL_OVERRIDE_MIN_TRADES:
            return True, (
                f"RL override: Strategy {strategy_code} has {win_rate:.0%} win rate in {regime} "
                f"over {total} trades (below {RL_OVERRIDE_WIN_RATE:.0%} threshold). Signal skipped."
            )

        # RL Override: 0% win rate with any meaningful sample
        if win_rate == 0.0 and total >= 5:
            return True, (
                f"RL override: Strategy {strategy_code} has 0% win rate in {regime} "
                f"over last {total} trades. Skipping signal."
            )

        # Check for severe losing streaks (4+ consecutive losses)
        streaks = patterns.detect_streaks(history)
        streak_data = streaks.get(strategy_code, {})
        if (
            streak_data.get("type") == "loss"
            and streak_data.get("current_streak", 0) >= RL_LOSS_STREAK_OVERRIDE
        ):
            streak_len = streak_data["current_streak"]
            return True, (
                f"RL override: Strategy {strategy_code} is on a "
                f"{streak_len}-trade losing streak (threshold: {RL_LOSS_STREAK_OVERRIDE}). "
                "Signal overridden until streak breaks."
            )

        # Check RSI zone performance
        rsi = indicators.get("rsi")
        if rsi is not None:
            zone = _rsi_zone(rsi)
            zone_stats = (
                self._state.get("rsi_zone_stats", {})
                .get(strategy_code, {})
                .get(zone, {})
            )
            zone_wins = zone_stats.get("wins", 0)
            zone_losses = zone_stats.get("losses", 0)
            zone_total = zone_wins + zone_losses

            if zone_total >= _min_trades:
                zone_rate = _safe_div(zone_wins, zone_total)
                if zone_rate <= 0.15:
                    return True, (
                        f"RL override: Strategy {strategy_code} has {zone_rate:.0%} win rate "
                        f"in {zone} RSI zone. Skipping signal."
                    )

        # Thompson Sampling check: if best expected value is very low, warn but allow
        _, best_ev = self.parameter_adapter.get_best_expected(strategy_code, regime)
        if best_ev < 0.25 and total >= 10:
            return True, (
                f"RL override: Thompson Sampling shows very low expected value ({best_ev:.0%}) "
                f"for {strategy_code} in {regime}. Signal skipped."
            )

        return False, "Signal approved by RL learning engine"

    # ------------------------------------------------------------------ #
    #  RL State Persistence
    # ------------------------------------------------------------------ #

    def _save_rl_state(self) -> bool:
        """
        PURPOSE: Persist RL-specific state (Thompson Sampling distributions,
        counters) to /tmp/jsr_brain_rl_state.json.

        Returns:
            bool: True if save succeeded.

        CALLED BY: analyze_trade() — after each trade
        """
        try:
            rl_state = {
                "parameter_adapter": self.parameter_adapter.to_dict(),
                "rl_total_trades": self._rl_total_trades,
                "rl_total_reward": self._rl_total_reward,
                "rl_exploration_rate": self._rl_exploration_rate,
                "_saved_at": datetime.now(timezone.utc).isoformat(),
            }

            tmp_path = RL_STATE_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(rl_state, f, indent=2, default=str)

            os.replace(tmp_path, RL_STATE_PATH)

            logger.debug(
                "rl_state_saved",
                path=RL_STATE_PATH,
                total_trades=self._rl_total_trades,
            )
            return True

        except Exception as e:
            logger.error("rl_state_save_failed", path=RL_STATE_PATH, error=str(e))
            return False

    def _load_rl_state(self) -> bool:
        """
        PURPOSE: Load RL state from /tmp/jsr_brain_rl_state.json.

        Returns:
            bool: True if load succeeded.

        CALLED BY: __init__() — on startup
        """
        if not os.path.exists(RL_STATE_PATH):
            logger.info("rl_state_not_found", path=RL_STATE_PATH, message="Starting with fresh RL state")
            return False

        try:
            with open(RL_STATE_PATH, "r") as f:
                rl_state = json.load(f)

            # Restore Thompson Sampling distributions
            adapter_data = rl_state.get("parameter_adapter", {})
            if adapter_data:
                self.parameter_adapter.from_dict(adapter_data)

            self._rl_total_trades = rl_state.get("rl_total_trades", 0)
            self._rl_total_reward = rl_state.get("rl_total_reward", 0.0)
            self._rl_exploration_rate = rl_state.get(
                "rl_exploration_rate", runtime_settings.get("exploration_rate")
            )

            saved_at = rl_state.get("_saved_at", "unknown")
            logger.info(
                "rl_state_loaded",
                path=RL_STATE_PATH,
                saved_at=saved_at,
                total_trades=self._rl_total_trades,
                total_reward=round(self._rl_total_reward, 4),
            )
            return True

        except (json.JSONDecodeError, Exception) as e:
            logger.error("rl_state_load_failed", path=RL_STATE_PATH, error=str(e))
            return False

    # ------------------------------------------------------------------ #
    #  RL Stats for Dashboard
    # ------------------------------------------------------------------ #

    def get_rl_stats(self) -> dict:
        """
        PURPOSE: Return comprehensive RL statistics for the brain dashboard.

        Returns:
            dict: {
                "distributions": Thompson Sampling distributions,
                "total_trades_analyzed": int,
                "total_reward": float,
                "avg_reward": float,
                "exploration_rate": float,
                "confidence_adjustments": per-strategy adjustments with reasons,
            }

        CALLED BY: brain/brain.py get_rl_stats(), API endpoint
        """
        return {
            "distributions": self.parameter_adapter.get_all_distributions(),
            "total_trades_analyzed": self._rl_total_trades,
            "total_reward": round(self._rl_total_reward, 4),
            "avg_reward": round(
                _safe_div(self._rl_total_reward, self._rl_total_trades), 4
            ),
            "exploration_rate": self._rl_exploration_rate,
            "confidence_adjustments": self.get_strategy_confidence_adjustments(),
        }

    # ------------------------------------------------------------------ #
    #  Persistence (original memory.py based)
    # ------------------------------------------------------------------ #

    def save(self) -> bool:
        """
        PURPOSE: Persist the current learning state to disk.

        Returns:
            bool: True if save succeeded.

        CALLED BY: brain/brain.py — periodic save (every 5 minutes)
        """
        self._save_rl_state()  # Also save RL state
        return memory.save_state(self._state)

    def get_trade_count(self) -> int:
        """Return total number of trades in history."""
        return len(self._state.get("trade_history", []))

    def get_streaks(self) -> dict:
        """
        PURPOSE: Return current streak data for all strategies.

        Returns:
            dict: {strategy: {current_streak, type, max_win_streak, max_loss_streak}}

        CALLED BY: brain/brain.py, API endpoints
        """
        return patterns.detect_streaks(self._state.get("trade_history", []))

    def get_market_memory(self, current_regime: str) -> str:
        """
        PURPOSE: Get a comprehensive narrative of what the brain has learned.

        Args:
            current_regime: Current market regime string.

        Returns:
            str: Human-readable market memory paragraph.

        CALLED BY: brain/brain.py, brain/prompts.py
        """
        return patterns.generate_market_memory(
            self._state.get("trade_history", []),
            current_regime,
        )
