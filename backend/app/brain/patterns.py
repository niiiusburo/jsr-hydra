"""
PURPOSE: Pattern recognition from trade history for JSR Hydra Brain.

Detects trading patterns including regime bias, time-of-day patterns,
indicator correlations, and streak tracking. Produces actionable
human-readable insights that feed into the Brain's decision-making.

CALLED BY: brain/learner.py — after trade analysis and during periodic reviews
"""

from collections import defaultdict
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger("brain.patterns")

# Strategy human-readable names for insight generation
STRATEGY_NAMES = {
    "A": "Trend Following (EMA crossover + ADX)",
    "B": "Mean Reversion (Bollinger + Z-score)",
    "C": "Session Breakout",
    "D": "Momentum Scalper (BB + RSI)",
    "E": "Range Scalper (Sideways)",
}

# Minimum trades needed before pattern is considered meaningful
MIN_TRADES_FOR_PATTERN = 5


def _safe_win_rate(wins: int, total: int) -> float:
    """Return win rate as a float between 0.0 and 1.0, safe from division by zero."""
    if total == 0:
        return 0.0
    return wins / total


def _pct(rate: float) -> str:
    """Format a 0-1 rate as a percentage string like '72%'."""
    return f"{rate * 100:.0f}%"


def detect_regime_bias(trade_history: list) -> list[str]:
    """
    PURPOSE: Detect which strategies perform best/worst in each regime.

    Analyzes trade history to find regime-strategy correlations.
    E.g., "Strategy A excels in trending markets (75% win rate)"

    Args:
        trade_history: List of trade dicts with keys: strategy, regime, won, profit

    Returns:
        list[str]: Human-readable insights about regime-strategy relationships.

    CALLED BY: brain/learner.py — get_learned_insights(), generate_market_memory()
    """
    if not trade_history:
        return ["Not enough trade data yet to detect regime bias."]

    # Aggregate: {strategy: {regime: {wins, losses, total_profit}}}
    stats = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "total_profit": 0.0}))

    for trade in trade_history:
        strategy = trade.get("strategy", "?")
        regime = trade.get("regime", "UNKNOWN")
        won = trade.get("won", False)
        profit = trade.get("profit", 0.0)

        bucket = stats[strategy][regime]
        if won:
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1
        bucket["total_profit"] += profit

    insights = []

    for strategy in sorted(stats.keys()):
        for regime, data in stats[strategy].items():
            total = data["wins"] + data["losses"]
            if total < MIN_TRADES_FOR_PATTERN:
                continue

            win_rate = _safe_win_rate(data["wins"], total)
            avg_profit = data["total_profit"] / total

            name = STRATEGY_NAMES.get(strategy, f"Strategy {strategy}")

            if win_rate >= 0.65:
                insights.append(
                    f"Strategy {strategy} excels in {regime} "
                    f"({_pct(win_rate)} win rate over {total} trades, "
                    f"avg profit ${avg_profit:+.2f})"
                )
            elif win_rate <= 0.35:
                insights.append(
                    f"Strategy {strategy} struggles in {regime} "
                    f"({_pct(win_rate)} win rate over {total} trades, "
                    f"avg loss ${avg_profit:+.2f})"
                )

    if not insights:
        return ["Regime bias patterns are still forming. Need more trades per regime."]

    return insights


