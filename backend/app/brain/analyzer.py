"""
PURPOSE: Market analysis helper functions that generate human-readable insights from raw indicator data.

Transforms numeric indicator values into concise trader language. Each function takes raw numbers
and returns a sentence or two that a seasoned trader would use to describe the current read.

CALLED BY:
    - brain/brain.py (Brain.process_cycle)
"""

from typing import Optional, Dict, List


# ════════════════════════════════════════════════════════════════
# Trend Analysis
# ════════════════════════════════════════════════════════════════


def analyze_trend(ema_20: Optional[float], ema_50: Optional[float], adx_val: Optional[float]) -> str:
    """
    PURPOSE: Generate human-readable trend analysis from EMA and ADX values.

    Args:
        ema_20: 20-period EMA value
        ema_50: 50-period EMA value
        adx_val: ADX indicator value

    Returns:
        str: Concise trend description a trader would use

    CALLED BY: brain.py process_cycle
    """
    if ema_20 is None or ema_50 is None or adx_val is None:
        return "Insufficient data for trend analysis."

    # Determine trend direction
    if ema_20 > ema_50:
        direction = "uptrend"
        ema_desc = f"EMA20 ({ema_20}) above EMA50 ({ema_50})"
    elif ema_20 < ema_50:
        direction = "downtrend"
        ema_desc = f"EMA20 ({ema_20}) below EMA50 ({ema_50})"
    else:
        direction = "flat"
        ema_desc = f"EMA20 and EMA50 converged at {ema_20}"

    # ADX strength classification
    if adx_val >= 50:
        strength = "extremely strong"
    elif adx_val >= 40:
        strength = "strong"
    elif adx_val >= 25:
        strength = "moderate"
    elif adx_val >= 15:
        strength = "weak"
    else:
        strength = "absent"

    if direction == "flat":
        return f"No clear trend. {ema_desc}. ADX at {adx_val} shows {strength} directional movement."

    if adx_val >= 25:
        return f"{strength.capitalize()} {direction}: {ema_desc}. ADX at {adx_val} confirms directional conviction."
    else:
        return f"Weak {direction}: {ema_desc}, but ADX at {adx_val} suggests {strength} directional momentum — trend may lack follow-through."


# ════════════════════════════════════════════════════════════════
# Momentum Analysis
# ════════════════════════════════════════════════════════════════


def analyze_momentum(rsi_val: Optional[float], adx_val: Optional[float]) -> str:
    """
    PURPOSE: Generate human-readable momentum assessment from RSI and ADX.

    Args:
        rsi_val: RSI indicator value (0-100)
        adx_val: ADX indicator value

    Returns:
        str: Momentum description with actionable context

    CALLED BY: brain.py process_cycle
    """
    if rsi_val is None:
        return "No RSI data available for momentum read."

    # RSI zone classification
    if rsi_val >= 80:
        zone = "extremely overbought"
        outlook = "Reversal risk is elevated — watching for exhaustion signals."
    elif rsi_val >= 70:
        zone = "overbought"
        outlook = "Buyers stretched. Pullback likely if momentum fades."
    elif rsi_val >= 60:
        zone = "bullish"
        outlook = "Healthy upside momentum. Trend continuation favored."
    elif rsi_val >= 40:
        zone = "neutral"
        outlook = "No clear momentum bias. Waiting for directional catalyst."
    elif rsi_val >= 30:
        zone = "bearish"
        outlook = "Selling pressure dominant. Downside continuation possible."
    elif rsi_val >= 20:
        zone = "oversold"
        outlook = "Sellers stretched. Bounce potential if support holds."
    else:
        zone = "deeply oversold"
        outlook = "Extreme selling — potential reversal or capitulation in progress."

    adx_context = ""
    if adx_val is not None:
        if adx_val >= 25:
            adx_context = f" ADX at {adx_val} confirms strong directional pressure."
        else:
            adx_context = f" ADX at {adx_val} — weak trend, momentum may not sustain."

    return f"RSI at {rsi_val} ({zone}). {outlook}{adx_context}"


# ════════════════════════════════════════════════════════════════
# Volatility Analysis
# ════════════════════════════════════════════════════════════════


