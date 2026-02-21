"""
PURPOSE: Chart Vision Analysis for JSR Hydra.

Analyzes TradingView chart screenshots using vision-capable LLMs (GPT-4o).
Identifies indicators, patterns, key levels, and suggests trading strategies
based on the visual content of the chart image.

CALLED BY: api/routes_chart_vision.py
"""

import base64
import json
import re
import httpx
from typing import Optional

from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger("chart_vision.analyzer")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

CHART_VISION_SYSTEM_PROMPT = """You are an expert technical analyst AI that analyzes trading chart screenshots.

When shown a chart image, you must:
1. Identify the symbol and timeframe from the chart header/title
2. Detect all visible indicators (moving averages, oscillators, etc.) — note their colors and approximate values
3. Identify chart patterns (trend lines, support/resistance, consolidation, breakouts)
4. Determine the current trend direction
5. Identify key price levels
6. Suggest a trading strategy based on what you see

Output ONLY valid JSON with this exact schema:
{
    "symbol": "detected symbol or UNKNOWN",
    "timeframe": "detected timeframe or UNKNOWN",
    "indicators_detected": [
        {"name": "SMA", "period": 44, "color": "orange", "current_value": "approximate value"}
    ],
    "patterns_detected": [
        {"pattern": "pattern_name", "description": "what you see"}
    ],
    "trend": "bullish|bearish|sideways|transitioning",
    "key_levels": {
        "support": [price1, price2],
        "resistance": [price1, price2]
    },
    "suggested_strategy": {
        "action": "BUY|SELL|WAIT",
        "reasoning": "why this action",
        "entry_condition": "specific condition to enter",
        "stop_loss": "suggested stop loss level or method",
        "take_profit": "suggested take profit level or method",
        "indicators_to_watch": ["indicator1", "indicator2"]
    },
    "natural_language_summary": "2-3 sentence plain English summary of what you see",
    "confidence": 0.0-1.0
}

Read indicator legends carefully. If you see text like "SMA(44)" or "EMA 20" near a line, report the exact period.
If you can identify colors (orange line, blue line), map them to the indicator they represent.
Be specific about price levels — read actual numbers from the Y-axis.
"""

CHART_VISION_USER_PROMPT = """Analyze this trading chart screenshot. Identify all indicators, patterns, and suggest a trading strategy.

Additional context from the user: {user_context}

Remember: Output ONLY valid JSON matching the schema."""


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_chart_analyzer: Optional["ChartVisionAnalyzer"] = None


def get_chart_analyzer() -> "ChartVisionAnalyzer":
    """Return (and lazily create) the singleton ChartVisionAnalyzer."""
    global _chart_analyzer
    if _chart_analyzer is None:
        _chart_analyzer = ChartVisionAnalyzer()
    return _chart_analyzer


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class ChartVisionAnalyzer:
    """
    PURPOSE: Analyzes TradingView chart screenshots using vision-capable LLMs.

    Uses OpenAI GPT-4o as the primary vision model. Falls back to a helpful
    error response if no vision-capable LLM is configured.

    CALLED BY: api/routes_chart_vision.py
    """

    def __init__(self) -> None:
        self._analysis_history: list = []

    async def analyze_chart(self, image_data: bytes, user_context: str = "") -> dict:
        """
        Analyze a chart screenshot using a vision-capable LLM.

        Args:
            image_data: Raw image bytes (PNG/JPG/WEBP).
            user_context: Optional user description, e.g. "this is BTCUSD 1H chart".

        Returns:
            dict with symbol, timeframe, indicators_detected, patterns_detected,
            trend, key_levels, suggested_strategy, natural_language_summary, confidence.
        """
        b64_image = base64.b64encode(image_data).decode("utf-8")

        result = await self._analyze_with_openai(b64_image, user_context)
        if not result:
            result = await self._analyze_with_fallback()

        if result and "error" not in result:
            self._analysis_history.append(result)
            if len(self._analysis_history) > 20:
                self._analysis_history = self._analysis_history[-20:]

        return result or {
            "error": "Analysis failed",
            "detail": "No vision-capable LLM available",
        }

    async def _analyze_with_openai(self, b64_image: str, user_context: str) -> Optional[dict]:
        """Use OpenAI GPT-4o for chart vision analysis."""
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            logger.warning(
                "openai_not_configured",
                message="No OPENAI_API_KEY set — chart vision requires GPT-4o",
            )
            return None

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {
                                "role": "system",
                                "content": CHART_VISION_SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": CHART_VISION_USER_PROMPT.format(
                                            user_context=user_context or "No additional context provided"
                                        ),
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{b64_image}",
                                            "detail": "high",
                                        },
                                    },
                                ],
                            },
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3,
                    },
                )

            if response.status_code != 200:
                logger.error(
                    "openai_vision_error",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return None

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(
                "chart_vision_openai_success",
                content_length=len(content),
                tokens=data.get("usage", {}).get("total_tokens", 0),
            )
            return self._parse_analysis(content)

        except Exception as e:
            logger.error("chart_vision_openai_error", error=str(e))
            return None

    async def _analyze_with_fallback(self) -> dict:
        """Return a helpful error when no vision model is available."""
        return {
            "error": "no_vision_model",
            "detail": (
                "Configure OPENAI_API_KEY for chart vision analysis (GPT-4o required). "
                "Set OPENAI_API_KEY in your environment variables or .env file."
            ),
            "suggested_action": "Set OPENAI_API_KEY in environment variables",
        }

    def _parse_analysis(self, content: str) -> Optional[dict]:
        """
        Extract JSON from an LLM response, handling markdown fences and
        partial JSON gracefully.
        """
        # Try markdown code-fence extraction
        fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", content)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try direct JSON parse
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # Try brace-matching to extract the outermost JSON object
        start = content.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(content[start : i + 1])
                        except json.JSONDecodeError:
                            break

        # Fall back to returning the raw text as a natural-language summary
        logger.warning("chart_vision_json_parse_failed", preview=content[:120])
        return {"natural_language_summary": content, "parse_failed": True}

    def get_history(self, limit: int = 10) -> list:
        """Return the last `limit` analysis results (newest last)."""
        return self._analysis_history[-limit:]