def detect_time_patterns(trade_history: list) -> list[str]:
    """
    PURPOSE: Detect session-based performance patterns.

    Identifies which trading sessions produce the best/worst outcomes.
    E.g., "Most winning trades occur during London session (08:00-16:00 UTC)"

    Args:
        trade_history: List of trade dicts with keys: strategy, session, won, profit

    Returns:
        list[str]: Human-readable insights about session performance.

    CALLED BY: brain/learner.py — get_learned_insights()
    """
    if not trade_history:
        return ["Not enough trade data yet to detect time patterns."]

    # Aggregate by session
    session_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "total_profit": 0.0})

    for trade in trade_history:
        session = trade.get("session", "UNKNOWN")
        won = trade.get("won", False)
        profit = trade.get("profit", 0.0)

        bucket = session_stats[session]
        if won:
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1
        bucket["total_profit"] += profit

    # Also aggregate by strategy + session
    strategy_session = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "losses": 0}))

    for trade in trade_history:
        strategy = trade.get("strategy", "?")
        session = trade.get("session", "UNKNOWN")
        won = trade.get("won", False)

        if won:
            strategy_session[strategy][session]["wins"] += 1
        else:
            strategy_session[strategy][session]["losses"] += 1

    session_hours = {
        "ASIAN": "00:00-08:00 UTC",
        "LONDON": "08:00-16:00 UTC",
        "NEWYORK": "13:00-22:00 UTC",
    }

    insights = []

    # Overall session performance
    best_session = None
    best_rate = 0.0

    for session, data in session_stats.items():
        total = data["wins"] + data["losses"]
        if total < MIN_TRADES_FOR_PATTERN:
            continue
        rate = _safe_win_rate(data["wins"], total)
        if rate > best_rate:
            best_rate = rate
            best_session = session

    if best_session and best_rate > 0.5:
        hours = session_hours.get(best_session, "")
        total = session_stats[best_session]["wins"] + session_stats[best_session]["losses"]
        insights.append(
            f"Most winning trades occur during {best_session} session "
            f"({hours}) with {_pct(best_rate)} win rate over {total} trades"
        )

    # Per-strategy session insights
    for strategy in sorted(strategy_session.keys()):
        for session, data in strategy_session[strategy].items():
            total = data["wins"] + data["losses"]
            if total < MIN_TRADES_FOR_PATTERN:
                continue
            rate = _safe_win_rate(data["wins"], total)
            hours = session_hours.get(session, "")

            if rate >= 0.70:
                insights.append(
                    f"Strategy {strategy} performs best during {session} session "
                    f"({hours}) — {_pct(rate)} win rate over {total} trades"
                )
            elif rate <= 0.30:
                insights.append(
                    f"Strategy {strategy} underperforms during {session} session "
                    f"({hours}) — {_pct(rate)} win rate over {total} trades"
                )

    if not insights:
        return ["Session-based patterns are still forming. Need more data per session."]

    return insights