def analyze_volatility(atr_val: Optional[float], spread: Optional[float]) -> str:
    """
    PURPOSE: Generate human-readable volatility assessment from ATR and spread.

    Args:
        atr_val: Average True Range value
        spread: Current bid-ask spread

    Returns:
        str: Volatility description with trading implications

    CALLED BY: brain.py process_cycle
    """
    if atr_val is None:
        return "No ATR data for volatility assessment."

    # ATR-based volatility classification (forex-scale heuristic)
    # For XAUUSD: ATR thresholds are higher than EURUSD
    if atr_val >= 5.0:
        # Gold-scale volatility
        if atr_val >= 30:
            vol_level = "extremely high"
            implication = "Wide swings expected — widen stops or reduce size."
        elif atr_val >= 15:
            vol_level = "elevated"
            implication = "Active market — good for breakout strategies."
        elif atr_val >= 8:
            vol_level = "moderate"
            implication = "Normal trading conditions."
        else:
            vol_level = "low"
            implication = "Tight range — breakout may be brewing."
    else:
        # Forex-scale volatility (EURUSD etc.)
        if atr_val >= 0.0020:
            vol_level = "elevated"
            implication = "Active market — good for breakout strategies."
        elif atr_val >= 0.0010:
            vol_level = "moderate"
            implication = "Normal trading conditions."
        elif atr_val >= 0.0005:
            vol_level = "low"
            implication = "Tight range — breakout may be brewing."
        else:
            vol_level = "very low"
            implication = "Compressed volatility — potential explosive move ahead."

    spread_note = ""
    if spread is not None and spread > 0:
        spread_note = f" Spread at {spread}."

    return f"{vol_level.capitalize()} volatility (ATR {atr_val}). {implication}{spread_note}"


# ════════════════════════════════════════════════════════════════
# Regime Interpretation
# ════════════════════════════════════════════════════════════════


def interpret_regime(regime: Optional[str], confidence: Optional[float]) -> str:
    """
    PURPOSE: Generate human-readable regime interpretation.

    Args:
        regime: Regime string (TRENDING_UP, TRENDING_DOWN, RANGING, etc.)
        confidence: Regime detection confidence (0.0 - 1.0)

    Returns:
        str: Regime description with conviction level and implications

    CALLED BY: brain.py process_cycle
    """
    if regime is None:
        return "No regime data available."

    conf_pct = round(confidence * 100) if confidence else 0

    regime_descriptions = {
        "TRENDING_UP": f"TRENDING_UP with {conf_pct}% conviction. Bull market conditions — trend-following strategies favored.",
        "TRENDING_DOWN": f"TRENDING_DOWN with {conf_pct}% conviction. Bear market conditions — trend-following shorts or mean-reversion longs at extremes.",
        "RANGING": f"RANGING with {conf_pct}% conviction. Sideways chop — mean reversion and grid strategies preferred.",
        "VOLATILE": f"VOLATILE with {conf_pct}% conviction. Choppy, high-energy market — reduce position sizes, widen stops.",
        "QUIET": f"QUIET with {conf_pct}% conviction. Low activity — patience required, watch for breakout setups.",
        "TRANSITIONING": f"TRANSITIONING with {conf_pct}% conviction. Regime shifting — reduce exposure until clarity emerges.",
    }

    return regime_descriptions.get(
        regime,
        f"Unknown regime '{regime}' with {conf_pct}% conviction."
    )


# ════════════════════════════════════════════════════════════════
# Next Move Generation
# ════════════════════════════════════════════════════════════════


