"""
PURPOSE: Auto-allocation engine that dynamically rebalances capital across strategies.

Combines XP level, recent win rate, profit factor, RL expected values, and streak
performance into a composite "fitness score" per strategy. Normalizes scores to
percentages and smoothly adjusts allocation_pct in the database.

Runs after every N completed trades (configurable). Applies a smoothing cap so
allocations don't swing wildly between rebalances.

CALLED BY:
    - brain/brain.py -> process_trade_result() triggers check after each trade
    - api/routes_brain.py -> /auto-allocation-status endpoint for dashboard
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from app.brain.paths import resolve_brain_state_path
from app.utils.logger import get_logger

logger = get_logger("brain.auto_allocator")

# Persistence path for auto-allocation state
AUTO_ALLOC_STATE_PATH = resolve_brain_state_path("auto_allocation.json")

# How often to rebalance (every N trades across all strategies)
REBALANCE_INTERVAL = 10

# Maximum allocation change per rebalance (percentage points)
MAX_CHANGE_PER_REBALANCE = 5.0

# Minimum allocation floor so no strategy is starved
MIN_ALLOCATION_PCT = 5.0

# Maximum allocation cap per strategy
MAX_ALLOCATION_PCT = 50.0

# Fitness score weights
WEIGHT_XP_LEVEL = 0.20
WEIGHT_WIN_RATE = 0.30
WEIGHT_PROFIT_FACTOR = 0.20
WEIGHT_RL_EXPECTED = 0.20
WEIGHT_STREAK = 0.10

# Strategy codes
STRATEGY_CODES = ("A", "B", "C", "D")


class AutoAllocator:
    """
    Dynamically rebalances capital allocation across strategies based on
    a composite fitness score derived from XP level, win rate, profit factor,
    RL Thompson Sampling expected values, and streak performance.

    CALLED BY:
        - brain.py process_trade_result() after each completed trade
        - routes_brain.py for dashboard status
    """

    def __init__(self):
        self._enabled: bool = True
        self._trades_since_rebalance: int = 0
        self._total_rebalances: int = 0
        self._last_rebalance_time: Optional[str] = None
        self._last_fitness_scores: dict = {}
        self._last_allocations: dict = {}
        self._rebalance_history: list = []  # Keep last 20 rebalance events
        self._load_state()

    # ------------------------------------------------------------------ #
    #  Fitness Score Calculation
    # ------------------------------------------------------------------ #

    def calculate_fitness_scores(
        self,
        xp_data: dict,
        learner_adjustments: dict,
        rl_stats: dict,
    ) -> dict:
        """
        Calculate composite fitness score for each strategy.

        Args:
            xp_data: Dict from StrategyXP.get_all_xp() keyed by strategy code
            learner_adjustments: Dict from BrainLearner.get_strategy_confidence_adjustments()
            rl_stats: Dict from BrainLearner.get_rl_stats()

        Returns:
            dict: {strategy_code: {"score": float, "breakdown": dict}}
        """
        scores = {}
        distributions = rl_stats.get("distributions", {})

        for code in STRATEGY_CODES:
            strategy_xp = xp_data.get(code, {})
            adj = learner_adjustments.get(code, {})

            # 1. XP Level score (0-1): Level 1=0.1, Level 10=1.0
            level = strategy_xp.get("level", 1)
            xp_score = level / 10.0

            # 2. Win rate score (0-1): Direct win rate
            win_rate = strategy_xp.get("win_rate", 0.0)
            win_rate_score = min(1.0, win_rate)  # Already 0-1

            # 3. Profit factor score (0-1): Normalize PF, cap at 3.0
            total_profit = strategy_xp.get("total_profit", 0.0)
            total_trades = strategy_xp.get("total_trades", 0)
            wins = strategy_xp.get("wins", 0)
            losses = strategy_xp.get("losses", 0)

            if losses > 0 and wins > 0:
                # Approximate profit factor from win rate and avg trade
                pf = wins / losses if losses > 0 else 1.0
                pf_score = min(1.0, pf / 3.0)
            elif total_profit > 0:
                pf_score = 0.7  # Profitable but no losses to compute PF
            else:
                pf_score = 0.3  # Default for no data

            # 4. RL expected value score (0-1): Best Thompson Sampling EV
            rl_ev = adj.get("rl_expected", 0.5)
            rl_score = min(1.0, max(0.0, rl_ev))

            # 5. Streak score (0-1): Bonus for win streaks, penalty for loss streaks
            current_streak = strategy_xp.get("current_streak", 0)
            streak_type = strategy_xp.get("current_streak_type", "none")

            if streak_type == "win":
                streak_score = min(1.0, 0.5 + (current_streak * 0.1))
            elif streak_type == "loss":
                streak_score = max(0.0, 0.5 - (current_streak * 0.1))
            else:
                streak_score = 0.5

            # Composite weighted score
            composite = (
                WEIGHT_XP_LEVEL * xp_score
                + WEIGHT_WIN_RATE * win_rate_score
                + WEIGHT_PROFIT_FACTOR * pf_score
                + WEIGHT_RL_EXPECTED * rl_score
                + WEIGHT_STREAK * streak_score
            )

            scores[code] = {
                "score": round(composite, 4),
                "breakdown": {
                    "xp_level": {"value": level, "score": round(xp_score, 3), "weight": WEIGHT_XP_LEVEL},
                    "win_rate": {"value": round(win_rate, 3), "score": round(win_rate_score, 3), "weight": WEIGHT_WIN_RATE},
                    "profit_factor": {"value": round(pf_score * 3, 2), "score": round(pf_score, 3), "weight": WEIGHT_PROFIT_FACTOR},
                    "rl_expected": {"value": round(rl_ev, 3), "score": round(rl_score, 3), "weight": WEIGHT_RL_EXPECTED},
                    "streak": {"value": f"{streak_type}:{current_streak}", "score": round(streak_score, 3), "weight": WEIGHT_STREAK},
                },
                "total_trades": total_trades,
                "total_profit": round(total_profit, 2),
            }

        return scores

    # ------------------------------------------------------------------ #
    #  Allocation Calculation
    # ------------------------------------------------------------------ #

    def calculate_target_allocations(self, fitness_scores: dict) -> dict:
        """
        Convert fitness scores to target allocation percentages.

        Normalizes scores to sum to 100%, applies min/max floors and caps,
        then renormalizes.

        Args:
            fitness_scores: Dict from calculate_fitness_scores()

        Returns:
            dict: {strategy_code: target_allocation_pct}
        """
        # Get raw scores
        raw = {code: data["score"] for code, data in fitness_scores.items()}
        total_score = sum(raw.values())

        if total_score <= 0:
            # Equal distribution if all scores are 0
            equal = 100.0 / len(STRATEGY_CODES)
            return {code: equal for code in STRATEGY_CODES}

        # Normalize to 100%
        target = {
            code: (score / total_score) * 100.0
            for code, score in raw.items()
        }

        # Apply floor and cap
        for code in target:
            target[code] = max(MIN_ALLOCATION_PCT, min(MAX_ALLOCATION_PCT, target[code]))

        # Renormalize after floor/cap to sum to 100%
        clamped_total = sum(target.values())
        if clamped_total > 0:
            target = {
                code: round((pct / clamped_total) * 100.0, 1)
                for code, pct in target.items()
            }

        # Fix rounding to exactly 100%
        diff = 100.0 - sum(target.values())
        if abs(diff) > 0.05:
            # Add/subtract from the highest allocation
            best = max(target, key=target.get)
            target[best] = round(target[best] + diff, 1)

        return target

    def apply_smoothing(
        self,
        current_allocations: dict,
        target_allocations: dict,
    ) -> dict:
        """
        Apply smoothing so allocations don't change more than MAX_CHANGE_PER_REBALANCE
        per rebalance cycle.

        Args:
            current_allocations: Current allocation_pct per strategy
            target_allocations: Target allocation_pct per strategy

        Returns:
            dict: Smoothed allocation_pct per strategy
        """
        smoothed = {}
        for code in STRATEGY_CODES:
            current = current_allocations.get(code, 25.0)
            target = target_allocations.get(code, 25.0)
            diff = target - current

            if abs(diff) <= MAX_CHANGE_PER_REBALANCE:
                smoothed[code] = target
            elif diff > 0:
                smoothed[code] = round(current + MAX_CHANGE_PER_REBALANCE, 1)
            else:
                smoothed[code] = round(current - MAX_CHANGE_PER_REBALANCE, 1)

            # Ensure floor
            smoothed[code] = max(MIN_ALLOCATION_PCT, smoothed[code])

        # Normalize to 100% after smoothing
        total = sum(smoothed.values())
        if total > 0 and abs(total - 100.0) > 0.2:
            smoothed = {
                code: round((pct / total) * 100.0, 1)
                for code, pct in smoothed.items()
            }
            # Fix rounding
            diff = 100.0 - sum(smoothed.values())
            if abs(diff) > 0.05:
                best = max(smoothed, key=smoothed.get)
                smoothed[best] = round(smoothed[best] + diff, 1)

        return smoothed

    # ------------------------------------------------------------------ #
    #  Core: Check and Rebalance
    # ------------------------------------------------------------------ #

    def on_trade_completed(
        self,
        xp_data: dict,
        learner_adjustments: dict,
        rl_stats: dict,
        current_allocations: dict,
    ) -> Optional[dict]:
        """
        Called after every trade completion. Increments counter and triggers
        rebalance if interval is reached.

        Args:
            xp_data: From StrategyXP.get_all_xp()
            learner_adjustments: From BrainLearner.get_strategy_confidence_adjustments()
            rl_stats: From BrainLearner.get_rl_stats()
            current_allocations: Current {code: allocation_pct} from database

        Returns:
            Optional[dict]: New allocations if rebalance occurred, None otherwise.
                Format: {
                    "allocations": {code: pct},
                    "fitness_scores": {code: score_data},
                    "rebalance_number": int,
                    "changes": {code: {from, to, delta}},
                }
        """
        if not self._enabled:
            return None

        self._trades_since_rebalance += 1

        if self._trades_since_rebalance < REBALANCE_INTERVAL:
            return None

        # Time to rebalance
        self._trades_since_rebalance = 0
        self._total_rebalances += 1

        # Calculate fitness scores
        fitness = self.calculate_fitness_scores(xp_data, learner_adjustments, rl_stats)
        self._last_fitness_scores = fitness

        # Calculate target allocations
        target = self.calculate_target_allocations(fitness)

        # Apply smoothing
        new_allocations = self.apply_smoothing(current_allocations, target)
        self._last_allocations = new_allocations

        # Build change summary
        changes = {}
        for code in STRATEGY_CODES:
            old = current_allocations.get(code, 25.0)
            new = new_allocations[code]
            changes[code] = {
                "from": old,
                "to": new,
                "delta": round(new - old, 1),
            }

        now = datetime.now(timezone.utc).isoformat()
        self._last_rebalance_time = now

        # Record in history (keep last 20)
        event = {
            "timestamp": now,
            "rebalance_number": self._total_rebalances,
            "allocations": new_allocations,
            "fitness_scores": {code: data["score"] for code, data in fitness.items()},
            "changes": changes,
        }
        self._rebalance_history.append(event)
        if len(self._rebalance_history) > 20:
            self._rebalance_history = self._rebalance_history[-20:]

        # Persist state
        self._save_state()

        logger.info(
            "auto_rebalance",
            rebalance_number=self._total_rebalances,
            allocations=new_allocations,
            fitness={code: data["score"] for code, data in fitness.items()},
            changes=changes,
        )

        return {
            "allocations": new_allocations,
            "fitness_scores": fitness,
            "rebalance_number": self._total_rebalances,
            "changes": changes,
            "timestamp": now,
        }

    # ------------------------------------------------------------------ #
    #  Status for Dashboard
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        """
        Return current auto-allocation status for the dashboard API.

        Returns:
            dict: Full auto-allocation state for frontend display

        CALLED BY: api/routes_brain.py /auto-allocation-status
        """
        return {
            "enabled": self._enabled,
            "trades_since_rebalance": self._trades_since_rebalance,
            "rebalance_interval": REBALANCE_INTERVAL,
            "trades_until_next": max(0, REBALANCE_INTERVAL - self._trades_since_rebalance),
            "total_rebalances": self._total_rebalances,
            "last_rebalance_time": self._last_rebalance_time,
            "last_fitness_scores": self._last_fitness_scores,
            "last_allocations": self._last_allocations,
            "rebalance_history": self._rebalance_history[-10:],
            "config": {
                "rebalance_interval": REBALANCE_INTERVAL,
                "max_change_per_rebalance": MAX_CHANGE_PER_REBALANCE,
                "min_allocation_pct": MIN_ALLOCATION_PCT,
                "max_allocation_pct": MAX_ALLOCATION_PCT,
                "weights": {
                    "xp_level": WEIGHT_XP_LEVEL,
                    "win_rate": WEIGHT_WIN_RATE,
                    "profit_factor": WEIGHT_PROFIT_FACTOR,
                    "rl_expected": WEIGHT_RL_EXPECTED,
                    "streak": WEIGHT_STREAK,
                },
            },
        }

    def set_enabled(self, enabled: bool) -> None:
        """Toggle auto-allocation on/off."""
        self._enabled = enabled
        self._save_state()
        logger.info("auto_allocation_toggled", enabled=enabled)

    # ------------------------------------------------------------------ #
    #  Persistence
    # ------------------------------------------------------------------ #

    def _save_state(self) -> bool:
        """Persist auto-allocation state to disk."""
        try:
            state = {
                "enabled": self._enabled,
                "trades_since_rebalance": self._trades_since_rebalance,
                "total_rebalances": self._total_rebalances,
                "last_rebalance_time": self._last_rebalance_time,
                "last_fitness_scores": self._last_fitness_scores,
                "last_allocations": self._last_allocations,
                "rebalance_history": self._rebalance_history,
                "_saved_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_path = AUTO_ALLOC_STATE_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp_path, AUTO_ALLOC_STATE_PATH)
            return True
        except Exception as e:
            logger.error("auto_alloc_save_failed", error=str(e))
            return False

    def _load_state(self) -> bool:
        """Load auto-allocation state from disk."""
        if not os.path.exists(AUTO_ALLOC_STATE_PATH):
            logger.info("auto_alloc_state_not_found", message="Starting fresh")
            return False
        try:
            with open(AUTO_ALLOC_STATE_PATH, "r") as f:
                state = json.load(f)
            self._enabled = state.get("enabled", True)
            self._trades_since_rebalance = state.get("trades_since_rebalance", 0)
            self._total_rebalances = state.get("total_rebalances", 0)
            self._last_rebalance_time = state.get("last_rebalance_time")
            self._last_fitness_scores = state.get("last_fitness_scores", {})
            self._last_allocations = state.get("last_allocations", {})
            self._rebalance_history = state.get("rebalance_history", [])
            logger.info(
                "auto_alloc_state_loaded",
                total_rebalances=self._total_rebalances,
                enabled=self._enabled,
            )
            return True
        except Exception as e:
            logger.error("auto_alloc_load_failed", error=str(e))
            return False
