"""
PURPOSE: Thought generation templates for JSR Hydra Brain.

Generates human-readable brain "thoughts" — the inner monologue of a
confident but cautious quantitative trader thinking out loud. These thoughts
are displayed in the Brain dashboard and logs to give the system a
personality and make its reasoning transparent.

CALLED BY: brain/brain.py — on market events, signals, trades, regime changes
"""

from typing import Optional

from app.utils.logger import get_logger

logger = get_logger("brain.prompts")

# Strategy descriptions for richer thoughts
STRATEGY_DESC = {
    "A": "Trend Following (EMA crossover + ADX)",
    "B": "Mean Reversion (Bollinger + Z-score)",
    "C": "Session Breakout",
    "D": "Momentum Scalper (BB + RSI)",
    "E": "Range Scalper (Sideways)",
}


def _rsi_description(rsi: Optional[float]) -> str:
    """Return a human-readable RSI condition description."""
    if rsi is None:
        return "RSI unavailable"
    if rsi < 20:
        return f"extremely oversold (RSI {rsi:.1f})"
    if rsi < 30:
        return f"deeply oversold (RSI {rsi:.1f})"
    if rsi < 40:
        return f"mildly oversold (RSI {rsi:.1f})"
    if rsi < 60:
        return f"neutral territory (RSI {rsi:.1f})"
    if rsi < 70:
        return f"mildly overbought (RSI {rsi:.1f})"
    if rsi < 80:
        return f"overbought (RSI {rsi:.1f})"
    return f"extremely overbought (RSI {rsi:.1f})"


def _adx_description(adx: Optional[float]) -> str:
    """Return a human-readable ADX trend strength description."""
    if adx is None:
        return ""
    if adx < 20:
        return f"weak trend (ADX {adx:.1f})"
    if adx < 30:
        return f"developing trend (ADX {adx:.1f})"
    if adx < 40:
        return f"strong trend (ADX {adx:.1f})"
    return f"very strong trend (ADX {adx:.1f})"


def _regime_outlook(regime: str) -> str:
    """Return a short outlook phrase for a regime."""
    outlooks = {
        "TRENDING_UP": "Momentum is bullish",
        "TRENDING_DOWN": "Bears are in control",
        "RANGING": "Price is choppy and range-bound",
        "VOLATILE": "Wild swings — high risk, high reward",
        "QUIET": "Markets are calm — patience needed",
        "TRANSITIONING": "Regime is shifting — staying nimble",
    }
    return outlooks.get(regime, f"Market is in {regime} mode")


def market_open_thought(indicators: dict, regime: str) -> str:
    """
    PURPOSE: Generate a thought when a new trading day opens.

    Summarizes the opening regime, key indicator levels, and which
    strategies the brain is watching closely.

    Args:
        indicators: Dict with keys like rsi, adx, atr, ema20, ema50, price.
        regime: Current market regime string.

    Returns:
        str: A conversational thought about market open conditions.

    CALLED BY: brain/brain.py — on daily open event
    """
    rsi = indicators.get("rsi")
    adx = indicators.get("adx")
    atr = indicators.get("atr")
    price = indicators.get("price")

    parts = [f"New trading day."]

    symbol = indicators.get("symbol", "EURUSD")
    if price is not None:
        parts.append(f"{symbol} opened at {price:.5f} in a {regime} regime")
        if adx is not None:
            parts[-1] += f" ({_adx_description(adx)})"
        parts[-1] += "."
    else:
        parts.append(f"Market opened in a {regime} regime.")

    if rsi is not None:
        parts.append(f"RSI at {rsi:.1f} signals {_rsi_description(rsi).split('(')[0].strip()} conditions.")

    # Strategy outlook based on regime
    if regime in ("TRENDING_UP", "TRENDING_DOWN"):
        parts.append(
            "I'll be watching Strategy A closely for trend continuation setups, "
            "and Strategy D for volatility entries near the Bollinger Bands."
        )
    elif regime == "RANGING":
        parts.append(
            "Ranging market favors Strategy B for mean reversion plays. "
            "Strategy A will likely stay quiet until a breakout occurs."
        )
    elif regime == "VOLATILE":
        parts.append(
            "High volatility — Strategy D's territory. "
            "Will be cautious with position sizing."
        )
    elif regime == "QUIET":
        parts.append(
            "Low volatility environment. Fewer signals expected. "
            "Strategy C may catch a breakout if one develops."
        )
    else:
        parts.append(
            "Regime is in transition — all strategies on standby, "
            "waiting for clarity before committing."
        )

    return " ".join(parts)