def generate_next_moves(
    indicators: Dict,
    regime: Optional[str],
    signals_summary: Dict,
    symbol: str = "XAUUSD",
) -> List[Dict]:
    """
    PURPOSE: Generate list of "what to watch for" based on current market state.

    Produces actionable items describing what conditions would trigger trades
    or what the Brain is monitoring for next.

    Args:
        indicators: Dict with rsi, adx, atr, ema_20, ema_50
        regime: Current regime string
        signals_summary: Dict of strategy signals from last cycle
        symbol: Trading symbol

    Returns:
        List[Dict]: Next move objects with keys:
            strategy, action, condition, timeframe, probability

    CALLED BY: brain.py process_cycle
    """
    moves: List[Dict] = []
    rsi_val = indicators.get("rsi")
    adx_val = indicators.get("adx")
    atr_val = indicators.get("atr")
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")

    # RSI-based watchpoints
    if rsi_val is not None:
        if 30 < rsi_val < 35:
            moves.append({
                "strategy": "D",
                "action": "Potential BUY setup",
                "condition": f"RSI at {rsi_val} approaching oversold. If it drops below 30, Volatility Harvester may trigger.",
                "timeframe": "Next 1-3 candles",
                "probability": 0.55,
            })
        elif 65 < rsi_val < 70:
            moves.append({
                "strategy": "B",
                "action": "Watch for SELL setup",
                "condition": f"RSI at {rsi_val} approaching overbought. Mean-reversion sell setups forming.",
                "timeframe": "Next 1-3 candles",
                "probability": 0.50,
            })
        elif rsi_val <= 30:
            moves.append({
                "strategy": "D",
                "action": "BUY reversal watch",
                "condition": f"RSI at {rsi_val} in oversold territory. Watching for reversal confirmation.",
                "timeframe": "Immediate",
                "probability": 0.65,
            })
        elif rsi_val >= 70:
            moves.append({
                "strategy": "D",
                "action": "SELL exhaustion watch",
                "condition": f"RSI at {rsi_val} in overbought territory. Watching for exhaustion signal to short.",
                "timeframe": "Immediate",
                "probability": 0.60,
            })

    # EMA crossover watchpoints
    if ema_20 is not None and ema_50 is not None:
        gap = abs(ema_20 - ema_50)
        if gap < (ema_50 * 0.001):  # EMAs converging within 0.1%
            moves.append({
                "strategy": "A",
                "action": "EMA crossover pending",
                "condition": f"EMA20 and EMA50 converging (gap: {round(gap, 5)}). Potential regime shift imminent.",
                "timeframe": "Next 1-5 candles",
                "probability": 0.55,
            })

    # ADX-based watchpoints
    if adx_val is not None:
        if 20 < adx_val < 25:
            moves.append({
                "strategy": "A",
                "action": "Trend confirmation watch",
                "condition": f"ADX at {adx_val} near trend threshold (25). A push above could confirm trending regime.",
                "timeframe": "Next 1-3 candles",
                "probability": 0.50,
            })
        elif adx_val >= 40:
            moves.append({
                "strategy": "A",
                "action": "Trend continuation",
                "condition": f"ADX at {adx_val} — strong trend in play. Strategy A should capitalize on continuation.",
                "timeframe": "Active now",
                "probability": 0.75,
            })

    # Regime-based watchpoints
    if regime == "RANGING":
        moves.append({
            "strategy": "B",
            "action": "Grid levels active",
            "condition": "Ranging market. Mean Reversion grid levels are active. Watching for range extreme touches.",
            "timeframe": "Ongoing",
            "probability": 0.60,
        })
    elif regime == "TRANSITIONING":
        moves.append({
            "strategy": "ALL",
            "action": "Hold — regime shifting",
            "condition": "Market transitioning between regimes. Holding off on new entries until direction clarifies.",
            "timeframe": "Until clarity",
            "probability": 0.30,
        })

    # Strategy-specific notes
    for code, sig in signals_summary.items():
        if sig == "waiting_for_candle":
            moves.append({
                "strategy": code,
                "action": "Awaiting candle close",
                "condition": f"Strategy {code} waiting for next candle close to evaluate.",
                "timeframe": "Next candle",
                "probability": 0.40,
            })

    if not moves:
        moves.append({
            "strategy": "ALL",
            "action": "Monitoring",
            "condition": f"No immediate triggers on {symbol}. Monitoring for new candle or indicator threshold crossings.",
            "timeframe": "Next candle",
            "probability": 0.30,
        })

    return moves


# ════════════════════════════════════════════════════════════════
# Strategy Confidence Reasoning
# ════════════════════════════════════════════════════════════════


