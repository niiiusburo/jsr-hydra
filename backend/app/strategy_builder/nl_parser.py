"""
PURPOSE: Natural language to structured trading strategy parser.

Converts plain English trading descriptions into structured JSON strategy
definitions using the existing LLMBrain infrastructure.

Examples:
    "Buy when price crosses above SMA44 and RSI is below 30"
    "Sell when EMA20 crosses below EMA50 and ADX is above 25"
    "Enter long when price touches lower Bollinger Band and RSI < 35"

CALLED BY:
    - api/routes_strategy_builder.py (parse and refine endpoints)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.brain.prompts import STRATEGY_BUILDER_SYSTEM, STRATEGY_BUILDER_USER
from app.utils.logger import get_logger

logger = get_logger("strategy_builder.nl_parser")


class NLStrategyParser:
    """
    PURPOSE: Parses natural language trading descriptions into structured rules.

    Reuses the existing LLMBrain instance so no new API client is created.
    All LLM calls go through the proven _call_gpt_with_retry() pipeline.

    CALLED BY: api/routes_strategy_builder.py
    """

    def __init__(self, llm_brain: Any) -> None:
        self._llm = llm_brain

    async def parse(self, user_input: str, context: Optional[Dict] = None) -> Dict:
        """
        Parse natural language into a structured strategy definition.

        Args:
            user_input: e.g. "Buy when price crosses above SMA44 and RSI < 30"
            context: Optional dict with symbol, current indicators, timeframe, etc.

        Returns:
            Structured strategy definition dict with conditions, Pine Script,
            Python code, risk parameters, confidence, and warnings.
        """
        context = context or {}
        symbol = context.get("symbol", "BTCUSD")
        market_context = context.get("market_context", "No additional market context provided.")

        user_prompt = STRATEGY_BUILDER_USER.format(
            user_input=user_input,
            symbol=symbol,
            market_context=market_context,
        )

        logger.info(
            "nl_parse_start",
            input_length=len(user_input),
            symbol=symbol,
        )

        response = await self._llm._call_gpt_with_retry(
            STRATEGY_BUILDER_SYSTEM,
            user_prompt,
            max_tokens=1800,
        )

        if not response or self._llm._is_error_content(response):
            logger.error("nl_parse_llm_failed", response_preview=str(response)[:120])
            return self._error_result(user_input, response)

        parsed = self._llm._parse_json_response(response)
        if not parsed:
            logger.warning("nl_parse_json_failed", response_preview=response[:120])
            return self._error_result(user_input, "[JSON parse failure] LLM response was not valid JSON.")

        # Normalise and fill mandatory fields
        parsed = self._normalise(parsed, user_input, symbol)

        logger.info(
            "nl_parse_complete",
            strategy_name=parsed.get("name"),
            action=parsed.get("action"),
            conditions=len(parsed.get("conditions", [])),
            confidence=parsed.get("confidence"),
        )
        return parsed

    async def refine(self, existing_strategy: Dict, feedback: str) -> Dict:
        """
        Refine an existing parsed strategy with additional natural language input.

        Args:
            existing_strategy: Previously parsed strategy definition dict.
            feedback: e.g. "also add an EMA20 filter and tighten the SL"

        Returns:
            Updated structured strategy definition dict.
        """
        existing_json = json.dumps(existing_strategy, indent=2)

        refine_prompt = (
            f"You previously produced this strategy definition:\n\n"
            f"```json\n{existing_json}\n```\n\n"
            f"The user wants to refine it with this additional instruction:\n\n"
            f"\"{feedback}\"\n\n"
            f"Return a complete, updated strategy definition JSON incorporating the requested changes. "
            f"Keep all existing conditions unless the user explicitly asks to remove them."
        )

        logger.info("nl_refine_start", feedback_length=len(feedback))

        response = await self._llm._call_gpt_with_retry(
            STRATEGY_BUILDER_SYSTEM,
            refine_prompt,
            max_tokens=1800,
        )

        if not response or self._llm._is_error_content(response):
            logger.error("nl_refine_llm_failed", response_preview=str(response)[:120])
            return self._error_result(feedback, response)

        parsed = self._llm._parse_json_response(response)
        if not parsed:
            return self._error_result(feedback, "[JSON parse failure] LLM response was not valid JSON.")

        original_input = existing_strategy.get("description", "")
        parsed = self._normalise(parsed, f"{original_input} + {feedback}", existing_strategy.get("symbol", "BTCUSD"))

        logger.info(
            "nl_refine_complete",
            strategy_name=parsed.get("name"),
            conditions=len(parsed.get("conditions", [])),
        )
        return parsed

    # ------------------------------------------------------------------ #
    #  Private helpers
    # ------------------------------------------------------------------ #

    def _normalise(self, parsed: Dict, user_input: str, symbol: str) -> Dict:
        """Fill in missing mandatory fields and ensure consistent structure."""
        if not parsed.get("name"):
            parsed["name"] = "Custom Strategy"

        parsed.setdefault("description", f"Generated from: {user_input}")
        parsed.setdefault("symbol", symbol)
        parsed.setdefault("action", "BUY")
        parsed.setdefault("conditions", [])
        parsed.setdefault("exit_conditions", [])
        parsed.setdefault("risk", {"sl_atr_mult": 1.5, "tp_atr_mult": 2.0})
        parsed.setdefault("suggested_timeframe", "1H")
        parsed.setdefault("confidence", 0.75)
        parsed.setdefault("warnings", [])
        parsed.setdefault("pine_script", "")
        parsed.setdefault("python_code", "")
        parsed["created_at"] = datetime.now(timezone.utc).isoformat()
        return parsed

    def _error_result(self, user_input: str, error_msg: Any) -> Dict:
        """Return a safe fallback result when parsing fails."""
        return {
            "name": "Parse Error",
            "description": f"Failed to parse: {user_input}",
            "conditions": [],
            "action": "BUY",
            "exit_conditions": [],
            "risk": {"sl_atr_mult": 1.5, "tp_atr_mult": 2.0},
            "suggested_timeframe": "1H",
            "confidence": 0.0,
            "warnings": [str(error_msg or "Unknown LLM error")],
            "pine_script": "",
            "python_code": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "error": True,
        }
