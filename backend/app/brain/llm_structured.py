"""
PURPOSE: Structured output parser for LLM trading signals.

Converts free-form LLM text into typed, validated Python objects that
the Brain can act on.  Works with any OpenAI-compatible chat completion
endpoint (OpenAI, Z.AI glm-5, etc.) without requiring native structured
output support -- uses prompt-level JSON schema enforcement plus robust
fallback parsing.

Design inspired by:
  - FinMem's structured decision outputs (investment_decision + summary_reason)
  - TradingAgents' structured report format
  - OpenAI structured outputs / Pydantic patterns

Each analysis type has its own schema:
  - MarketSignal:   sentiment, key_levels, risk_factors, opportunities
  - TradeReview:    grade, lessons, improvement, pattern_tags
  - StrategyAdvice: per-strategy recommendations with confidence
  - RegimeInsight:  regime implications, favored/unfavored strategies

The parser:
  1. Injects a JSON schema instruction into the system prompt
  2. Attempts to parse the LLM response as JSON
  3. Falls back to regex extraction if JSON parse fails
  4. Validates and normalizes the result
  5. Returns both the structured object AND the raw text

CALLED BY: brain/llm_brain.py -- wraps _call_gpt responses
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any, Tuple

from app.utils.logger import get_logger

logger = get_logger("brain.llm_structured")


# ============================================================
# Schema definitions
# ============================================================

@dataclass
class MarketSignal:
    """Structured output from market analysis."""
    sentiment: str = "neutral"       # bullish, bearish, neutral
    confidence: float = 0.5          # 0-1
    key_levels: List[Dict] = field(default_factory=list)
    # e.g. [{"type": "support", "price": 1.0850, "strength": "strong"}]
    risk_factors: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    regime_assessment: str = ""
    summary: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TradeReview:
    """Structured output from trade review."""
    grade: str = "C"                 # A, B, C, D, F
    outcome_quality: str = "neutral" # good, neutral, poor
    entry_quality: str = "neutral"   # good, neutral, poor
    exit_quality: str = "neutral"    # good, neutral, poor
    lessons: List[str] = field(default_factory=list)
    improvement: str = ""
    pattern_tags: List[str] = field(default_factory=list)
    # e.g. ["early_exit", "good_entry_timing", "wrong_regime"]
    should_repeat: bool = True       # Would you take this trade again?

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StrategyRecommendation:
    """Recommendation for a single strategy."""
    strategy_code: str = ""
    action: str = "hold"             # increase, decrease, hold, pause
    confidence_adjustment: float = 0.0  # -0.3 to +0.3
    reason: str = ""
    parameter_changes: Dict = field(default_factory=dict)
    # e.g. {"rsi_oversold": 25, "sl_multiplier": 1.5}


@dataclass
class StrategyAdvice:
    """Structured output from strategy review."""
    overall_assessment: str = ""
    recommendations: List[Dict] = field(default_factory=list)
    # Each dict is a StrategyRecommendation.to_dict()
    highest_edge: str = ""           # Which strategy has best edge right now
    summary: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RegimeInsight:
    """Structured output from regime change analysis."""
    transition_type: str = ""        # continuation, reversal, breakdown
    expected_duration: str = "hours"  # minutes, hours, days
    favored_strategies: List[str] = field(default_factory=list)
    unfavored_strategies: List[str] = field(default_factory=list)
    key_levels_to_watch: List[Dict] = field(default_factory=list)
    risk_level: str = "medium"       # low, medium, high, extreme
    summary: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LossDiagnosis:
    """Structured output from loss diagnosis."""
    root_causes: List[str] = field(default_factory=list)
    worst_combinations: List[Dict] = field(default_factory=list)
    # e.g. [{"strategy": "A", "symbol": "EURUSD", "reason": "wrong regime"}]
    immediate_actions: List[str] = field(default_factory=list)
    parameter_fixes: Dict = field(default_factory=dict)
    recovery_plan: str = ""
    severity: str = "moderate"       # mild, moderate, severe, critical

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# JSON Schema strings for prompt injection
# ============================================================

MARKET_SIGNAL_SCHEMA = """\
Respond ONLY with valid JSON matching this schema (no markdown, no explanation outside JSON):
{
  "sentiment": "bullish|bearish|neutral",
  "confidence": 0.0-1.0,
  "key_levels": [{"type": "support|resistance", "price": number, "strength": "weak|moderate|strong"}],
  "risk_factors": ["string"],
  "opportunities": ["string"],
  "regime_assessment": "string",
  "summary": "1-2 sentence summary"
}"""

TRADE_REVIEW_SCHEMA = """\
Respond ONLY with valid JSON matching this schema (no markdown, no explanation outside JSON):
{
  "grade": "A|B|C|D|F",
  "outcome_quality": "good|neutral|poor",
  "entry_quality": "good|neutral|poor",
  "exit_quality": "good|neutral|poor",
  "lessons": ["string"],
  "improvement": "string",
  "pattern_tags": ["string tags like: early_exit, good_entry, wrong_regime, trend_caught, mean_reversion_fail"],
  "should_repeat": true|false
}"""

STRATEGY_ADVICE_SCHEMA = """\
Respond ONLY with valid JSON matching this schema (no markdown, no explanation outside JSON):
{
  "overall_assessment": "string",
  "recommendations": [
    {
      "strategy_code": "A|B|C|D|E",
      "action": "increase|decrease|hold|pause",
      "confidence_adjustment": -0.3 to 0.3,
      "reason": "string",
      "parameter_changes": {"param_name": value}
    }
  ],
  "highest_edge": "strategy code with best edge",
  "summary": "1-2 sentence summary"
}"""

REGIME_INSIGHT_SCHEMA = """\
Respond ONLY with valid JSON matching this schema (no markdown, no explanation outside JSON):
{
  "transition_type": "continuation|reversal|breakdown",
  "expected_duration": "minutes|hours|days",
  "favored_strategies": ["A","B","C","D","E"],
  "unfavored_strategies": ["A","B","C","D","E"],
  "key_levels_to_watch": [{"type": "support|resistance", "price": number}],
  "risk_level": "low|medium|high|extreme",
  "summary": "1-2 sentence summary"
}"""

LOSS_DIAGNOSIS_SCHEMA = """\
Respond ONLY with valid JSON matching this schema (no markdown, no explanation outside JSON):
{
  "root_causes": ["string"],
  "worst_combinations": [{"strategy": "code", "symbol": "SYMBOL", "reason": "string"}],
  "immediate_actions": ["string"],
  "parameter_fixes": {"strategy_code.param_name": value},
  "recovery_plan": "string",
  "severity": "mild|moderate|severe|critical"
}"""


# ============================================================
# Parser
# ============================================================

class StructuredOutputParser:
    """
    PURPOSE: Parse free-form LLM text into structured trading objects.

    Handles three scenarios:
      1. Clean JSON response -- direct parse
      2. JSON embedded in markdown/text -- regex extraction
      3. No JSON at all -- fallback to text-based extraction

    CALLED BY: LLMBrain methods after _call_gpt returns raw text.
    """

    @staticmethod
    def get_schema_instruction(output_type: str) -> str:
        """
        Return the JSON schema instruction string for a given output type.
        This should be appended to the system prompt.
        """
        schemas = {
            "market_signal": MARKET_SIGNAL_SCHEMA,
            "trade_review": TRADE_REVIEW_SCHEMA,
            "strategy_advice": STRATEGY_ADVICE_SCHEMA,
            "regime_insight": REGIME_INSIGHT_SCHEMA,
            "loss_diagnosis": LOSS_DIAGNOSIS_SCHEMA,
        }
        return schemas.get(output_type, "")

    @staticmethod
    def extract_json(text: str) -> Optional[Dict]:
        """
        Extract JSON from LLM response text.

        Tries in order:
          1. Direct JSON.loads on full text
          2. Extract from ```json ... ``` code block
          3. Find first { ... } block
        """
        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # 1. Direct parse
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Markdown code block
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # 3. Find first complete JSON object
        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                # Try fixing common issues: trailing commas
                fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(fixed)
                except (json.JSONDecodeError, ValueError):
                    pass

        return None

    @classmethod
    def parse_market_signal(cls, raw_text: str) -> Tuple[MarketSignal, str]:
        """
        Parse market analysis response into MarketSignal.

        Returns:
            Tuple of (MarketSignal, raw_text).
            MarketSignal fields are best-effort populated.
        """
        signal = MarketSignal()
        parsed = cls.extract_json(raw_text)

        if parsed:
            signal.sentiment = cls._validate_enum(
                parsed.get("sentiment", ""), ["bullish", "bearish", "neutral"], "neutral"
            )
            signal.confidence = cls._clamp(parsed.get("confidence", 0.5), 0.0, 1.0)
            signal.key_levels = parsed.get("key_levels", [])
            signal.risk_factors = cls._ensure_list(parsed.get("risk_factors", []))
            signal.opportunities = cls._ensure_list(parsed.get("opportunities", []))
            signal.regime_assessment = str(parsed.get("regime_assessment", ""))
            signal.summary = str(parsed.get("summary", ""))
        else:
            # Fallback: extract sentiment from text
            signal.summary = raw_text[:300]
            text_lower = raw_text.lower()
            if any(w in text_lower for w in ["bullish", "uptrend", "buy opportunity"]):
                signal.sentiment = "bullish"
            elif any(w in text_lower for w in ["bearish", "downtrend", "sell", "short"]):
                signal.sentiment = "bearish"
            signal.confidence = 0.3  # Low confidence for text-only parse

        return signal, raw_text

    @classmethod
    def parse_trade_review(cls, raw_text: str) -> Tuple[TradeReview, str]:
        """Parse trade review response into TradeReview."""
        review = TradeReview()
        parsed = cls.extract_json(raw_text)

        if parsed:
            review.grade = cls._validate_enum(
                parsed.get("grade", "C"), ["A", "B", "C", "D", "F"], "C"
            )
            for quality_field in ("outcome_quality", "entry_quality", "exit_quality"):
                setattr(review, quality_field, cls._validate_enum(
                    parsed.get(quality_field, "neutral"),
                    ["good", "neutral", "poor"], "neutral"
                ))
            review.lessons = cls._ensure_list(parsed.get("lessons", []))
            review.improvement = str(parsed.get("improvement", ""))
            review.pattern_tags = cls._ensure_list(parsed.get("pattern_tags", []))
            review.should_repeat = bool(parsed.get("should_repeat", True))
        else:
            review.lessons = [raw_text[:200]]

        return review, raw_text

    @classmethod
    def parse_strategy_advice(cls, raw_text: str) -> Tuple[StrategyAdvice, str]:
        """Parse strategy review response into StrategyAdvice."""
        advice = StrategyAdvice()
        parsed = cls.extract_json(raw_text)

        if parsed:
            advice.overall_assessment = str(parsed.get("overall_assessment", ""))
            advice.recommendations = cls._ensure_list(parsed.get("recommendations", []))
            advice.highest_edge = str(parsed.get("highest_edge", ""))
            advice.summary = str(parsed.get("summary", ""))
        else:
            advice.summary = raw_text[:300]

        return advice, raw_text

    @classmethod
    def parse_regime_insight(cls, raw_text: str) -> Tuple[RegimeInsight, str]:
        """Parse regime change analysis into RegimeInsight."""
        insight = RegimeInsight()
        parsed = cls.extract_json(raw_text)

        if parsed:
            insight.transition_type = cls._validate_enum(
                parsed.get("transition_type", ""),
                ["continuation", "reversal", "breakdown"], ""
            )
            insight.expected_duration = cls._validate_enum(
                parsed.get("expected_duration", "hours"),
                ["minutes", "hours", "days"], "hours"
            )
            insight.favored_strategies = cls._ensure_list(
                parsed.get("favored_strategies", [])
            )
            insight.unfavored_strategies = cls._ensure_list(
                parsed.get("unfavored_strategies", [])
            )
            insight.key_levels_to_watch = cls._ensure_list(
                parsed.get("key_levels_to_watch", [])
            )
            insight.risk_level = cls._validate_enum(
                parsed.get("risk_level", "medium"),
                ["low", "medium", "high", "extreme"], "medium"
            )
            insight.summary = str(parsed.get("summary", ""))
        else:
            insight.summary = raw_text[:300]

        return insight, raw_text

    @classmethod
    def parse_loss_diagnosis(cls, raw_text: str) -> Tuple[LossDiagnosis, str]:
        """Parse loss diagnosis response into LossDiagnosis."""
        diagnosis = LossDiagnosis()
        parsed = cls.extract_json(raw_text)

        if parsed:
            diagnosis.root_causes = cls._ensure_list(parsed.get("root_causes", []))
            diagnosis.worst_combinations = cls._ensure_list(
                parsed.get("worst_combinations", [])
            )
            diagnosis.immediate_actions = cls._ensure_list(
                parsed.get("immediate_actions", [])
            )
            diagnosis.parameter_fixes = parsed.get("parameter_fixes", {})
            diagnosis.recovery_plan = str(parsed.get("recovery_plan", ""))
            diagnosis.severity = cls._validate_enum(
                parsed.get("severity", "moderate"),
                ["mild", "moderate", "severe", "critical"], "moderate"
            )
        else:
            diagnosis.root_causes = [raw_text[:200]]

        return diagnosis, raw_text

    # --- Utility helpers ---

    @staticmethod
    def _validate_enum(value: Any, allowed: List[str], default: str) -> str:
        """Return value if it's in allowed list, else default."""
        s = str(value).lower().strip()
        return s if s in allowed else default

    @staticmethod
    def _clamp(value: Any, min_val: float, max_val: float) -> float:
        """Clamp a numeric value to [min_val, max_val]."""
        try:
            return max(min_val, min(max_val, float(value)))
        except (TypeError, ValueError):
            return (min_val + max_val) / 2

    @staticmethod
    def _ensure_list(value: Any) -> list:
        """Ensure value is a list."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [value] if value else []
        return []


def compute_importance_from_signal(signal: MarketSignal) -> float:
    """
    Derive an importance score for memory storage from a MarketSignal.
    Higher importance for strong sentiment + high confidence + risk factors.
    """
    base = signal.confidence
    if signal.sentiment != "neutral":
        base += 0.1
    if signal.risk_factors:
        base += min(len(signal.risk_factors) * 0.05, 0.2)
    if signal.key_levels:
        base += min(len(signal.key_levels) * 0.05, 0.15)
    return min(1.0, base)


def compute_importance_from_review(review: TradeReview) -> float:
    """
    Derive importance from a TradeReview.
    Losses and extreme grades are more important to remember.
    """
    grade_scores = {"A": 0.7, "B": 0.5, "C": 0.3, "D": 0.6, "F": 0.8}
    base = grade_scores.get(review.grade, 0.4)
    if review.outcome_quality == "poor":
        base += 0.15  # Losses are more memorable
    if review.pattern_tags:
        base += min(len(review.pattern_tags) * 0.05, 0.15)
    return min(1.0, base)


def compute_importance_from_diagnosis(diagnosis: LossDiagnosis) -> float:
    """Derive importance from loss diagnosis. Severe = very important."""
    severity_scores = {"mild": 0.4, "moderate": 0.6, "severe": 0.8, "critical": 0.95}
    return severity_scores.get(diagnosis.severity, 0.5)
