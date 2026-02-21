"""
PURPOSE: Generates executable code from structured strategy rule definitions.

Takes the JSON output from NLStrategyParser and produces:
    - TradingView Pine Script v5 (for alerts and backtesting)
    - Python evaluation code (for the live engine via pandas-ta)
    - Webhook payload JSON template (for TradingView -> Hydra alerts)

CALLED BY:
    - api/routes_strategy_builder.py (included in parse responses)
    - nl_parser.py is invoked before this to create the strategy_def
"""

from typing import Any, Dict, List


class StrategyCodeGenerator:
    """
    PURPOSE: Converts structured strategy definitions into executable code.

    Stateless — each method takes a strategy_def dict and returns a string.

    CALLED BY: api/routes_strategy_builder.py
    """

    # ------------------------------------------------------------------ #
    #  Pine Script Generation
    # ------------------------------------------------------------------ #

    def generate_pine_script(self, strategy_def: Dict) -> str:
        """
        Generate a complete TradingView Pine Script v5 from a strategy definition.

        Produces:
            - strategy() declaration with commission
            - All indicator calculations
            - Entry and exit logic via strategy.entry() / strategy.exit()
            - alertcondition() with JSON webhook payload
            - plot() calls for each indicator
        """
        name = strategy_def.get("name", "Custom Strategy")
        action = strategy_def.get("action", "BUY")
        conditions = strategy_def.get("conditions", [])
        exit_conditions = strategy_def.get("exit_conditions", [])
        risk = strategy_def.get("risk", {})
        sl_atr_mult = risk.get("sl_atr_mult", 1.5)
        tp_atr_mult = risk.get("tp_atr_mult", 2.0)

        lines: List[str] = []

        # Header
        lines.append("//@version=5")
        lines.append(
            f'strategy("{name}", overlay=true, default_qty_type=strategy.percent_of_equity, '
            f"default_qty_value=10, commission_type=strategy.commission.percent, commission_value=0.1)"
        )
        lines.append("")

        # ATR for SL/TP
        lines.append("// ATR for dynamic stop-loss and take-profit")
        lines.append("atr_len = input.int(14, title='ATR Length')")
        lines.append("atr_val = ta.atr(atr_len)")
        lines.append("")

        # Collect required indicators
        indicators = self._collect_indicators(conditions + exit_conditions)

        # Indicator declarations
        lines.extend(self._pine_indicator_declarations(indicators))
        lines.append("")

        # Entry condition
        entry_parts = self._pine_conditions(conditions)
        entry_cond = " and\n     ".join(entry_parts) if entry_parts else "true"
        lines.append(f"// Entry condition — {action}")
        lines.append(f"entry_signal = {entry_cond}")
        lines.append("")

        # Exit condition
        exit_parts = self._pine_conditions(exit_conditions)
        if exit_parts:
            exit_cond = " and\n     ".join(exit_parts)
        else:
            # Default: opposite crossover or trailing ATR exit
            if action == "BUY":
                exit_cond = "ta.crossunder(close, ta.ema(close, 20))"
            else:
                exit_cond = "ta.crossover(close, ta.ema(close, 20))"
        lines.append("// Exit condition")
        lines.append(f"exit_signal = {exit_cond}")
        lines.append("")

        # Strategy logic
        direction = "strategy.long" if action in ("BUY", "CLOSE_SHORT") else "strategy.short"
        lines.append("// Strategy entries and exits")
        lines.append(f"sl_price = close - atr_val * {sl_atr_mult}" if action == "BUY" else
                     f"sl_price = close + atr_val * {sl_atr_mult}")
        lines.append(f"tp_price = close + atr_val * {tp_atr_mult}" if action == "BUY" else
                     f"tp_price = close - atr_val * {tp_atr_mult}")
        lines.append("")
        lines.append(f"if entry_signal")
        lines.append(f"    strategy.entry('Entry', {direction})")
        lines.append(
            f"    strategy.exit('Exit', from_entry='Entry', stop=sl_price, limit=tp_price)"
        )
        lines.append("")
        lines.append("if exit_signal")
        lines.append("    strategy.close_all()")
        lines.append("")

        # Webhook alert payload
        webhook_fields = self._pine_webhook_fields(indicators)
        lines.append("// Webhook alert message (JSON payload for JSR Hydra)")
        lines.append("alert_msg = '{' +")
        lines.append(f'    \'"action": "{action}",\' +')
        lines.append('    \'"symbol": "\' + syminfo.ticker + \'",\' +')
        lines.append('    \'"price": \' + str.tostring(close, "#.#####") + \'",\' +')
        for field in webhook_fields:
            lines.append(f"    {field} +")
        lines.append('    \'"timeframe": "\' + timeframe.period + \'"\' +')
        lines.append("    '}'")
        lines.append("")
        lines.append("alertcondition(entry_signal, title='Entry Signal', message=alert_msg)")
        lines.append("")

        # Plots
        lines.extend(self._pine_plots(indicators))

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Python Rule Generation
    # ------------------------------------------------------------------ #

    def generate_python_rule(self, strategy_def: Dict) -> str:
        """
        Generate Python evaluation code that can run in the JSR Hydra engine.

        Uses pandas-ta for indicator computation.  The generated function
        accepts a pandas DataFrame with OHLCV data and returns a signal dict.
        """
        name = strategy_def.get("name", "Custom Strategy")
        action = strategy_def.get("action", "BUY")
        conditions = strategy_def.get("conditions", [])
        exit_conditions = strategy_def.get("exit_conditions", [])
        risk = strategy_def.get("risk", {})
        sl_atr_mult = risk.get("sl_atr_mult", 1.5)
        tp_atr_mult = risk.get("tp_atr_mult", 2.0)
        timeframe = strategy_def.get("suggested_timeframe", "1H")

        lines: List[str] = []

        lines.append('"""')
        lines.append(f"Auto-generated Python strategy rule: {name}")
        lines.append(f"Action: {action} | Timeframe: {timeframe}")
        lines.append('"""')
        lines.append("")
        lines.append("import pandas as pd")
        lines.append("import pandas_ta as ta  # pip install pandas-ta")
        lines.append("from typing import Dict, Optional")
        lines.append("")
        lines.append("")
        lines.append(f'STRATEGY_NAME = "{name}"')
        lines.append(f'STRATEGY_ACTION = "{action}"')
        lines.append(f'STRATEGY_TIMEFRAME = "{timeframe}"')
        lines.append(f"SL_ATR_MULT = {sl_atr_mult}")
        lines.append(f"TP_ATR_MULT = {tp_atr_mult}")
        lines.append("")
        lines.append("")
        lines.append("def evaluate(df: pd.DataFrame) -> Optional[Dict]:")
        lines.append('    """')
        lines.append(f"    Evaluate strategy conditions on OHLCV DataFrame.")
        lines.append("")
        lines.append("    Args:")
        lines.append("        df: DataFrame with columns [open, high, low, close, volume]")
        lines.append("            Must have at least 60 rows for reliable indicator values.")
        lines.append("")
        lines.append("    Returns:")
        lines.append("        Signal dict or None if no signal.")
        lines.append('    """')
        lines.append('    if len(df) < 60:')
        lines.append('        return None')
        lines.append("")
        lines.append("    # --- Indicator computations ---")

        indicators = self._collect_indicators(conditions + exit_conditions)
        lines.extend(self._python_indicator_computations(indicators))
        lines.append("")

        # Entry conditions
        entry_py = self._python_conditions(conditions)
        if not entry_py:
            entry_py = ["True"]
        lines.append("    # --- Entry conditions ---")
        for i, cond in enumerate(entry_py):
            if i == 0:
                lines.append(f"    entry_signal = {cond}")
            else:
                lines.append(f"    entry_signal = entry_signal and {cond}")
        lines.append("")

        # Exit conditions
        exit_py = self._python_conditions(exit_conditions)
        if not exit_py:
            lines.append("    # --- Exit conditions (default: reverse crossover) ---")
            lines.append("    exit_signal = False  # Managed externally by engine SL/TP")
        else:
            lines.append("    # --- Exit conditions ---")
            for i, cond in enumerate(exit_py):
                if i == 0:
                    lines.append(f"    exit_signal = {cond}")
                else:
                    lines.append(f"    exit_signal = exit_signal and {cond}")
        lines.append("")

        # Return signal
        lines.append("    if not entry_signal:")
        lines.append("        return None")
        lines.append("")
        lines.append("    close = float(df['close'].iloc[-1])")
        lines.append("    atr = float(ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1])")
        lines.append("")
        if action == "BUY":
            lines.append("    sl_price = close - atr * SL_ATR_MULT")
            lines.append("    tp_price = close + atr * TP_ATR_MULT")
        else:
            lines.append("    sl_price = close + atr * SL_ATR_MULT")
            lines.append("    tp_price = close - atr * TP_ATR_MULT")
        lines.append("")
        lines.append("    return {")
        lines.append(f'        "strategy": STRATEGY_NAME,')
        lines.append(f'        "action": STRATEGY_ACTION,')
        lines.append(f'        "direction": "{action}",')
        lines.append('        "entry_price": close,')
        lines.append('        "sl_price": sl_price,')
        lines.append('        "tp_price": tp_price,')
        lines.append('        "confidence": 0.75,')
        lines.append('        "exit_now": exit_signal,')
        lines.append("    }")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Webhook Payload Template
    # ------------------------------------------------------------------ #

    def generate_webhook_payload_template(self, strategy_def: Dict) -> str:
        """
        Generate the JSON payload template for TradingView alert messages.

        The placeholders like {{ticker}} and {{close}} are TradingView
        built-in variables that get substituted at alert time.
        """
        import json as _json

        action = strategy_def.get("action", "BUY")
        name = strategy_def.get("name", "Custom Strategy")

        payload = {
            "action": action,
            "strategy": name,
            "symbol": "{{ticker}}",
            "price": "{{close}}",
            "timeframe": "{{interval}}",
            "high": "{{high}}",
            "low": "{{low}}",
            "volume": "{{volume}}",
            "time": "{{time}}",
        }

        # Add indicator values for the strategy's indicators
        indicators = self._collect_indicators(strategy_def.get("conditions", []) +
                                              strategy_def.get("exit_conditions", []))
        for ind_key in indicators:
            ind = indicators[ind_key]
            ind_name = ind.get("name", "").lower()
            period = ind.get("period", "")
            payload[f"{ind_name}_{period}"] = f"{{{{{ind_name}_{period}}}}}"

        return _json.dumps(payload, indent=2)

    # ------------------------------------------------------------------ #
    #  Private helpers — indicator collection
    # ------------------------------------------------------------------ #

    def _collect_indicators(self, conditions: List[Dict]) -> Dict[str, Dict]:
        """Build a deduplicated dict of required indicators from conditions list."""
        indicators: Dict[str, Dict] = {}
        for cond in conditions:
            for field in ("subject", "reference"):
                part = cond.get(field)
                if not isinstance(part, dict):
                    continue
                if part.get("type") != "indicator":
                    continue
                ind_name = str(part.get("name", "")).upper()
                period = int(part.get("period", 14))
                key = f"{ind_name}_{period}"
                if key not in indicators:
                    indicators[key] = {
                        "name": ind_name,
                        "period": period,
                        "source": part.get("source", "close"),
                    }
        return indicators

    # ------------------------------------------------------------------ #
    #  Private helpers — Pine Script
    # ------------------------------------------------------------------ #

    def _pine_indicator_declarations(self, indicators: Dict[str, Dict]) -> List[str]:
        """Return Pine Script variable declarations for each required indicator."""
        lines: List[str] = []
        lines.append("// Indicator declarations")
        for key, ind in indicators.items():
            name = ind["name"]
            period = ind["period"]
            src = ind.get("source", "close")
            var_name = key.lower()

            if name == "SMA":
                lines.append(f"{var_name} = ta.sma({src}, {period})")
            elif name == "EMA":
                lines.append(f"{var_name} = ta.ema({src}, {period})")
            elif name == "RSI":
                lines.append(f"{var_name} = ta.rsi({src}, {period})")
            elif name == "MACD":
                lines.append(f"[macd_line, signal_line, _] = ta.macd({src}, 12, 26, 9)")
            elif name in ("BB", "BBANDS", "BOLLINGER"):
                lines.append(
                    f"[bb_upper_{period}, bb_basis_{period}, bb_lower_{period}] = "
                    f"ta.bb({src}, {period}, 2.0)"
                )
            elif name == "ADX":
                lines.append(f"[{var_name}, _, _] = ta.dmi({period}, {period})")
            elif name == "ATR":
                lines.append(f"{var_name} = ta.atr({period})")
            elif name == "STOCH":
                lines.append(
                    f"[stoch_k_{period}, stoch_d_{period}] = ta.stoch(high, low, close, {period}, 3, 3)"
                )
            elif name == "CCI":
                lines.append(f"{var_name} = ta.cci({period})")
            elif name == "VWAP":
                lines.append(f"vwap_val = ta.vwap(hlc3)")
            else:
                lines.append(f"// TODO: {name} period={period} (manual implementation needed)")
        return lines

    def _pine_conditions(self, conditions: List[Dict]) -> List[str]:
        """Convert structured conditions to Pine Script boolean expressions."""
        parts: List[str] = []
        for cond in conditions:
            ctype = cond.get("type", "")
            subject = cond.get("subject", {})
            reference = cond.get("reference", {})
            operator = cond.get("operator", "")
            value = cond.get("value")
            direction = cond.get("direction", "")

            subj_var = self._pine_var(subject)
            ref_var = self._pine_var(reference) if reference else None

            if ctype in ("crossover",) or direction == "above":
                if ref_var:
                    parts.append(f"ta.crossover({subj_var}, {ref_var})")
                else:
                    parts.append(f"ta.crossover({subj_var}, {value})")
            elif ctype in ("crossunder",) or direction == "below":
                if ref_var:
                    parts.append(f"ta.crossunder({subj_var}, {ref_var})")
                else:
                    parts.append(f"ta.crossunder({subj_var}, {value})")
            elif ctype == "threshold":
                if operator in ("less_than", "below"):
                    parts.append(f"{subj_var} < {value}")
                elif operator in ("greater_than", "above"):
                    parts.append(f"{subj_var} > {value}")
                elif operator == "equals":
                    parts.append(f"{subj_var} == {value}")
                elif operator == "between":
                    v2 = cond.get("value2", value)
                    parts.append(f"({subj_var} >= {value} and {subj_var} <= {v2})")
            elif ctype == "slope":
                if direction == "rising":
                    parts.append(f"{subj_var} > {subj_var}[1]")
                elif direction == "falling":
                    parts.append(f"{subj_var} < {subj_var}[1]")
            else:
                # Fallback — use raw operator if available
                if value is not None:
                    parts.append(f"{subj_var} > {value}" if "above" in str(ctype) else f"{subj_var} != na")
        return parts

    def _pine_var(self, part: Dict) -> str:
        """Convert a subject/reference dict to a Pine Script variable name."""
        if not isinstance(part, dict):
            return "close"
        ptype = part.get("type", "")
        if ptype == "price":
            return part.get("field", "close")
        if ptype == "indicator":
            name = str(part.get("name", "")).upper()
            period = part.get("period", 14)
            key = f"{name}_{period}".lower()
            if name in ("BB", "BBANDS", "BOLLINGER"):
                return f"bb_basis_{period}"
            if name == "MACD":
                return "macd_line"
            if name == "VWAP":
                return "vwap_val"
            return key
        if ptype == "value":
            return str(part.get("value", 0))
        return "close"

    def _pine_webhook_fields(self, indicators: Dict[str, Dict]) -> List[str]:
        """Build Pine Script string concatenation lines for webhook JSON fields."""
        fields: List[str] = []
        for key, ind in indicators.items():
            var_name = key.lower()
            fields.append(
                f'    \'"{var_name}": \' + str.tostring({var_name}, "#.##") + \'",\' +'
            )
        return fields

    def _pine_plots(self, indicators: Dict[str, Dict]) -> List[str]:
        """Generate plot() calls for all indicators."""
        colors = {
            "SMA": "color.orange",
            "EMA": "color.blue",
            "RSI": "color.purple",
            "ADX": "color.yellow",
            "ATR": "color.gray",
        }
        lines: List[str] = []
        lines.append("// Visual plots")
        plotted_vwap = False
        for key, ind in indicators.items():
            name = ind["name"]
            var_name = key.lower()
            c = colors.get(name, "color.teal")
            if name in ("BB", "BBANDS", "BOLLINGER"):
                period = ind["period"]
                lines.append(
                    f"plot(bb_upper_{period}, color=color.red, title='BB Upper {period}')"
                )
                lines.append(
                    f"plot(bb_basis_{period}, color=color.gray, title='BB Mid {period}')"
                )
                lines.append(
                    f"plot(bb_lower_{period}, color=color.green, title='BB Lower {period}')"
                )
            elif name == "MACD":
                lines.append("// MACD is plotted in a separate pane (remove overlay=true above)")
            elif name == "VWAP":
                if not plotted_vwap:
                    lines.append("plot(vwap_val, color=color.yellow, title='VWAP')")
                    plotted_vwap = True
            elif name in ("RSI", "ADX", "CCI", "STOCH"):
                lines.append(f"// {name} plotted in a separate pane — add hline({var_name}) if needed")
            else:
                lines.append(f"plot({var_name}, color={c}, title='{key}')")
        return lines

    # ------------------------------------------------------------------ #
    #  Private helpers — Python
    # ------------------------------------------------------------------ #

    def _python_indicator_computations(self, indicators: Dict[str, Dict]) -> List[str]:
        """Return Python/pandas-ta indicator computation lines."""
        lines: List[str] = []
        for key, ind in indicators.items():
            name = ind["name"]
            period = ind["period"]
            src = ind.get("source", "close")
            var_name = key.lower()

            if name == "SMA":
                lines.append(f"    {var_name} = float(ta.sma(df['{src}'], length={period}).iloc[-1])")
            elif name == "EMA":
                lines.append(f"    {var_name} = float(ta.ema(df['{src}'], length={period}).iloc[-1])")
            elif name == "RSI":
                lines.append(f"    {var_name} = float(ta.rsi(df['{src}'], length={period}).iloc[-1])")
            elif name == "MACD":
                lines.append(f"    _macd = ta.macd(df['{src}'], fast=12, slow=26, signal=9)")
                lines.append(f"    macd_line = float(_macd['MACD_12_26_9'].iloc[-1])")
                lines.append(f"    macd_signal = float(_macd['MACDs_12_26_9'].iloc[-1])")
            elif name in ("BB", "BBANDS", "BOLLINGER"):
                lines.append(
                    f"    _bb = ta.bbands(df['{src}'], length={period}, std=2.0)"
                )
                lines.append(
                    f"    bb_upper_{period} = float(_bb['BBU_{period}_2.0'].iloc[-1])"
                )
                lines.append(
                    f"    bb_mid_{period} = float(_bb['BBM_{period}_2.0'].iloc[-1])"
                )
                lines.append(
                    f"    bb_lower_{period} = float(_bb['BBL_{period}_2.0'].iloc[-1])"
                )
            elif name == "ADX":
                lines.append(f"    _adx = ta.adx(df['high'], df['low'], df['close'], length={period})")
                lines.append(f"    {var_name} = float(_adx['ADX_{period}'].iloc[-1])")
            elif name == "ATR":
                lines.append(
                    f"    {var_name} = float(ta.atr(df['high'], df['low'], df['close'], length={period}).iloc[-1])"
                )
            elif name == "STOCH":
                lines.append(
                    f"    _stoch = ta.stoch(df['high'], df['low'], df['close'], k={period}, d=3, smooth_k=3)"
                )
                lines.append(f"    stoch_k_{period} = float(_stoch['STOCHk_{period}_3_3'].iloc[-1])")
                lines.append(f"    stoch_d_{period} = float(_stoch['STOCHd_{period}_3_3'].iloc[-1])")
            elif name == "CCI":
                lines.append(
                    f"    {var_name} = float(ta.cci(df['high'], df['low'], df['close'], length={period}).iloc[-1])"
                )
            elif name == "VWAP":
                lines.append("    vwap_val = float(ta.vwap(df['high'], df['low'], df['close'], df['volume']).iloc[-1])")
            else:
                lines.append(f"    # TODO: {name} period={period} — implement manually")
                lines.append(f"    {var_name} = float('nan')")
        return lines

    def _python_conditions(self, conditions: List[Dict]) -> List[str]:
        """Convert structured conditions to Python boolean expressions."""
        parts: List[str] = []
        for cond in conditions:
            ctype = cond.get("type", "")
            subject = cond.get("subject", {})
            reference = cond.get("reference", {})
            operator = cond.get("operator", "")
            value = cond.get("value")
            direction = cond.get("direction", "")

            subj_var = self._python_var(subject)
            ref_var = self._python_var(reference) if isinstance(reference, dict) and reference else None

            if ctype in ("crossover",) or direction == "above":
                # For Python we approximate crossover as: current > ref AND previous < ref
                # We need prev values — simplified to >= check
                if ref_var:
                    parts.append(f"{subj_var} > {ref_var}")
                elif value is not None:
                    parts.append(f"{subj_var} > {value}")
            elif ctype in ("crossunder",) or direction == "below":
                if ref_var:
                    parts.append(f"{subj_var} < {ref_var}")
                elif value is not None:
                    parts.append(f"{subj_var} < {value}")
            elif ctype == "threshold":
                if operator in ("less_than", "below") and value is not None:
                    parts.append(f"{subj_var} < {value}")
                elif operator in ("greater_than", "above") and value is not None:
                    parts.append(f"{subj_var} > {value}")
                elif operator == "between" and value is not None:
                    v2 = cond.get("value2", value)
                    parts.append(f"({subj_var} >= {value} and {subj_var} <= {v2})")
            elif ctype == "slope":
                # Require prev row for slope — add a note in generated code
                if direction == "rising":
                    parts.append(f"True  # slope rising ({subj_var}) — verify with prev bar")
                elif direction == "falling":
                    parts.append(f"True  # slope falling ({subj_var}) — verify with prev bar")
        return parts

    def _python_var(self, part: Dict) -> str:
        """Convert a subject/reference dict to a Python variable name."""
        if not isinstance(part, dict):
            return "df['close'].iloc[-1]"
        ptype = part.get("type", "")
        if ptype == "price":
            field = part.get("field", "close")
            return f"float(df['{field}'].iloc[-1])"
        if ptype == "indicator":
            name = str(part.get("name", "")).upper()
            period = part.get("period", 14)
            key = f"{name}_{period}".lower()
            if name in ("BB", "BBANDS", "BOLLINGER"):
                return f"bb_mid_{period}"
            if name == "MACD":
                return "macd_line"
            if name == "VWAP":
                return "vwap_val"
            return key
        if ptype == "value":
            return str(part.get("value", 0))
        return "float(df['close'].iloc[-1])"