def new_candle_thought(timeframe: str, indicators: dict, regime: str, signals: list) -> str:
    """
    PURPOSE: Generate a thought when a new candle completes.

    Describes the latest price action, indicator movements, and any
    signal activity across strategies.

    Args:
        timeframe: Candle timeframe (e.g., "H1", "M15").
        indicators: Dict with indicator values.
        regime: Current market regime string.
        signals: List of signal dicts from strategies (may be empty).

    Returns:
        str: A conversational thought about the new candle.

    CALLED BY: brain/brain.py — on new candle event
    """
    ema20 = indicators.get("ema20")
    ema50 = indicators.get("ema50")
    rsi = indicators.get("rsi")
    adx = indicators.get("adx")
    price = indicators.get("price")

    parts = [f"New {timeframe} candle."]

    # Price and EMA commentary
    if price is not None and ema20 is not None and ema50 is not None:
        if ema20 > ema50:
            ema_status = "EMA20 above EMA50 — bullish alignment"
        elif ema20 < ema50:
            ema_status = "EMA20 below EMA50 — bearish alignment"
        else:
            ema_status = "EMAs converging — potential crossover forming"

        parts.append(
            f"Price at {price:.5f}. EMA20 ({ema20:.3f}) vs EMA50 ({ema50:.3f}). "
            f"{ema_status}."
        )
    elif price is not None:
        parts.append(f"Price at {price:.5f}.")

    # RSI and ADX
    if rsi is not None:
        parts.append(f"RSI reading {_rsi_description(rsi)}.")

    # Strategy signals
    if signals:
        signal_names = [f"Strategy {s.get('strategy', '?')} ({s.get('direction', '?')})" for s in signals]
        parts.append(f"Active signals: {', '.join(signal_names)}.")
    else:
        parts.append("No strategy signals this candle. Waiting for setups to develop.")

    return " ".join(parts)


def signal_generated_thought(strategy: str, signal: dict, indicators: dict) -> str:
    """
    PURPOSE: Generate a thought when a strategy fires a signal.

    Describes the signal details, entry conditions, and risk/reward.

    Args:
        strategy: Strategy code (A, B, C, D).
        signal: Dict with keys: direction, sl_price, tp_price, confidence, reason.
        indicators: Dict with current indicator values.

    Returns:
        str: A conversational thought about the new signal.

    CALLED BY: brain/brain.py — on signal generation event
    """
    direction = signal.get("direction", "?")
    sl = signal.get("sl_price", 0)
    tp = signal.get("tp_price", 0)
    confidence = signal.get("confidence", 0)
    reason = signal.get("reason", "")
    price = indicators.get("price", 0)
    rsi = indicators.get("rsi")
    bb_lower = indicators.get("bb_lower")
    bb_upper = indicators.get("bb_upper")

    desc = STRATEGY_DESC.get(strategy, f"Strategy {strategy}")

    parts = [f"Strategy {strategy} fired a {direction} signal!"]

    # Indicator context
    context_bits = []
    if rsi is not None:
        context_bits.append(f"RSI at {rsi:.1f} ({_rsi_description(rsi).split('(')[0].strip()})")
    if direction == "BUY" and bb_lower is not None:
        context_bits.append(f"price near lower BB at {bb_lower:.4f}")
    elif direction == "SELL" and bb_upper is not None:
        context_bits.append(f"price near upper BB at {bb_upper:.4f}")

    if context_bits:
        parts.append(f"{' with '.join(context_bits)}.")

    # Entry, SL, TP
    if price and sl and tp:
        parts.append(f"Entry at {price:.5f}, SL at {sl:.5f}, TP at {tp:.5f}.")

        # Risk/reward calculation
        risk = abs(price - sl)
        reward = abs(tp - price)
        if risk > 0:
            rr = reward / risk
            parts.append(f"Risk/reward looks {'favorable' if rr >= 1.0 else 'tight'} at 1:{rr:.1f}.")

    parts.append(f"Confidence: {confidence:.0%}.")

    if reason:
        parts.append(f"Reason: {reason}")

    return " ".join(parts)


