"""
PURPOSE: Pokemon-style XP/Leveling system for trading strategies.

Strategies gain XP from trades and level up as they improve. Each strategy
tracks total XP, current level, win/loss streaks, unlocked skills, and
earned badges. State persists to /tmp/jsr_strategy_xp.json.

CALLED BY:
    - brain/brain.py -> process_trade_result() awards XP after each trade
    - api/routes_brain.py -> /strategy-xp endpoint returns XP data
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from app.brain.paths import resolve_brain_state_path
from app.utils.logger import get_logger

logger = get_logger("brain.strategy_xp")

# Persistence path
XP_STATE_PATH = resolve_brain_state_path("strategy_xp.json")

# Strategy metadata
STRATEGY_NAMES = {
    "A": "Trend Following",
    "B": "Mean Reversion",
    "C": "Session Breakout",
    "D": "Momentum Scalper",
    "E": "Range Scalper (Sideways)",
}


class StrategyXP:
    """
    Pokemon-style leveling system for trading strategies.
    Strategies gain XP from trades and level up as they improve.
    """

    LEVELS = {
        1: {"name": "Novice", "xp_required": 0, "color": "#6B7280"},
        2: {"name": "Apprentice", "xp_required": 100, "color": "#3B82F6"},
        3: {"name": "Journeyman", "xp_required": 300, "color": "#10B981"},
        4: {"name": "Expert", "xp_required": 600, "color": "#8B5CF6"},
        5: {"name": "Master", "xp_required": 1000, "color": "#F59E0B"},
        6: {"name": "Grandmaster", "xp_required": 1500, "color": "#EF4444"},
        7: {"name": "Legend", "xp_required": 2500, "color": "#EC4899"},
        8: {"name": "Mythic", "xp_required": 4000, "color": "#F97316"},
        9: {"name": "Transcendent", "xp_required": 6000, "color": "#14B8A6"},
        10: {"name": "Apex Predator", "xp_required": 10000, "color": "#FFD700"},
    }

    XP_REWARDS = {
        "winning_trade": 25,       # Base XP for a winning trade
        "losing_trade": 5,         # Small XP even for losses (learning)
        "big_win": 50,             # Win > 2R (2x risk)
        "streak_bonus": 10,        # Per consecutive win in streak
        "new_symbol_bonus": 15,    # First trade on a new symbol
        "regime_adaptation": 20,   # Profitable trade in a new regime
        "risk_discipline": 10,     # Trade with proper SL/TP
        "quick_scalp": 15,         # Profitable trade < 30 minutes
    }

    SKILLS = {
        1: [],
        2: ["Basic Pattern Recognition"],
        3: ["Can trade during high volatility"],
        4: ["Multi-timeframe analysis", "Adaptive stop-loss"],
        5: ["Increased lot size allowed", "Counter-trend entries"],
        6: ["News event trading", "Correlation-based filtering"],
        7: ["Full autonomy mode", "Dynamic risk scaling"],
        8: ["Cross-pair hedging", "Sentiment integration"],
        9: ["Regime prediction", "Adaptive parameter tuning"],
        10: ["Apex mode: unrestricted trading", "Self-optimizing parameters"],
    }

    BADGE_DEFINITIONS = {
        "first_blood": {
            "name": "First Blood",
            "description": "Completed first trade",
            "icon": "sword",
        },
        "gold_rush": {
            "name": "Gold Rush",
            "description": "First trade on XAUUSD",
            "icon": "coins",
        },
        "streak_master": {
            "name": "Streak Master",
            "description": "Achieved 5+ win streak",
            "icon": "fire",
        },
        "survivor": {
            "name": "Survivor",
            "description": "Recovered from 3+ loss streak",
            "icon": "shield",
        },
        "speed_demon": {
            "name": "Speed Demon",
            "description": "Profitable scalp under 5 minutes",
            "icon": "zap",
        },
        "risk_manager": {
            "name": "Risk Manager",
            "description": "100 trades with stop-loss",
            "icon": "lock",
        },
        "century": {
            "name": "Century",
            "description": "Completed 100 trades",
            "icon": "trophy",
        },
        "ten_streak": {
            "name": "Unstoppable",
            "description": "10-win streak",
            "icon": "star",
        },
        "big_winner": {
            "name": "Big Winner",
            "description": "Single trade profit > 2R",
            "icon": "gem",
        },
        "multi_symbol": {
            "name": "Diversifier",
            "description": "Traded on 4+ symbols",
            "icon": "globe",
        },
    }

    def __init__(self):
        """Initialize the XP system with empty or restored state."""
        self._state: dict = {}
        self._load_state()

    def _empty_strategy_state(self, code: str) -> dict:
        """Return a clean initial XP state for a single strategy."""
        return {
            "code": code,
            "name": STRATEGY_NAMES.get(code, f"Strategy {code}"),
            "total_xp": 0,
            "level": 1,
            "level_name": "Novice",
            "level_color": "#6B7280",
            "xp_to_next_level": 100,
            "xp_current_level": 0,
            "xp_needed_for_level": 100,
            "progress_pct": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "best_streak": 0,
            "current_streak": 0,
            "current_streak_type": "none",
            "worst_streak": 0,
            "skills_unlocked": [],
            "badges": [],
            "symbols_traded": [],
            "regimes_traded": [],
            "trades_with_sl": 0,
            "total_profit": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_duration_seconds": 0.0,
            "xp_history": [],
            "last_updated": None,
        }

    def _ensure_strategy(self, code: str) -> dict:
        """Ensure a strategy entry exists in state."""
        if code not in self._state:
            self._state[code] = self._empty_strategy_state(code)
        return self._state[code]

    # ------------------------------------------------------------------ #
    #  XP Calculation and Leveling
    # ------------------------------------------------------------------ #

    def _calculate_level(self, total_xp: int) -> tuple:
        """
        Calculate level, level name, color, and progress from total XP.

        Returns:
            tuple: (level, level_name, level_color, xp_to_next, xp_in_current_level,
                    xp_needed_for_level, progress_pct)
        """
        current_level = 1
        for lvl in sorted(self.LEVELS.keys(), reverse=True):
            if total_xp >= self.LEVELS[lvl]["xp_required"]:
                current_level = lvl
                break

        level_info = self.LEVELS[current_level]
        level_name = level_info["name"]
        level_color = level_info["color"]

        # Calculate progress to next level
        if current_level < 10:
            next_level_xp = self.LEVELS[current_level + 1]["xp_required"]
            current_level_xp = level_info["xp_required"]
            xp_in_level = total_xp - current_level_xp
            xp_needed = next_level_xp - current_level_xp
            xp_to_next = next_level_xp - total_xp
            progress_pct = round((xp_in_level / xp_needed) * 100, 1) if xp_needed > 0 else 100.0
        else:
            # Max level
            xp_to_next = 0
            xp_in_level = total_xp - level_info["xp_required"]
            xp_needed = 0
            progress_pct = 100.0

        return (current_level, level_name, level_color, xp_to_next,
                xp_in_level, xp_needed, progress_pct)

    def _get_skills_for_level(self, level: int) -> list:
        """Return all skills unlocked up to and including the given level."""
        skills = []
        for lvl in range(1, level + 1):
            skills.extend(self.SKILLS.get(lvl, []))
        return skills

    def _calculate_xp_for_trade(self, strategy_state: dict, trade_result: dict) -> tuple:
        """
        Calculate XP earned from a trade.

        Args:
            strategy_state: Current strategy XP state dict.
            trade_result: Trade result dict with keys: won, profit, sl_distance,
                         duration_seconds, symbol, regime, has_sl, has_tp.

        Returns:
            tuple: (total_xp_earned, xp_breakdown_list)
        """
        xp = 0
        breakdown = []

        won = trade_result.get("won", False)
        profit = trade_result.get("profit", 0.0)
        sl_distance = trade_result.get("sl_distance", 1.0)
        duration = trade_result.get("duration_seconds", 3600)
        symbol = trade_result.get("symbol", "UNKNOWN")
        regime = trade_result.get("regime", "UNKNOWN")
        has_sl = trade_result.get("has_sl", True)

        # Base XP for win or loss
        if won:
            xp += self.XP_REWARDS["winning_trade"]
            breakdown.append(("Winning trade", self.XP_REWARDS["winning_trade"]))
        else:
            xp += self.XP_REWARDS["losing_trade"]
            breakdown.append(("Trade experience", self.XP_REWARDS["losing_trade"]))

        # Big win bonus (> 2R)
        if won and sl_distance > 0:
            r_multiple = abs(profit) / sl_distance
            if r_multiple >= 2.0:
                xp += self.XP_REWARDS["big_win"]
                breakdown.append(("Big win (>2R)", self.XP_REWARDS["big_win"]))

        # Streak bonus
        if won and strategy_state.get("current_streak_type") == "win":
            streak_len = strategy_state.get("current_streak", 0)
            streak_xp = self.XP_REWARDS["streak_bonus"] * min(streak_len, 10)
            if streak_xp > 0:
                xp += streak_xp
                breakdown.append((f"Win streak x{streak_len}", streak_xp))

        # New symbol bonus
        symbols_traded = strategy_state.get("symbols_traded", [])
        if symbol and symbol not in symbols_traded:
            xp += self.XP_REWARDS["new_symbol_bonus"]
            breakdown.append((f"New symbol: {symbol}", self.XP_REWARDS["new_symbol_bonus"]))

        # Regime adaptation bonus
        regimes_traded = strategy_state.get("regimes_traded", [])
        if won and regime and regime not in regimes_traded:
            xp += self.XP_REWARDS["regime_adaptation"]
            breakdown.append((f"Regime adaptation: {regime}", self.XP_REWARDS["regime_adaptation"]))

        # Risk discipline bonus
        if has_sl:
            xp += self.XP_REWARDS["risk_discipline"]
            breakdown.append(("Risk discipline (SL set)", self.XP_REWARDS["risk_discipline"]))

        # Quick scalp bonus
        if won and duration < 1800:  # < 30 minutes
            xp += self.XP_REWARDS["quick_scalp"]
            breakdown.append(("Quick scalp (<30min)", self.XP_REWARDS["quick_scalp"]))

        return xp, breakdown

    # ------------------------------------------------------------------ #
    #  Badge Checking
    # ------------------------------------------------------------------ #

    def _check_badges(self, strategy_state: dict, trade_result: dict) -> list:
        """Check and award any new badges after a trade."""
        current_badges = [b["id"] for b in strategy_state.get("badges", [])]
        new_badges = []
        now = datetime.now(timezone.utc).isoformat()

        # First Blood
        if "first_blood" not in current_badges and strategy_state.get("total_trades", 0) >= 1:
            new_badges.append({
                "id": "first_blood",
                **self.BADGE_DEFINITIONS["first_blood"],
                "earned_at": now,
            })

        # Gold Rush
        symbol = trade_result.get("symbol", "")
        if "gold_rush" not in current_badges and "XAU" in symbol.upper():
            new_badges.append({
                "id": "gold_rush",
                **self.BADGE_DEFINITIONS["gold_rush"],
                "earned_at": now,
            })

        # Streak Master
        if "streak_master" not in current_badges and strategy_state.get("best_streak", 0) >= 5:
            new_badges.append({
                "id": "streak_master",
                **self.BADGE_DEFINITIONS["streak_master"],
                "earned_at": now,
            })

        # Unstoppable (10 win streak)
        if "ten_streak" not in current_badges and strategy_state.get("best_streak", 0) >= 10:
            new_badges.append({
                "id": "ten_streak",
                **self.BADGE_DEFINITIONS["ten_streak"],
                "earned_at": now,
            })

        # Survivor: recovered from 3+ loss streak
        # Use pre-update streak type (before the win resets the streak counter)
        pre_streak_type = trade_result.get("_pre_streak_type", strategy_state.get("current_streak_type", "none"))
        pre_streak_len = trade_result.get("_pre_streak_len", strategy_state.get("current_streak", 0))
        if ("survivor" not in current_badges
                and trade_result.get("won", False)
                and pre_streak_type == "loss"
                and pre_streak_len >= 3):
            new_badges.append({
                "id": "survivor",
                **self.BADGE_DEFINITIONS["survivor"],
                "earned_at": now,
            })

        # Speed Demon
        duration = trade_result.get("duration_seconds", 3600)
        if ("speed_demon" not in current_badges
                and trade_result.get("won", False)
                and duration < 300):
            new_badges.append({
                "id": "speed_demon",
                **self.BADGE_DEFINITIONS["speed_demon"],
                "earned_at": now,
            })

        # Risk Manager
        if "risk_manager" not in current_badges and strategy_state.get("trades_with_sl", 0) >= 100:
            new_badges.append({
                "id": "risk_manager",
                **self.BADGE_DEFINITIONS["risk_manager"],
                "earned_at": now,
            })

        # Century
        if "century" not in current_badges and strategy_state.get("total_trades", 0) >= 100:
            new_badges.append({
                "id": "century",
                **self.BADGE_DEFINITIONS["century"],
                "earned_at": now,
            })

        # Big Winner
        if "big_winner" not in current_badges:
            sl_dist = trade_result.get("sl_distance", 1.0)
            profit = trade_result.get("profit", 0.0)
            if sl_dist > 0 and trade_result.get("won", False) and abs(profit) / sl_dist >= 2.0:
                new_badges.append({
                    "id": "big_winner",
                    **self.BADGE_DEFINITIONS["big_winner"],
                    "earned_at": now,
                })

        # Diversifier
        if "multi_symbol" not in current_badges and len(strategy_state.get("symbols_traded", [])) >= 4:
            new_badges.append({
                "id": "multi_symbol",
                **self.BADGE_DEFINITIONS["multi_symbol"],
                "earned_at": now,
            })

        return new_badges

    # ------------------------------------------------------------------ #
    #  Core: Award XP
    # ------------------------------------------------------------------ #

    def award_xp(self, strategy_code: str, trade_result: dict) -> dict:
        """
        Award XP to a strategy based on trade result.

        Args:
            strategy_code: Strategy code (A, B, C, D).
            trade_result: Dict with keys: won, profit, sl_distance,
                         duration_seconds, symbol, regime, has_sl, has_tp.

        Returns:
            dict: {
                "xp_earned": int,
                "xp_breakdown": list of (reason, amount),
                "new_level": int or None (if leveled up),
                "level_up": bool,
                "old_level": int,
                "new_badges": list,
                "notification": str or None,
            }

        CALLED BY: brain/brain.py process_trade_result()
        """
        state = self._ensure_strategy(strategy_code)
        old_level = state["level"]
        won = trade_result.get("won", False)
        profit = trade_result.get("profit", 0.0)
        symbol = trade_result.get("symbol", "UNKNOWN")
        regime = trade_result.get("regime", "UNKNOWN")
        duration = trade_result.get("duration_seconds", 3600)
        has_sl = trade_result.get("has_sl", True)

        # Capture streak state BEFORE updating (needed for Survivor badge check)
        pre_update_streak_type = state.get("current_streak_type", "none")
        pre_update_streak_len = state.get("current_streak", 0)

        # Update trade stats BEFORE XP calculation (streak matters)
        state["total_trades"] += 1
        if won:
            state["wins"] += 1
            if state["current_streak_type"] == "win":
                state["current_streak"] += 1
            else:
                state["current_streak"] = 1
                state["current_streak_type"] = "win"
            state["best_streak"] = max(state["best_streak"], state["current_streak"])
        else:
            state["losses"] += 1
            if state["current_streak_type"] == "loss":
                state["current_streak"] += 1
            else:
                state["current_streak"] = 1
                state["current_streak_type"] = "loss"
            state["worst_streak"] = max(state["worst_streak"], state["current_streak"])

        # Update win rate
        state["win_rate"] = round(state["wins"] / state["total_trades"], 3) if state["total_trades"] > 0 else 0.0

        # Update symbol and regime tracking
        if symbol and symbol not in state["symbols_traded"]:
            state["symbols_traded"].append(symbol)
        if regime and regime not in state["regimes_traded"]:
            state["regimes_traded"].append(regime)

        # Update SL tracking
        if has_sl:
            state["trades_with_sl"] += 1

        # Update profit stats
        state["total_profit"] = round(state["total_profit"] + profit, 2)
        if profit > state["best_trade"]:
            state["best_trade"] = round(profit, 2)
        if profit < state["worst_trade"]:
            state["worst_trade"] = round(profit, 2)

        # Update average duration
        prev_total_duration = state["avg_duration_seconds"] * (state["total_trades"] - 1)
        state["avg_duration_seconds"] = round(
            (prev_total_duration + duration) / state["total_trades"], 1
        )

        # Calculate XP
        xp_earned, xp_breakdown = self._calculate_xp_for_trade(state, trade_result)
        state["total_xp"] += xp_earned

        # Recalculate level
        (level, level_name, level_color, xp_to_next,
         xp_in_level, xp_needed, progress_pct) = self._calculate_level(state["total_xp"])

        state["level"] = level
        state["level_name"] = level_name
        state["level_color"] = level_color
        state["xp_to_next_level"] = xp_to_next
        state["xp_current_level"] = xp_in_level
        state["xp_needed_for_level"] = xp_needed
        state["progress_pct"] = progress_pct

        # Update skills
        state["skills_unlocked"] = self._get_skills_for_level(level)

        # Inject pre-update streak info into trade_result context for Survivor badge
        trade_result_with_context = dict(trade_result)
        trade_result_with_context["_pre_streak_type"] = pre_update_streak_type
        trade_result_with_context["_pre_streak_len"] = pre_update_streak_len

        # Check badges
        new_badges = self._check_badges(state, trade_result_with_context)
        state["badges"].extend(new_badges)

        # Record XP event in history (keep last 50)
        state["xp_history"].append({
            "xp": xp_earned,
            "total_xp": state["total_xp"],
            "level": level,
            "won": won,
            "profit": round(profit, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(state["xp_history"]) > 50:
            state["xp_history"] = state["xp_history"][-50:]

        state["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Check for level-up
        leveled_up = level > old_level
        notification = None
        if leveled_up:
            notification = (
                f"LEVEL UP! Strategy {strategy_code} ({STRATEGY_NAMES.get(strategy_code, '')}) "
                f"reached Level {level} ({level_name})! "
                f"+{xp_earned} XP from {'winning' if won else 'losing'} trade."
            )
            logger.info(
                "strategy_level_up",
                strategy=strategy_code,
                old_level=old_level,
                new_level=level,
                level_name=level_name,
                total_xp=state["total_xp"],
            )

        # Persist state
        self._save_state()

        logger.debug(
            "xp_awarded",
            strategy=strategy_code,
            xp_earned=xp_earned,
            total_xp=state["total_xp"],
            level=level,
            level_name=level_name,
        )

        return {
            "xp_earned": xp_earned,
            "xp_breakdown": xp_breakdown,
            "new_level": level if leveled_up else None,
            "level_up": leveled_up,
            "old_level": old_level,
            "new_badges": new_badges,
            "notification": notification,
        }

    # ------------------------------------------------------------------ #
    #  Queries
    # ------------------------------------------------------------------ #

    def get_strategy_xp(self, strategy_code: str) -> dict:
        """Return XP data for a single strategy."""
        return self._ensure_strategy(strategy_code).copy()

    def get_all_xp(self) -> dict:
        """
        Return XP data for all configured strategies.

        Returns:
            dict: {strategy_code: strategy_xp_state}

        CALLED BY: api/routes_brain.py /strategy-xp endpoint
        """
        # Ensure all strategies exist
        for code in ("A", "B", "C", "D", "E"):
            self._ensure_strategy(code)

        return {
            code: state.copy()
            for code, state in self._state.items()
        }

    # ------------------------------------------------------------------ #
    #  Persistence
    # ------------------------------------------------------------------ #

    def _save_state(self) -> bool:
        """Persist XP state to disk."""
        try:
            tmp_path = XP_STATE_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
            os.replace(tmp_path, XP_STATE_PATH)
            return True
        except Exception as e:
            logger.error("xp_state_save_failed", error=str(e))
            return False

    def _load_state(self) -> bool:
        """Load XP state from disk."""
        if not os.path.exists(XP_STATE_PATH):
            logger.info("xp_state_not_found", message="Starting with fresh XP state")
            return False

        try:
            with open(XP_STATE_PATH, "r") as f:
                self._state = json.load(f)
            logger.info(
                "xp_state_loaded",
                strategies=list(self._state.keys()),
            )
            return True
        except Exception as e:
            logger.error("xp_state_load_failed", error=str(e))
            self._state = {}
            return False