def detect_indicator_patterns(trade_history: list) -> list[str]:
    """
    PURPOSE: Detect patterns based on indicator values at trade entry.

    Identifies RSI zones, ADX thresholds, and ATR conditions that
    correlate with trade success or failure.
    E.g., "Trades entered when RSI < 25 have 80% win rate"

    Args:
        trade_history: List of trade dicts with keys: strategy, rsi, adx, atr, won

    Returns:
        list[str]: Human-readable insights about indicator-performance correlations.

    CALLED BY: brain/learner.py — get_learned_insights()
    """
    if not trade_history:
        return ["Not enough trade data yet to detect indicator patterns."]

    # RSI zone analysis
    rsi_zones = {
        "deeply_oversold": {"range": (0, 25), "label": "RSI < 25", "wins": 0, "losses": 0},
        "oversold": {"range": (25, 30), "label": "RSI 25-30", "wins": 0, "losses": 0},
        "low_neutral": {"range": (30, 45), "label": "RSI 30-45", "wins": 0, "losses": 0},
        "neutral": {"range": (45, 55), "label": "RSI 45-55", "wins": 0, "losses": 0},
        "high_neutral": {"range": (55, 70), "label": "RSI 55-70", "wins": 0, "losses": 0},
        "overbought": {"range": (70, 75), "label": "RSI 70-75", "wins": 0, "losses": 0},
        "deeply_overbought": {"range": (75, 100), "label": "RSI > 75", "wins": 0, "losses": 0},
    }

    # ADX strength analysis
    adx_zones = {
        "weak": {"range": (0, 20), "label": "ADX < 20 (weak trend)", "wins": 0, "losses": 0},
        "moderate": {"range": (20, 30), "label": "ADX 20-30 (moderate trend)", "wins": 0, "losses": 0},
        "strong": {"range": (30, 40), "label": "ADX 30-40 (strong trend)", "wins": 0, "losses": 0},
        "very_strong": {"range": (40, 100), "label": "ADX > 40 (very strong trend)", "wins": 0, "losses": 0},
    }

    for trade in trade_history:
        rsi = trade.get("rsi")
        adx = trade.get("adx")
        won = trade.get("won", False)

        if rsi is not None:
            for zone in rsi_zones.values():
                low, high = zone["range"]
                if low <= rsi < high:
                    if won:
                        zone["wins"] += 1
                    else:
                        zone["losses"] += 1
                    break

        if adx is not None:
            for zone in adx_zones.values():
                low, high = zone["range"]
                if low <= adx < high:
                    if won:
                        zone["wins"] += 1
                    else:
                        zone["losses"] += 1
                    break

    insights = []

    # RSI insights
    for zone_name, zone in rsi_zones.items():
        total = zone["wins"] + zone["losses"]
        if total < MIN_TRADES_FOR_PATTERN:
            continue
        rate = _safe_win_rate(zone["wins"], total)

        if rate >= 0.65:
            insights.append(
                f"Trades entered when {zone['label']} have {_pct(rate)} win rate "
                f"({total} trades)"
            )
        elif rate <= 0.35:
            insights.append(
                f"Trades entered when {zone['label']} have poor results — "
                f"only {_pct(rate)} win rate ({total} trades)"
            )

    # ADX insights
    for zone_name, zone in adx_zones.items():
        total = zone["wins"] + zone["losses"]
        if total < MIN_TRADES_FOR_PATTERN:
            continue
        rate = _safe_win_rate(zone["wins"], total)

        if rate >= 0.65:
            insights.append(
                f"{zone['label']} significantly improves trade outcomes — "
                f"{_pct(rate)} win rate ({total} trades)"
            )
        elif rate <= 0.35:
            insights.append(
                f"{zone['label']} correlates with poor outcomes — "
                f"only {_pct(rate)} win rate ({total} trades)"
            )

    # Strategy-specific indicator patterns
    strategy_rsi = defaultdict(lambda: {"oversold_wins": 0, "oversold_total": 0, "overbought_wins": 0, "overbought_total": 0})

    for trade in trade_history:
        strategy = trade.get("strategy", "?")
        rsi = trade.get("rsi")
        won = trade.get("won", False)

        if rsi is None:
            continue

        if rsi < 30:
            strategy_rsi[strategy]["oversold_total"] += 1
            if won:
                strategy_rsi[strategy]["oversold_wins"] += 1
        elif rsi > 70:
            strategy_rsi[strategy]["overbought_total"] += 1
            if won:
                strategy_rsi[strategy]["overbought_wins"] += 1

    for strategy in sorted(strategy_rsi.keys()):
        data = strategy_rsi[strategy]

        if data["oversold_total"] >= MIN_TRADES_FOR_PATTERN:
            rate = _safe_win_rate(data["oversold_wins"], data["oversold_total"])
            if rate >= 0.65:
                insights.append(
                    f"Strategy {strategy} thrives in oversold conditions (RSI < 30) — "
                    f"{_pct(rate)} win rate"
                )
            elif rate <= 0.30:
                insights.append(
                    f"Strategy {strategy} fails in oversold conditions (RSI < 30) — "
                    f"only {_pct(rate)} win rate"
                )

    if not insights:
        return ["Indicator-based patterns are still forming. Need more data."]

    return insights


def detect_streaks(trade_history: list) -> dict:
    """
    PURPOSE: Detect current winning/losing streaks per strategy.

    Tracks consecutive wins or losses for each strategy to identify
    hot/cold streaks that may warrant confidence adjustments.

    Args:
        trade_history: List of trade dicts with keys: strategy, won
                       (should be chronologically ordered)

    Returns:
        dict: {strategy_code: {"current_streak": int, "type": "win"|"loss",
               "max_win_streak": int, "max_loss_streak": int}}

    CALLED BY: brain/learner.py — get_strategy_confidence_adjustments()
    """
    if not trade_history:
        return {}

    # Group trades by strategy in chronological order
    strategy_trades = defaultdict(list)
    for trade in trade_history:
        strategy = trade.get("strategy", "?")
        won = trade.get("won", False)
        strategy_trades[strategy].append(won)

    result = {}

    for strategy, outcomes in strategy_trades.items():
        current_streak = 0
        streak_type = "none"
        max_win_streak = 0
        max_loss_streak = 0
        temp_win = 0
        temp_loss = 0

        for won in outcomes:
            if won:
                temp_win += 1
                temp_loss = 0
                max_win_streak = max(max_win_streak, temp_win)
            else:
                temp_loss += 1
                temp_win = 0
                max_loss_streak = max(max_loss_streak, temp_loss)

        # Current streak is from the end of the list
        if outcomes:
            last = outcomes[-1]
            streak_type = "win" if last else "loss"
            current_streak = 1
            for i in range(len(outcomes) - 2, -1, -1):
                if outcomes[i] == last:
                    current_streak += 1
                else:
                    break

        result[strategy] = {
            "current_streak": current_streak,
            "type": streak_type,
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
        }

    return result