def trade_executed_thought(strategy: str, trade_result: dict) -> str:
    """
    PURPOSE: Generate a thought when a trade is actually executed.

    Confirms the trade details and expresses the brain's sentiment.

    Args:
        strategy: Strategy code (A, B, C, D).
        trade_result: Dict with keys: direction, symbol, lots, entry_price,
                      stop_loss, take_profit, ticket, is_simulated.

    Returns:
        str: A conversational thought about the executed trade.

    CALLED BY: brain/brain.py — on trade execution event
    """
    direction = trade_result.get("direction", "?")
    symbol = trade_result.get("symbol", "?")
    lots = trade_result.get("lots", 0.01)
    entry = trade_result.get("entry_price", 0)
    sl = trade_result.get("stop_loss", 0)
    tp = trade_result.get("take_profit", 0)
    ticket = trade_result.get("ticket", "N/A")
    simulated = trade_result.get("is_simulated", False)

    sim_tag = " [SIMULATED]" if simulated else ""

    parts = [
        f"Trade executed!{sim_tag} {direction} {symbol} {lots} lots at {entry:.5f} "
        f"(ticket #{ticket})."
    ]

    if sl and tp:
        parts.append(f"Stop loss at {sl:.5f}, take profit at {tp:.5f}.")

    parts.append("Let's see how this plays out.")

    return " ".join(parts)


def trade_closed_thought(strategy: str, trade_result: dict, learnings: str) -> str:
    """
    PURPOSE: Generate a thought when a trade closes.

    Describes the outcome, profit/loss, and any lessons learned.

    Args:
        strategy: Strategy code (A, B, C, D).
        trade_result: Dict with keys: ticket, profit, direction, entry_price,
                      exit_price, won.
        learnings: Human-readable string describing what the brain learned.

    Returns:
        str: A conversational thought about the closed trade.

    CALLED BY: brain/brain.py — on trade close event
    """
    ticket = trade_result.get("ticket", "N/A")
    profit = trade_result.get("profit", 0.0)
    won = trade_result.get("won", profit > 0)
    symbol = trade_result.get("symbol", "")
    entry = trade_result.get("entry_price", 0)
    exit_price = trade_result.get("exit_price", 0)

    if won:
        sentiment = "Nice win!"
        profit_str = f"+${profit:.2f}"
    else:
        sentiment = "Tough break."
        profit_str = f"-${abs(profit):.2f}"

    parts = [
        f"Trade #{ticket} closed at {profit_str}. {sentiment}"
    ]

    if entry and exit_price:
        # Pip multiplier depends on instrument type
        sym = symbol.upper() if symbol else ""
        if any(c in sym for c in ("BTC", "ETH", "LTC", "XRP")):
            pip_mult = 1.0       # Crypto: 1 pip = $1
            fmt = f"({entry:.2f} -> {exit_price:.2f})"
        elif "XAU" in sym or "GOLD" in sym:
            pip_mult = 100.0     # Gold: 1 pip = 0.01
            fmt = f"({entry:.2f} -> {exit_price:.2f})"
        elif "JPY" in sym:
            pip_mult = 100.0     # JPY: 1 pip = 0.01
            fmt = f"({entry:.3f} -> {exit_price:.3f})"
        else:
            pip_mult = 10000.0   # Standard forex: 1 pip = 0.0001
            fmt = f"({entry:.5f} -> {exit_price:.5f})"
        pips = abs(exit_price - entry) * pip_mult
        parts.append(f"Moved {pips:.1f} pips from entry {fmt}.")

    if learnings:
        parts.append(f"Lesson: {learnings}")

    return " ".join(parts)


def regime_change_thought(old_regime: str, new_regime: str, implications: dict) -> str:
    """
    PURPOSE: Generate a thought when the market regime changes.

    Describes the shift, its implications for each strategy, and
    any allocation adjustments the brain is considering.

    Args:
        old_regime: Previous regime string.
        new_regime: New regime string.
        implications: Dict with strategy implications, e.g.:
                      {"favored": ["B"], "unfavored": ["A"],
                       "adjustments": {"A": -0.1, "B": +0.1}}

    Returns:
        str: A conversational thought about the regime change.

    CALLED BY: brain/brain.py — on regime change event
    """
    parts = [f"Regime shift detected: {old_regime} -> {new_regime}."]
    parts.append(f"{_regime_outlook(new_regime)}.")

    favored = implications.get("favored", [])
    unfavored = implications.get("unfavored", [])

    if favored:
        strat_names = [f"Strategy {s}" for s in favored]
        parts.append(f"This favors {', '.join(strat_names)}.")

    if unfavored:
        strat_names = [f"Strategy {s}" for s in unfavored]
        parts.append(f"Reducing confidence in {', '.join(strat_names)}.")

    adjustments = implications.get("adjustments", {})
    if adjustments:
        adj_parts = []
        for strat, adj in adjustments.items():
            direction = "up" if adj > 0 else "down"
            adj_parts.append(f"{strat} {direction} {abs(adj)*100:.0f}%")
        parts.append(f"Adjusting mental allocations: {', '.join(adj_parts)}.")

    return " ".join(parts)


