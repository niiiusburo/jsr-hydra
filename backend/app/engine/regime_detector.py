"""
PURPOSE: Detects market regime from price action using ADX and conviction layering.

Simple placeholder regime detection for Phase 1. Uses ADX > 25 threshold to classify
markets as TRENDING or RANGING. In Phase 2, will be upgraded to use HMM (Hidden Markov
Models) for more sophisticated regime classification.

CALLED BY:
    - engine/orchestrator.py
"""

import pandas as pd
from typing import Optional
from app.config.constants import RegimeType
from app.indicators.trend import adx
from app.utils.logger import get_logger

logger = get_logger("engine.regime_detector")


class RegimeDetector:
    """
    PURPOSE: Detect current market regime from OHLCV data.

    Simple Phase 1 implementation using ADX indicator. In Phase 2, will expand
    to use Hidden Markov Models, conviction scoring, and ADDM drift detection
    for more sophisticated regime classification.

    Attributes:
        _conviction_threshold: ADX threshold for trending (default: 25)
    """

    def __init__(self, adx_threshold: float = 25.0):
        """
        PURPOSE: Initialize RegimeDetector with ADX threshold.

        Args:
            adx_threshold: ADX value threshold for TRENDING classification (default: 25.0)

        CALLED BY: engine/orchestrator.py
        """
        self._conviction_threshold = adx_threshold
        logger.info(
            "regime_detector_initialized",
            adx_threshold=adx_threshold
        )

    def detect_regime(self, candles_df: pd.DataFrame) -> dict:
        """
        PURPOSE: Detect current market regime from candles.

        Simple Phase 1 implementation:
        - ADX > threshold → TRENDING
        - ADX < threshold → RANGING

        Args:
            candles_df: DataFrame with columns [open, high, low, close, volume].
                       Index should be datetime.

        Returns:
            dict: Regime state with keys:
                - regime: RegimeType (TRENDING_UP, TRENDING_DOWN, RANGING, etc.)
                - confidence: float (0.0 - 1.0)
                - conviction_score: int (0 - 100)
                - hmm_state: int (placeholder, always 0 in Phase 1)
                - is_drifting: bool (placeholder, always False in Phase 1)
                - layer_scores: dict (placeholder with default values)

        CALLED BY: engine/orchestrator.py
        """
        try:
            if candles_df.empty or len(candles_df) < 14:
                logger.warning(
                    "insufficient_candles_for_regime_detection",
                    available=len(candles_df),
                    required=14
                )
                return {
                    "regime": RegimeType.RANGING,
                    "confidence": 0.3,
                    "conviction_score": 30,
                    "hmm_state": 0,
                    "is_drifting": False,
                    "layer_scores": {
                        "mtf": 0,
                        "adx": 0,
                        "structure": 0,
                        "momentum": 0,
                    }
                }

            # Calculate ADX
            adx_values = adx(
                high=candles_df['high'],
                low=candles_df['low'],
                close=candles_df['close'],
                period=14
            )

            # Get latest ADX value
            latest_adx = adx_values.iloc[-1] if not adx_values.empty else 0.0

            # Determine regime based on ADX
            if latest_adx > self._conviction_threshold:
                # Trending regime
                trend_direction = self._determine_trend_direction(candles_df)
                regime = (
                    RegimeType.TRENDING_UP if trend_direction > 0
                    else RegimeType.TRENDING_DOWN
                )
                confidence = min(0.9, (latest_adx / 100.0))  # Max 90% confidence
                conviction_score = min(100, int(latest_adx * 2))  # Scale ADX to 0-100
            else:
                # Ranging regime
                regime = RegimeType.RANGING
                confidence = min(0.7, (1.0 - latest_adx / self._conviction_threshold) * 0.5 + 0.2)
                conviction_score = max(20, 50 - int(latest_adx * 2))

            logger.info(
                "regime_detected",
                regime=regime.value,
                adx=latest_adx,
                confidence=confidence,
                conviction_score=conviction_score
            )

            return {
                "regime": regime,
                "confidence": confidence,
                "conviction_score": conviction_score,
                "hmm_state": 0,  # Placeholder for Phase 2
                "is_drifting": False,  # Placeholder for Phase 2
                "layer_scores": {
                    "mtf": conviction_score // 4,
                    "adx": int(latest_adx),
                    "structure": conviction_score // 4,
                    "momentum": conviction_score // 4,
                }
            }

        except Exception as e:
            logger.error(
                "regime_detection_error",
                error=str(e)
            )
            # Return neutral regime on error
            return {
                "regime": RegimeType.TRANSITIONING,
                "confidence": 0.5,
                "conviction_score": 50,
                "hmm_state": 0,
                "is_drifting": False,
                "layer_scores": {
                    "mtf": 0,
                    "adx": 0,
                    "structure": 0,
                    "momentum": 0,
                }
            }

    def _determine_trend_direction(self, candles_df: pd.DataFrame) -> int:
        """
        PURPOSE: Determine if trend is up or down.

        Simple heuristic: compare current close to MA20 and previous close.

        Args:
            candles_df: OHLCV DataFrame

        Returns:
            int: 1 for up trend, -1 for down trend

        CALLED BY: detect_regime()
        """
        try:
            close = candles_df['close']
            if len(close) < 20:
                return 1  # Default to up

            ma20 = close.rolling(window=20).mean().iloc[-1]
            latest_close = close.iloc[-1]
            prev_close = close.iloc[-2]

            if latest_close > ma20 and latest_close > prev_close:
                return 1
            elif latest_close < ma20 and latest_close < prev_close:
                return -1
            else:
                return 1  # Default to up

        except Exception:
            return 1  # Default to up on error

    def get_conviction_score(self) -> int:
        """
        PURPOSE: Get current conviction score (0-100).

        Placeholder for Phase 2 enhancement. In Phase 1, always returns 50.

        Returns:
            int: Conviction score between 0 and 100

        CALLED BY: engine/orchestrator.py, external monitoring
        """
        return 50  # Placeholder for Phase 2