def generate_market_memory(trade_history: list, current_regime: str) -> str:
    """
    PURPOSE: Generate a comprehensive paragraph summarizing what the brain has learned.

    Combines regime performance, session patterns, indicator correlations, and
    current market context into a single narrative paragraph. This is the brain's
    "memory recall" — what it remembers about how markets have behaved.

    Args:
        trade_history: List of trade dicts with full context.
        current_regime: Current market regime string (e.g., "TRENDING_DOWN").

    Returns:
        str: A comprehensive human-readable paragraph of learned market memory.

    CALLED BY: brain/learner.py — for brain state summary, brain/prompts.py
    """
    if not trade_history:
        return (
            "The brain has no trade history yet. All strategies start with equal "
            "confidence. Observing and learning from each trade as it comes."
        )

    total_trades = len(trade_history)
    total_wins = sum(1 for t in trade_history if t.get("won", False))
    overall_rate = _safe_win_rate(total_wins, total_trades)

    # Strategy performance in current regime
    regime_perf = defaultdict(lambda: {"wins": 0, "total": 0, "profit": 0.0})
    for trade in trade_history:
        if trade.get("regime") == current_regime:
            s = trade.get("strategy", "?")
            regime_perf[s]["total"] += 1
            regime_perf[s]["profit"] += trade.get("profit", 0.0)
            if trade.get("won", False):
                regime_perf[s]["wins"] += 1

    # Best and worst strategies in current regime
    best_strategy = None
    best_rate = 0.0
    worst_strategy = None
    worst_rate = 1.0

    for strategy, data in regime_perf.items():
        if data["total"] < 3:
            continue
        rate = _safe_win_rate(data["wins"], data["total"])
        if rate > best_rate:
            best_rate = rate
            best_strategy = strategy
        if rate < worst_rate:
            worst_rate = rate
            worst_strategy = strategy

    # Session performance
    session_wins = defaultdict(lambda: {"wins": 0, "total": 0})
    for trade in trade_history:
        session = trade.get("session", "UNKNOWN")
        session_wins[session]["total"] += 1
        if trade.get("won", False):
            session_wins[session]["wins"] += 1

    best_session = None
    best_session_rate = 0.0
    for session, data in session_wins.items():
        if data["total"] < 3:
            continue
        rate = _safe_win_rate(data["wins"], data["total"])
        if rate > best_session_rate:
            best_session_rate = rate
            best_session = session

    # Build the narrative
    parts = [f"Over the last {total_trades} trades, the brain has observed"]

    # Overall performance
    parts[0] += f" an overall {_pct(overall_rate)} win rate."

    # Current regime insights
    if best_strategy and regime_perf[best_strategy]["total"] >= 3:
        parts.append(
            f"{current_regime} conditions favor Strategy {best_strategy} "
            f"({_pct(best_rate)} win rate)"
        )
    if worst_strategy and worst_strategy != best_strategy and regime_perf[worst_strategy]["total"] >= 3:
        parts.append(
            f"while Strategy {worst_strategy} consistently underperforms "
            f"({_pct(worst_rate)} win rate)"
        )

    # Session insights
    if best_session and best_session_rate > 0.5:
        parts.append(
            f"The most profitable entry window is during {best_session} session "
            f"({_pct(best_session_rate)} win rate)"
        )

    # Recent RSI context from last trade
    recent_trades = [t for t in trade_history if t.get("regime") == current_regime]
    if recent_trades:
        last = recent_trades[-1]
        rsi_val = last.get("rsi")
        adx_val = last.get("adx")
        context_parts = []
        if rsi_val is not None:
            context_parts.append(f"RSI {rsi_val:.0f}")
        if adx_val is not None:
            context_parts.append(f"ADX {adx_val:.0f}")
        if context_parts:
            parts.append(
                f"Current market conditions ({current_regime}, {', '.join(context_parts)}) "
                f"are being monitored for optimal entry setups"
            )

    return ". ".join(parts) + "."