def periodic_summary_thought(brain_state: dict) -> str:
    """
    PURPOSE: Generate a periodic check-in thought (every ~5 minutes).

    Summarizes current market state, active positions, and system health.

    Args:
        brain_state: Dict with keys: regime, signal_count, strategy_count,
                     balance, drawdown_pct, open_trades, last_trade_ago.

    Returns:
        str: A conversational check-in thought.

    CALLED BY: brain/brain.py — on periodic timer
    """
    regime = brain_state.get("regime", "UNKNOWN")
    strategy_count = brain_state.get("strategy_count", 4)
    balance = brain_state.get("balance")
    drawdown_pct = brain_state.get("drawdown_pct", 0.0)
    open_trades = brain_state.get("open_trades", 0)
    total_trades_today = brain_state.get("total_trades_today", 0)

    parts = [f"Periodic check-in. Market still in {regime}."]

    if open_trades > 0:
        parts.append(f"{open_trades} trade{'s' if open_trades > 1 else ''} currently open.")
    else:
        parts.append("No open trades.")

    parts.append(f"{strategy_count} strategies monitoring.")

    if total_trades_today > 0:
        parts.append(f"{total_trades_today} trade{'s' if total_trades_today > 1 else ''} executed today.")

    if balance is not None:
        parts.append(f"Account balance: ${balance:,.2f}.")

    if drawdown_pct is not None:
        if drawdown_pct < 1.0:
            parts.append(f"Drawdown: {drawdown_pct:.2f}%. All systems nominal.")
        elif drawdown_pct < 3.0:
            parts.append(f"Drawdown: {drawdown_pct:.2f}%. Monitoring closely.")
        else:
            parts.append(f"Drawdown: {drawdown_pct:.2f}%. Elevated — tightening risk controls.")

    return " ".join(parts)


def risk_event_thought(event_type: str, details: dict) -> str:
    """
    PURPOSE: Generate a thought when a risk event occurs.

    Describes the risk event and the brain's response — tightening
    controls, halting trading, or alerting the operator.

    Args:
        event_type: Type of risk event (e.g., "DAILY_LOSS_LIMIT",
                    "MAX_DRAWDOWN", "CONSECUTIVE_LOSSES", "KILL_SWITCH").
        details: Dict with event-specific details like threshold, current_value.

    Returns:
        str: A conversational thought about the risk event.

    CALLED BY: brain/brain.py — on risk management events
    """
    threshold = details.get("threshold")
    current = details.get("current_value")
    strategy = details.get("strategy")

    templates = {
        "DAILY_LOSS_LIMIT": (
            f"Risk alert: Daily loss approaching {threshold}% threshold "
            f"(currently at {current:.2f}%). "
            "Tightening position sizing and increasing SL buffers. "
            f"Will halt trading at {(threshold or 5.0):.0f}%."
            if threshold and current else
            "Risk alert: Daily loss limit approaching. Tightening position sizing."
        ),
        "MAX_DRAWDOWN": (
            f"CRITICAL: Maximum drawdown hit {current:.2f}% "
            f"(limit: {threshold}%). "
            "Kill switch engaged. All trading halted until manual review."
            if threshold and current else
            "CRITICAL: Maximum drawdown limit hit. Trading halted."
        ),
        "CONSECUTIVE_LOSSES": (
            f"Warning: Strategy {strategy} has hit {int(current) if current else '?'} consecutive losses. "
            "Pausing this strategy and reviewing recent trade patterns. "
            "Something may have changed in the market structure."
            if strategy and current else
            "Warning: Consecutive loss streak detected. Reviewing patterns."
        ),
        "KILL_SWITCH": (
            "KILL SWITCH ACTIVATED. All trading operations immediately halted. "
            f"Reason: {details.get('reason', 'Manual trigger or safety threshold breached')}. "
            "Awaiting manual intervention to resume."
        ),
        "MARGIN_WARNING": (
            f"Margin warning: Free margin at {current:.2f}%. "
            "Reducing exposure and avoiding new positions until margin improves."
            if current else
            "Margin warning: Free margin is low. Reducing exposure."
        ),
    }

    thought = templates.get(
        event_type,
        f"Risk event detected: {event_type}. Details: {details}. Staying cautious."
    )

    return thought


