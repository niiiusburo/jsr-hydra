"""
PURPOSE: LLM-powered trading intelligence.
Supports OpenAI-compatible chat completion endpoints so the Brain can
switch between providers (for example OpenAI and Z.AI) without changing
core analysis logic.

NOT called every cycle -- called on specific triggers to save costs:
1. Every 15 minutes: Market analysis summary
2. On trade close: Trade review and lessons learned
3. Every hour: Strategy performance review
4. On regime change: Regime analysis and strategy recommendations

ENHANCEMENTS (v2):
- Hierarchical memory (short/medium/long-term) via LLMMemory
- Structured JSON output parsing via StructuredOutputParser
- Memory context injection into all LLM prompts
- Importance-scored memory entries with automatic promotion/decay
"""

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
import httpx

from app.brain.llm_memory import LLMMemory
from app.brain.llm_structured import (
    StructuredOutputParser,
    MarketSignal,
    TradeReview,
    StrategyAdvice,
    RegimeInsight,
    LossDiagnosis,
    compute_importance_from_signal,
    compute_importance_from_review,
    compute_importance_from_diagnosis,
)
from app.brain.sentiment import get_sentiment_data, format_sentiment_for_prompt
from app.utils.logger import get_logger

logger = get_logger("brain.llm")


class LLMBrain:
    """
    PURPOSE: LLM-powered trading intelligence layer for JSR Hydra Brain.

    Makes cost-efficient calls to a configured OpenAI-compatible endpoint
    for market analysis,
    trade review, strategy optimization, and regime change analysis.
    All calls are rate-limited internally to prevent excessive API usage.

    CALLED BY:
        - brain/brain.py (process_cycle, process_trade_result, regime change)
        - api/routes_brain.py (get insights, get stats)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        provider: str = "openai",
        base_url: str = "https://api.openai.com/v1/chat/completions",
    ):
        self._api_key = api_key
        self._model = model
        self._provider = provider
        self._base_url = base_url
        self._last_analysis_time = 0
        self._last_review_time = 0
        self._analysis_interval = 900  # 15 minutes
        self._review_interval = 3600   # 1 hour
        self._loss_diagnosis_interval = 1200  # 20 minutes
        self._total_tokens_used = 0
        self._total_calls = 0
        self._last_loss_diagnosis_time = 0
        self._insights_history: List[Dict] = []  # Rolling list of LLM insights
        self._max_insights = 50

        # v2: Hierarchical memory and structured output parser
        self._memory = LLMMemory()
        self._parser = StructuredOutputParser()

        logger.info(
            "llm_brain_initialized",
            provider=provider,
            model=model,
            base_url=base_url,
            analysis_interval=self._analysis_interval,
            review_interval=self._review_interval,
        )

    def _normalize_error_message(self, raw_message: Optional[str], fallback: str) -> str:
        """Normalize message text so dashboard errors are never blank."""
        msg = " ".join(str(raw_message or "").strip().split())
        return msg[:240] if msg else fallback

    def _extract_http_error_detail(self, response: httpx.Response) -> str:
        """Extract a meaningful detail from non-2xx provider responses."""
        fallback = f"HTTP {response.status_code}"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                if isinstance(payload.get("error"), dict):
                    maybe_msg = payload["error"].get("message")
                    return self._normalize_error_message(maybe_msg, fallback=fallback)
                for key in ("message", "detail"):
                    if payload.get(key):
                        return self._normalize_error_message(payload.get(key), fallback=fallback)
            if isinstance(payload, list) and payload:
                return self._normalize_error_message(str(payload[0]), fallback=fallback)
        except Exception:
            pass
        return self._normalize_error_message(response.text, fallback=fallback)

    def _is_error_content(self, content: str) -> bool:
        return str(content or "").strip().startswith("[LLM Error")

    def _build_insight(self, insight_type: str, content: str, **extras: object) -> Dict:
        """Create a normalized insight payload with explicit error markers."""
        insight: Dict[str, object] = {
            "type": insight_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content,
            "model": self._model,
            "provider": self._provider,
            "is_error": self._is_error_content(content),
        }
        if insight["is_error"]:
            insight["error_message"] = content
        for key, value in extras.items():
            if value is not None:
                insight[key] = value
        return insight

    async def _call_gpt(self, system_prompt: str, user_prompt: str, max_tokens: int = 500) -> Optional[str]:
        """
        PURPOSE: Make an async call to an OpenAI-compatible chat completions API.

        Args:
            system_prompt: System role instruction for GPT.
            user_prompt: User message with data to analyze.
            max_tokens: Maximum response length.

        Returns:
            str or None: GPT response content, or error string on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.7,
                    },
                )
                response.raise_for_status()
                data = response.json()
                tokens_used = data.get("usage", {}).get("total_tokens", 0)
                self._total_tokens_used += tokens_used
                self._total_calls += 1

                logger.info(
                    "llm_call_success",
                    provider=self._provider,
                    model=self._model,
                    tokens=tokens_used,
                    total_calls=self._total_calls,
                )

                choices = data.get("choices") or []
                if not choices:
                    return "[LLM Error][EmptyChoices] Provider response had no choices."
                first_choice = choices[0] if isinstance(choices[0], dict) else {}
                message_obj = first_choice.get("message", {})
                content = message_obj.get("content") if isinstance(message_obj, dict) else None
                content_str = str(content or "").strip()
                if not content_str:
                    # Z.AI "thinking" models (e.g. glm-5) put content in reasoning_content
                    reasoning = message_obj.get("reasoning_content") if isinstance(message_obj, dict) else None
                    content_str = str(reasoning or "").strip()
                if not content_str:
                    return "[LLM Error][EmptyContent] Provider returned an empty completion."
                return content_str
        except httpx.HTTPStatusError as e:
            detail = self._extract_http_error_detail(e.response)
            logger.error(
                "llm_api_http_error",
                status=e.response.status_code,
                detail=detail,
            )
            return f"[LLM Error][HTTP {e.response.status_code}] {detail}"
        except Exception as e:
            err_type = type(e).__name__
            detail = self._normalize_error_message(str(e), fallback=err_type)
            logger.error("llm_api_error", error_type=err_type, error=detail)
            return f"[LLM Error][{err_type}] {detail}"

    def _store_insight(self, insight: Dict) -> None:
        """Store an insight in the rolling history, trimming if needed."""
        self._insights_history.append(insight)
        if len(self._insights_history) > self._max_insights:
            self._insights_history = self._insights_history[-self._max_insights:]

    def _estimate_cost(self) -> float:
        """Estimate total USD cost based on provider and model."""
        # Approximate blended rate (input + output averaged)
        COST_PER_MILLION: Dict[str, float] = {
            "gpt-4o-mini": 0.375,       # avg of $0.15 input / $0.60 output
            "gpt-4.1-mini": 0.40,
            "gpt-4.1-nano": 0.14,
            "gpt-4o": 7.50,             # avg of $2.50 / $10.00
            "gpt-4.1": 6.00,
            "glm-5": 0.10,              # Z.AI approximate
        }
        rate = COST_PER_MILLION.get(self._model, 0.40)
        return round(self._total_tokens_used * rate / 1_000_000, 4)

    async def _call_gpt_with_retry(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 500, max_retries: int = 2
    ) -> Optional[str]:
        """Call LLM with exponential backoff retry on transient errors."""
        import random
        result = None
        for attempt in range(max_retries + 1):
            result = await self._call_gpt(system_prompt, user_prompt, max_tokens)
            if result and not self._is_error_content(result):
                return result
            # Only retry on transient errors (HTTP 429, 500, 503, timeouts)
            transient = ["[HTTP 4", "[HTTP 5", "Timeout", "ConnectError"]
            if result and any(tag in result for tag in transient):
                if attempt < max_retries:
                    wait = (3 ** attempt) * 2 + random.uniform(0, 2)
                    logger.info("llm_retry", attempt=attempt + 1, wait=round(wait, 1))
                    await asyncio.sleep(wait)
                    continue
            break  # Non-transient error, don't retry
        return result

    async def analyze_market(self, market_data: Dict) -> Optional[Dict]:
        """
        PURPOSE: Analyze current market conditions. Called every 15 minutes.

        Returns insights and recommendations based on current indicators,
        regime, and account state. Internally rate-limited to avoid
        excessive API calls.

        Args:
            market_data: Dict with symbols, indicators, regime, account info.

        Returns:
            Dict with type, timestamp, content, model, tokens_used or None if too soon.

        CALLED BY: brain/brain.py process_cycle (via asyncio.create_task)
        """
        now = time.time()
        if now - self._last_analysis_time < self._analysis_interval:
            return None  # Too soon
        self._last_analysis_time = now

        # Fetch sentiment/news data concurrently before building prompt
        from app.config.settings import settings as _settings
        finnhub_key = getattr(_settings, "FINNHUB_API_KEY", "") or None
        try:
            sentiment_data = await get_sentiment_data(finnhub_api_key=finnhub_key)
            sentiment_block = format_sentiment_for_prompt(sentiment_data)
        except Exception as e:
            logger.warning("sentiment_fetch_for_prompt_failed", error=str(e))
            sentiment_block = "(Sentiment data unavailable this cycle)"

        # Retrieve memory context for this analysis
        regime = market_data.get('regime', 'Unknown')
        symbols = market_data.get('symbols', [])
        memory_context = self._memory.get_context_for_prompt(
            source_type="market_analysis",
            regime=regime,
            symbol=symbols[0] if symbols else None,
        )
        schema_instruction = self._parser.get_schema_instruction("market_signal")

        system_prompt = f"""You are an expert forex, crypto, and commodities trader AI assistant.
You analyze market data AND sentiment/news context to provide concise, actionable trading insights.
Be specific about price levels and conditions.
When sentiment data is available, factor it into your analysis:
- Fear & Greed extremes are contrarian indicators (extreme fear = potential buy, extreme greed = potential sell)
- Upcoming high-impact economic events (NFP, CPI, FOMC) mean: avoid new positions 30 min before/after
- News headlines provide qualitative context for momentum shifts

{schema_instruction}"""

        user_prompt = f"""Analyze these current market conditions:

{memory_context}
=== TECHNICAL DATA ===
Symbols being traded: {', '.join(symbols)}

For each symbol:
{json.dumps(market_data.get('symbol_data', {}), indent=2, default=str)}

Current regime: {regime}
ADX: {market_data.get('adx', 'N/A')}
RSI: {market_data.get('rsi', 'N/A')}
Account balance: ${market_data.get('balance', 0):.2f}
Open positions: {market_data.get('open_positions', 0)}
Today's P&L: ${market_data.get('daily_pnl', 0):.2f}

{sentiment_block}

Based on BOTH the technical indicators AND the sentiment/news data above:
1. What are the key things to watch?
2. Any dangers from upcoming events or extreme sentiment?
3. Best opportunities right now?
4. Should we avoid trading due to upcoming high-impact news?"""

        response = await self._call_gpt(system_prompt, user_prompt, max_tokens=600)
        if response:
            # Parse structured output
            signal, raw_text = self._parser.parse_market_signal(response)
            importance = compute_importance_from_signal(signal)

            # Store in hierarchical memory
            if not self._is_error_content(response):
                self._memory.add(
                    text=signal.summary or raw_text[:300],
                    source_type="market_analysis",
                    importance=importance,
                    tags=[signal.sentiment, regime],
                    symbol=symbols[0] if symbols else "",
                    regime=regime,
                )
                self._memory.step()  # Run decay/promote cycle

            insight = self._build_insight(
                "market_analysis",
                raw_text,
                tokens_used=self._total_tokens_used,
                structured=signal.to_dict(),
            )
            self._store_insight(insight)
            logger.info(
                "llm_market_analysis_complete",
                content_length=len(response),
                sentiment=signal.sentiment,
                confidence=signal.confidence,
            )
            return insight
        return None

    async def review_trade(self, trade_data: Dict) -> Optional[Dict]:
        """
        PURPOSE: Review a completed trade and extract lessons.

        Called when a trade closes. Provides analysis of what went right
        or wrong, a lesson learned, and a suggestion for improvement.

        Args:
            trade_data: Dict with symbol, direction, strategy, entry/exit prices,
                       profit, duration, SL/TP, RSI at entry, regime.

        Returns:
            Dict with type, timestamp, content, trade_symbol, trade_pnl or None.

        CALLED BY: brain/brain.py process_trade_result (via asyncio.create_task)
        """
        profit = trade_data.get('profit', 0)
        symbol = trade_data.get('symbol', '')
        strategy = trade_data.get('strategy', '')
        regime = trade_data.get('regime', 'N/A')

        # Retrieve memory context: past reviews for same symbol/strategy
        memory_context = self._memory.get_context_for_prompt(
            source_type="trade_review",
            symbol=symbol,
            max_short=2, max_medium=2, max_long=2,
        )
        schema_instruction = self._parser.get_schema_instruction("trade_review")

        system_prompt = f"""You are a trading coach reviewing a completed trade.
Analyze what went right or wrong, provide lessons and improvement suggestions.
Be constructive and specific. Reference actual numbers.

{schema_instruction}"""

        user_prompt = f"""Review this completed trade:

{memory_context}
Symbol: {symbol}
Direction: {trade_data.get('direction')}
Strategy: {strategy}
Entry: {trade_data.get('entry_price')}
Exit: {trade_data.get('exit_price')}
P&L: ${profit:.2f}
Duration: {trade_data.get('duration_minutes', 0)} minutes
Stop Loss: {trade_data.get('sl_price')}
Take Profit: {trade_data.get('tp_price')}
RSI at entry: {trade_data.get('rsi_at_entry', 'N/A')}
Regime at entry: {regime}
Win/Loss: {'WIN' if profit > 0 else 'LOSS'}"""

        response = await self._call_gpt(system_prompt, user_prompt)
        if response:
            # Parse structured output
            review, raw_text = self._parser.parse_trade_review(response)
            importance = compute_importance_from_review(review)

            # Store in hierarchical memory
            if not self._is_error_content(response):
                tags = list(review.pattern_tags) + [
                    "win" if profit > 0 else "loss",
                    review.grade,
                ]
                self._memory.add(
                    text=f"[{review.grade}] {'; '.join(review.lessons)}" if review.lessons else raw_text[:300],
                    source_type="trade_review",
                    importance=importance,
                    tags=tags,
                    symbol=symbol,
                    regime=regime,
                    strategy=strategy,
                    pnl=profit,
                )

            insight = self._build_insight(
                "trade_review",
                raw_text,
                trade_symbol=symbol,
                trade_pnl=profit,
                structured=review.to_dict(),
            )
            self._store_insight(insight)
            logger.info(
                "llm_trade_review_complete",
                symbol=symbol,
                pnl=profit,
                grade=review.grade,
            )
            return insight
        return None

    async def hourly_strategy_review(self, strategy_stats: Dict) -> Optional[Dict]:
        """
        PURPOSE: Review overall strategy performance. Called every hour.

        Analyzes strategy statistics and suggests parameter adjustments,
        lot size changes, and whether to pause underperforming strategies.

        Args:
            strategy_stats: Dict with per-strategy performance metrics.

        Returns:
            Dict with type, timestamp, content or None if too soon.

        CALLED BY: brain/brain.py (periodic call via asyncio.create_task)
        """
        now = time.time()
        if now - self._last_review_time < self._review_interval:
            return None
        self._last_review_time = now

        # Retrieve memory context: past strategy reviews
        memory_context = self._memory.get_context_for_prompt(
            source_type="strategy_review",
            max_short=2, max_medium=3, max_long=2,
        )
        schema_instruction = self._parser.get_schema_instruction("strategy_advice")

        system_prompt = f"""You are a quantitative trading system optimizer.
Review strategy performance and suggest specific parameter changes.
Be precise -- suggest exact numbers for thresholds.

{schema_instruction}"""

        user_prompt = f"""Review these strategy performances over the last hour:

{memory_context}
{json.dumps(strategy_stats, indent=2, default=str)}

For each strategy, suggest:
1. Should we adjust any parameters? (RSI thresholds, EMA periods, etc.)
2. Should we increase or decrease lot size?
3. Should we pause any strategy that's underperforming?
4. Any new patterns you notice?"""

        response = await self._call_gpt(system_prompt, user_prompt, max_tokens=600)
        if response:
            # Parse structured output
            advice, raw_text = self._parser.parse_strategy_advice(response)

            # Store in hierarchical memory
            if not self._is_error_content(response):
                self._memory.add(
                    text=advice.summary or raw_text[:300],
                    source_type="strategy_review",
                    importance=0.5,
                    tags=["strategy_review", advice.highest_edge] if advice.highest_edge else ["strategy_review"],
                )

            insight = self._build_insight(
                "strategy_review",
                raw_text,
                structured=advice.to_dict(),
            )
            self._store_insight(insight)
            logger.info("llm_strategy_review_complete", content_length=len(response))
            return insight
        return None

    async def analyze_regime_change(self, old_regime: str, new_regime: str, indicators: Dict) -> Optional[Dict]:
        """
        PURPOSE: Analyze a market regime change and its implications.

        Called when the regime detector identifies a shift. Explains what
        the change means for different strategies and what to watch for.

        Args:
            old_regime: Previous regime string.
            new_regime: New regime string.
            indicators: Current indicator values (rsi, adx, atr, ema_20, ema_50).

        Returns:
            Dict with type, timestamp, content, old_regime, new_regime or None.

        CALLED BY: brain/brain.py process_cycle (via asyncio.create_task)
        """
        # Retrieve memory context: past regime transitions
        memory_context = self._memory.get_context_for_prompt(
            source_type="regime_analysis",
            regime=new_regime,
            max_short=2, max_medium=2, max_long=3,
        )
        schema_instruction = self._parser.get_schema_instruction("regime_insight")

        system_prompt = f"""You are a market regime analyst. When market conditions shift,
explain what it means for different trading strategies and what to watch for.
Be actionable.

{schema_instruction}"""

        user_prompt = f"""Market regime just changed from {old_regime} to {new_regime}.

{memory_context}
Current indicators:
RSI: {indicators.get('rsi', 'N/A')}
ADX: {indicators.get('adx', 'N/A')}
ATR: {indicators.get('atr', 'N/A')}
EMA20: {indicators.get('ema_20', 'N/A')}
EMA50: {indicators.get('ema_50', 'N/A')}

What does this regime change mean? Which strategies should be more/less aggressive?
Any specific price levels to watch?"""

        response = await self._call_gpt(system_prompt, user_prompt)
        if response:
            # Parse structured output
            regime_insight, raw_text = self._parser.parse_regime_insight(response)

            # Store in hierarchical memory with high importance (regime changes are significant)
            if not self._is_error_content(response):
                self._memory.add(
                    text=regime_insight.summary or raw_text[:300],
                    source_type="regime_analysis",
                    importance=0.7,  # Regime changes are always important
                    tags=[
                        f"from_{old_regime}", f"to_{new_regime}",
                        regime_insight.risk_level,
                    ],
                    regime=new_regime,
                )

            insight = self._build_insight(
                "regime_analysis",
                raw_text,
                old_regime=old_regime,
                new_regime=new_regime,
                structured=regime_insight.to_dict(),
            )
            self._store_insight(insight)
            logger.info(
                "llm_regime_analysis_complete",
                old_regime=old_regime,
                new_regime=new_regime,
                risk_level=regime_insight.risk_level,
            )
            return insight
        return None

    async def diagnose_losses(self, performance_snapshot: Dict) -> Optional[Dict]:
        """
        PURPOSE: Diagnose persistent losses and recommend concrete fixes.

        Called when the brain detects a losing cluster. Internally rate-limited
        to avoid repetitive cost while losses persist.
        """
        now = time.time()
        if now - self._last_loss_diagnosis_time < self._loss_diagnosis_interval:
            return None
        self._last_loss_diagnosis_time = now

        # Retrieve memory context: past diagnoses and recent trade reviews
        memory_context = self._memory.get_context_for_prompt(
            source_type="loss_diagnosis",
            max_short=2, max_medium=3, max_long=3,
        )
        # Also pull in recent losing trade reviews for additional context
        loss_memories = self._memory.query(
            source_type="trade_review", tags=["loss"], limit=3,
        )
        loss_context = ""
        if loss_memories:
            loss_items = "\n".join(
                f"  - {m.text[:150]}" for m in loss_memories
            )
            loss_context = f"\n[Recent Loss Trade Reviews]\n{loss_items}\n"

        schema_instruction = self._parser.get_schema_instruction("loss_diagnosis")

        system_prompt = f"""You are a quantitative trading diagnostician.
Given strategy/symbol performance stats from an automated system, identify why it is losing.

{schema_instruction}"""

        user_prompt = f"""Diagnose this automated trading system performance snapshot:

{memory_context}{loss_context}
{json.dumps(performance_snapshot, indent=2, default=str)}

Focus on:
- why losses are happening
- which strategy/symbol combinations are weakest
- what to pause or reduce now
- what to increase if edge exists
- how to adjust reward and exploration behavior."""

        response = await self._call_gpt(system_prompt, user_prompt, max_tokens=700)
        if response:
            # Parse structured output
            diagnosis, raw_text = self._parser.parse_loss_diagnosis(response)
            importance = compute_importance_from_diagnosis(diagnosis)

            # Store in hierarchical memory
            if not self._is_error_content(response):
                self._memory.add(
                    text=diagnosis.recovery_plan or raw_text[:300],
                    source_type="loss_diagnosis",
                    importance=importance,
                    tags=["loss_diagnosis", diagnosis.severity],
                )

            insight = self._build_insight(
                "loss_diagnosis",
                raw_text,
                structured=diagnosis.to_dict(),
            )
            self._store_insight(insight)
            logger.info(
                "llm_loss_diagnosis_complete",
                content_length=len(response),
                severity=diagnosis.severity,
            )
            return insight
        return None

    # ------------------------------------------------------------------ #
    #  Structured JSON Output Helpers
    # ------------------------------------------------------------------ #

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON object from an LLM response, handling markdown fences."""
        if not text or self._is_error_content(text):
            return None
        # Try to extract content between markdown code fences first
        fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", text)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # Try direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # Try to find the outermost JSON object via brace matching
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
        logger.warning("json_parse_failed", text_preview=text[:120])
        return None

    # ------------------------------------------------------------------ #
    #  Bull vs Bear Debate (TradingAgents pattern)
    # ------------------------------------------------------------------ #

    async def bull_bear_debate(self, market_data: Dict) -> Optional[Dict]:
        """
        Run a structured bull vs bear adversarial analysis for a symbol.
        Returns parsed JSON with bull_case, bear_case, and verdict.

        CALLED BY: brain.py _llm_analyze_market (enhanced pipeline)
        """
        from app.brain.prompts import BULL_BEAR_DEBATE_SYSTEM, BULL_BEAR_DEBATE_USER

        symbols = market_data.get("symbols", [])
        symbol = symbols[0] if symbols else "EURUSD"
        symbol_data = market_data.get("symbol_data", {})
        sym_info = symbol_data.get(symbol, {})
        indicators = sym_info.get("indicators", {})

        user_prompt = BULL_BEAR_DEBATE_USER.format(
            symbol=symbol,
            price=sym_info.get("bid", indicators.get("price", "N/A")),
            regime=market_data.get("regime", "UNKNOWN"),
            rsi=indicators.get("rsi", "N/A"),
            adx=indicators.get("adx", "N/A"),
            atr=indicators.get("atr", "N/A"),
            ema_20=indicators.get("ema_20", indicators.get("ema20", "N/A")),
            ema_50=indicators.get("ema_50", indicators.get("ema50", "N/A")),
            spread=sym_info.get("spread", "N/A"),
            balance=market_data.get("balance", 0),
            open_positions=market_data.get("open_positions", 0),
            daily_pnl=market_data.get("daily_pnl", 0),
        )

        response = await self._call_gpt_with_retry(
            BULL_BEAR_DEBATE_SYSTEM, user_prompt, max_tokens=600
        )
        if not response or self._is_error_content(response):
            return None

        parsed = self._parse_json_response(response)
        if not parsed or "verdict" not in parsed:
            logger.warning("debate_parse_failed", response_preview=response[:100])
            return None

        insight = self._build_insight(
            "bull_bear_debate",
            response,
            symbol=symbol,
            structured=parsed,
        )
        self._store_insight(insight)

        # Store in memory
        verdict = parsed.get("verdict", {})
        self._memory.add(
            text=f"[{symbol}] Debate verdict: {verdict.get('direction', '?')} "
                 f"(conviction {verdict.get('conviction', 0):.2f}) — {verdict.get('reasoning', '')}",
            source_type="debate",
            importance=max(0.4, verdict.get("conviction", 0.5)),
            tags=[verdict.get("direction", "NEUTRAL"), symbol],
            symbol=symbol,
            regime=market_data.get("regime", ""),
        )

        logger.info(
            "debate_complete",
            symbol=symbol,
            direction=verdict.get("direction"),
            conviction=verdict.get("conviction"),
        )
        return parsed

    # ------------------------------------------------------------------ #
    #  Signal Extraction (debate results -> actionable signal)
    # ------------------------------------------------------------------ #

    async def extract_signal(self, debate_result: Dict, market_data: Dict) -> Optional[Dict]:
        """
        Convert debate results into an actionable trading signal with
        per-strategy preferences and risk adjustment.

        CALLED BY: brain.py _llm_analyze_market (after debate)
        """
        from app.brain.prompts import SIGNAL_EXTRACTION_SYSTEM, SIGNAL_EXTRACTION_USER

        verdict = debate_result.get("verdict", {})
        bull = debate_result.get("bull_case", {})
        bear = debate_result.get("bear_case", {})

        user_prompt = SIGNAL_EXTRACTION_USER.format(
            bull_thesis=bull.get("thesis", "No bull case"),
            bull_confidence=bull.get("confidence", 0),
            bear_thesis=bear.get("thesis", "No bear case"),
            bear_confidence=bear.get("confidence", 0),
            verdict_direction=verdict.get("direction", "NEUTRAL"),
            verdict_conviction=verdict.get("conviction", 0),
            verdict_reasoning=verdict.get("reasoning", ""),
            regime=market_data.get("regime", "UNKNOWN"),
            rsi=market_data.get("rsi", "N/A"),
            adx=market_data.get("adx", "N/A"),
            drawdown_pct=market_data.get("drawdown_pct", 0),
        )

        response = await self._call_gpt_with_retry(
            SIGNAL_EXTRACTION_SYSTEM, user_prompt, max_tokens=400
        )
        if not response or self._is_error_content(response):
            return None

        parsed = self._parse_json_response(response)
        if not parsed or "signal" not in parsed:
            logger.warning("signal_parse_failed", response_preview=response[:100])
            return None

        insight = self._build_insight(
            "signal_extraction",
            response,
            structured=parsed,
        )
        self._store_insight(insight)

        logger.info(
            "signal_extracted",
            signal=parsed.get("signal"),
            confidence=parsed.get("confidence"),
            risk=parsed.get("risk_adjustment"),
        )
        return parsed

    # ------------------------------------------------------------------ #
    #  Structured Trade Reflection
    # ------------------------------------------------------------------ #

    async def structured_trade_review(self, trade_data: Dict) -> Optional[Dict]:
        """
        Structured post-trade reflection that produces actionable JSON
        with outcome quality, root cause, lesson, and strategy adjustment.

        CALLED BY: brain.py _llm_review_trade (enhanced pipeline)
        """
        from app.brain.prompts import TRADE_REFLECTION_SYSTEM, TRADE_REFLECTION_USER

        profit = trade_data.get("profit", 0)
        symbol = trade_data.get("symbol", "")
        strategy = trade_data.get("strategy", "A")

        user_prompt = TRADE_REFLECTION_USER.format(
            symbol=symbol,
            strategy=strategy,
            direction=trade_data.get("direction", "BUY"),
            entry_price=trade_data.get("entry_price", 0),
            exit_price=trade_data.get("exit_price", 0),
            profit=profit,
            regime=trade_data.get("regime", "N/A"),
            outcome="WIN" if profit > 0 else "LOSS",
        )

        response = await self._call_gpt_with_retry(
            TRADE_REFLECTION_SYSTEM, user_prompt, max_tokens=400
        )
        if not response or self._is_error_content(response):
            return None

        parsed = self._parse_json_response(response)
        if not parsed or "outcome_quality" not in parsed:
            logger.warning("reflection_parse_failed", response_preview=response[:100])
            return None

        insight = self._build_insight(
            "trade_reflection",
            response,
            trade_symbol=symbol,
            trade_pnl=profit,
            structured=parsed,
        )
        self._store_insight(insight)

        # Store lesson in memory
        lesson = parsed.get("lesson", "")
        if lesson and not self._is_error_content(response):
            self._memory.add(
                text=f"[{symbol}/{strategy}] {parsed.get('outcome_quality', '?')}: {lesson}",
                source_type="trade_reflection",
                importance=0.6 if profit > 0 else 0.7,
                tags=[
                    "win" if profit > 0 else "loss",
                    parsed.get("outcome_quality", ""),
                    strategy,
                ],
                symbol=symbol,
                strategy=strategy,
                pnl=profit,
            )

        logger.info(
            "trade_reflection_complete",
            symbol=symbol,
            strategy=strategy,
            outcome=parsed.get("outcome_quality"),
            adjustment=parsed.get("strategy_adjustment", {}).get("direction"),
        )
        return parsed

    def get_insights(self, limit: int = 20) -> List[Dict]:
        """
        PURPOSE: Get recent LLM insights, newest first.

        Args:
            limit: Maximum number of insights to return.

        Returns:
            List of insight dicts.

        CALLED BY: api/routes_brain.py /llm-insights endpoint
        """
        return list(reversed(self._insights_history[-limit:]))

    def get_stats(self) -> Dict:
        """
        PURPOSE: Get LLM usage statistics.

        Returns:
            Dict with total_calls, total_tokens_used, estimated_cost_usd,
            model, and insights_count.

        CALLED BY: api/routes_brain.py /llm-insights endpoint
        """
        last_error: Optional[str] = None
        for insight in reversed(self._insights_history):
            if insight.get("is_error"):
                last_error = insight.get("error_message") or insight.get("content")
                break
        return {
            "provider": self._provider,
            "total_calls": self._total_calls,
            "total_tokens_used": self._total_tokens_used,
            # Cost estimate is only available for the current OpenAI default path.
            "estimated_cost_usd": self._estimate_cost(),
            "model": self._model,
            "insights_count": len(self._insights_history),
            "last_error": last_error,
            "memory": self._memory.get_stats(),
        }

    @property
    def memory(self) -> LLMMemory:
        """Expose the hierarchical memory for external inspection."""
        return self._memory

    @property
    def parser(self) -> StructuredOutputParser:
        """Expose the structured output parser for external use."""
        return self._parser