def assess_strategy_fitness(
    strategy_code: str,
    regime: Optional[str],
    indicators: Dict,
) -> Dict:
    """
    PURPOSE: Assess how well a strategy fits current market conditions.

    Returns a confidence score (0-1) and reasoning for each strategy
    based on the current regime and indicator state.

    Args:
        strategy_code: Strategy identifier (A, B, C, D, E)
        regime: Current market regime string
        indicators: Dict with rsi, adx, atr, ema_20, ema_50

    Returns:
        Dict with 'confidence' (float 0-1) and 'reason' (str)

    CALLED BY: brain.py process_cycle
    """
    adx_val = indicators.get("adx")
    rsi_val = indicators.get("rsi")

    # Strategy A — Trend Following
    if strategy_code == "A":
        if regime in ("TRENDING_UP", "TRENDING_DOWN"):
            if adx_val and adx_val >= 30:
                return {"confidence": 0.85, "reason": f"Strong trending regime (ADX {adx_val}). Ideal conditions for trend following."}
            elif adx_val and adx_val >= 25:
                return {"confidence": 0.65, "reason": f"Moderate trend (ADX {adx_val}). Acceptable for trend following with tighter risk."}
            else:
                return {"confidence": 0.4, "reason": f"Trend regime detected but ADX {adx_val} is weak. Caution warranted."}
        elif regime == "RANGING":
            return {"confidence": 0.2, "reason": "Ranging market — trend following will get whipsawed. Sitting this out."}
        else:
            return {"confidence": 0.35, "reason": f"Uncertain regime ({regime}). Trend following is risky without clear direction."}

    # Strategy B — Mean Reversion
    elif strategy_code == "B":
        if regime == "RANGING":
            return {"confidence": 0.8, "reason": "Ranging market — perfect for mean reversion. Grid levels should hold."}
        elif regime in ("TRENDING_UP", "TRENDING_DOWN"):
            if adx_val and adx_val >= 35:
                return {"confidence": 0.15, "reason": f"Strong trend (ADX {adx_val}). Mean reversion will fight the tape — high risk of stops."}
            else:
                return {"confidence": 0.4, "reason": f"Mild trend (ADX {adx_val}). Mean reversion possible at extremes but risky."}
        else:
            return {"confidence": 0.5, "reason": f"Mixed regime ({regime}). Mean reversion moderately viable."}

    # Strategy C — Session Breakout
    elif strategy_code == "C":
        if regime in ("TRANSITIONING", "QUIET"):
            return {"confidence": 0.7, "reason": "Low volatility / transitioning — session breakout has good potential."}
        elif regime in ("TRENDING_UP", "TRENDING_DOWN"):
            return {"confidence": 0.6, "reason": "Trending market may offer breakout continuations. Reasonable conditions."}
        elif regime == "RANGING":
            return {"confidence": 0.45, "reason": "Ranging market — breakouts likely to false-start. Reduced confidence."}
        else:
            return {"confidence": 0.5, "reason": f"Regime ({regime}) is neutral for breakout strategy."}

    # Strategy D — Momentum Scalper
    elif strategy_code == "D":
        if rsi_val is not None and (rsi_val <= 30 or rsi_val >= 70):
            conf = 0.75 if regime != "TRENDING_DOWN" or rsi_val <= 25 else 0.5
            zone = "oversold" if rsi_val <= 30 else "overbought"
            return {"confidence": conf, "reason": f"RSI {rsi_val} is {zone} — momentum scalp setup is active."}
        elif regime == "VOLATILE":
            return {"confidence": 0.65, "reason": "High volatility regime — momentum scalp can capture fast expansions."}
        else:
            return {"confidence": 0.35, "reason": "RSI in neutral zone, no extreme readings. Waiting for BB touch or RSI extreme."}

    # Strategy E — Range Scalper (Sideways)
    elif strategy_code == "E":
        if regime == "RANGING":
            return {"confidence": 0.82, "reason": "Ranging regime detected — ideal conditions for sideways scalping."}
        if regime in ("TRANSITIONING", "QUIET"):
            return {"confidence": 0.62, "reason": "Low directional commitment — range scalper can work with tighter risk."}
        if regime in ("TRENDING_UP", "TRENDING_DOWN"):
            if adx_val and adx_val >= 25:
                return {"confidence": 0.22, "reason": f"Trend strength is elevated (ADX {adx_val}). Sideways scalps are likely to get run over."}
            return {"confidence": 0.4, "reason": f"Directional bias exists but ADX {adx_val} is not extreme. Range scalps only at clear band extremes."}
        return {"confidence": 0.5, "reason": f"Mixed regime ({regime}). Sideways scalper is neutral until structure is clearer."}

    # Unknown strategy
    return {"confidence": 0.5, "reason": f"No specific assessment for strategy {strategy_code}."}