# ---------------------------------------------------------------------------
# STRUCTURED LLM ANALYSIS PROMPTS
# Adapted from TradingAgents multi-agent debate pattern (single-call variant)
# ---------------------------------------------------------------------------

BULL_BEAR_DEBATE_SYSTEM = """You are a senior market analyst conducting an internal bull vs bear debate.
You will argue BOTH sides of a trade, then render a verdict.

You MUST respond in this exact JSON format and nothing else:
{
  "bull_case": {
    "thesis": "<2-3 sentence bullish argument>",
    "key_evidence": ["<point1>", "<point2>", "<point3>"],
    "confidence": <0.0 to 1.0>
  },
  "bear_case": {
    "thesis": "<2-3 sentence bearish argument>",
    "key_evidence": ["<point1>", "<point2>", "<point3>"],
    "confidence": <0.0 to 1.0>
  },
  "verdict": {
    "direction": "<BULLISH|BEARISH|NEUTRAL>",
    "conviction": <0.0 to 1.0>,
    "reasoning": "<1-2 sentences on why this side wins>"
  }
}

Rules:
- Be specific: cite actual indicator values, price levels, regime context
- Bull and bear confidence should NOT sum to 1.0 — they are independent
- Verdict conviction should reflect how lopsided the evidence is
- If the case is genuinely unclear, set conviction below 0.3
- Do NOT add any text outside the JSON object"""

BULL_BEAR_DEBATE_USER = """Conduct a bull vs bear analysis for {symbol}:

Current price: {price}
Regime: {regime}
RSI: {rsi}
ADX: {adx}
ATR: {atr}
EMA20: {ema_20}
EMA50: {ema_50}
Spread: {spread}
Account balance: ${balance:.2f}
Open positions: {open_positions}
Today's P&L: ${daily_pnl:.2f}"""


SIGNAL_EXTRACTION_SYSTEM = """You are a quantitative signal processor.
Given market analysis and debate results, produce a trading signal.

You MUST respond in this exact JSON format and nothing else:
{
  "signal": "<BUY|SELL|HOLD>",
  "confidence": <0.0 to 1.0>,
  "strategy_preferences": {
    "A": <-1.0 to 1.0>,
    "B": <-1.0 to 1.0>,
    "C": <-1.0 to 1.0>,
    "D": <-1.0 to 1.0>,
    "E": <-1.0 to 1.0>
  },
  "risk_adjustment": "<TIGHTEN|NORMAL|LOOSEN>",
  "key_levels": {
    "support": <price or null>,
    "resistance": <price or null>
  },
  "reasoning": "<1 sentence>"
}

Strategy reference:
A = Trend Following (EMA crossover + ADX) — favored in trending regimes
B = Mean Reversion (Bollinger + Z-score) — favored in ranging regimes
C = Session Breakout — favored in quiet-to-volatile transitions
D = Momentum Scalper (BB + RSI) — favored in volatile regimes
E = Range Scalper — favored in sideways markets

strategy_preferences: positive = favor, negative = disfavor, 0 = neutral
risk_adjustment: TIGHTEN = reduce lot sizes, LOOSEN = increase, NORMAL = no change

Do NOT add any text outside the JSON object."""

SIGNAL_EXTRACTION_USER = """Extract a trading signal from this analysis:

Bull case: {bull_thesis} (confidence: {bull_confidence})
Bear case: {bear_thesis} (confidence: {bear_confidence})
Verdict: {verdict_direction} (conviction: {verdict_conviction})
Reasoning: {verdict_reasoning}

Current regime: {regime}
RSI: {rsi}
ADX: {adx}
Current drawdown: {drawdown_pct:.2f}%"""


TRADE_REFLECTION_SYSTEM = """You are a trading performance analyst.
Review this completed trade and extract structured lessons.

You MUST respond in this exact JSON format and nothing else:
{
  "outcome_quality": "<GOOD_ENTRY_GOOD_EXIT|GOOD_ENTRY_BAD_EXIT|BAD_ENTRY_GOOD_EXIT|BAD_ENTRY_BAD_EXIT>",
  "root_cause": "<1 sentence: what drove the outcome>",
  "lesson": "<1 sentence: actionable takeaway>",
  "strategy_adjustment": {
    "strategy": "<A|B|C|D|E>",
    "direction": "<BOOST|PENALIZE|NEUTRAL>",
    "magnitude": <0.0 to 1.0>
  },
  "regime_note": "<1 sentence: how regime affected this trade>"
}

Do NOT add any text outside the JSON object."""

TRADE_REFLECTION_USER = """Review this trade:

Symbol: {symbol}
Strategy: {strategy}
Direction: {direction}
Entry: {entry_price}
Exit: {exit_price}
P&L: ${profit:.2f}
Regime at entry: {regime}
Win/Loss: {outcome}"""


# ---------------------------------------------------------------------------
# STRATEGY BUILDER PROMPTS
# Natural language -> structured trading rule conversion
# ---------------------------------------------------------------------------

STRATEGY_BUILDER_SYSTEM = """You are a quantitative trading strategy parser. Convert natural language trading descriptions into structured JSON strategy definitions.

Available indicators: SMA, EMA, RSI, MACD, Bollinger Bands (BB), ADX, ATR, Stochastic (STOCH), CCI, VWAP, Ichimoku
Available condition types: crossover, crossunder, threshold, between, slope
Available actions: BUY, SELL, CLOSE_LONG, CLOSE_SHORT

You MUST respond with ONLY valid JSON matching this exact schema (no extra text, no markdown fences):
{
  "name": "short descriptive name (5-8 words max)",
  "conditions": [
    {
      "type": "crossover|crossunder|threshold|between|slope",
      "subject": {
        "type": "price|indicator",
        "field": "close|high|low|open",
        "name": "SMA|EMA|RSI|MACD|BB|ADX|ATR|STOCH|CCI|VWAP",
        "period": 14,
        "source": "close"
      },
      "reference": {
        "type": "indicator|value",
        "name": "SMA|EMA|RSI|etc",
        "period": 44,
        "source": "close"
      },
      "operator": "greater_than|less_than|between|equals",
      "value": 30,
      "value2": null,
      "direction": "above|below|rising|falling"
    }
  ],
  "action": "BUY|SELL",
  "exit_conditions": [
    {
      "type": "crossunder",
      "subject": {"type": "price", "field": "close"},
      "reference": {"type": "indicator", "name": "SMA", "period": 20, "source": "close"},
      "direction": "below"
    }
  ],
  "risk": {
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 2.0
  },
  "suggested_timeframe": "1H|4H|1D|15M|5M",
  "confidence": 0.85,
  "warnings": ["list any concerns about the strategy here"]
}

Rules:
- If period is not specified, use standard defaults: RSI=14, MACD=12/26/9, BB=20, SMA/EMA=20, ADX=14, ATR=14, STOCH=14, CCI=20
- Always include at least one exit_condition even if the user does not specify one
- For crossover/crossunder conditions: the subject crosses the reference
- For threshold conditions: subject compared to a numeric value via operator
- Set confidence based on strategy quality (0.5=basic, 0.75=solid, 0.9=well-defined)
- Include warnings for aggressive thresholds, ambiguous inputs, or missing info
- If the user mentions "the orange/blue/green line" without specifying which indicator, add a warning
- Do NOT wrap the JSON in markdown code fences
- Output ONLY the JSON object, nothing else"""

STRATEGY_BUILDER_USER = """Parse this trading strategy description into a structured JSON definition:

Description: {user_input}

Symbol context: {symbol}
Market context: {market_context}

Remember: output ONLY the JSON object, no other text."""


PINE_SCRIPT_GENERATOR_SYSTEM = """You are a Pine Script v5 code generator. Generate complete, working TradingView Pine Script from a structured strategy definition JSON.

Requirements:
- Use //@version=5
- Use strategy() for backtestable scripts (overlay=true)
- Include all indicator calculations using ta.* built-ins
- Include strategy.entry() and strategy.exit() calls with ATR-based SL/TP
- Include alertcondition() with a JSON webhook payload containing action, symbol ({{ticker}}), price ({{close}}), and all indicator values
- Include plot() calls for overlay indicators
- Add commission and default_qty settings to strategy()
- The webhook JSON must be a valid JSON string built with str.tostring() for numerics
- Output only the Pine Script code, no markdown fences"""
