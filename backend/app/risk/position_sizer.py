"""
PURPOSE: Position sizing calculator using Kelly Criterion variant.

Calculates optimal lot sizes for trades based on equity, risk percentage,
stop-loss distance, and symbol-specific pip values. Ensures sizes fall
within configured limits and are properly rounded.
"""

from typing import Optional

from app.config.settings import settings
from app.utils.logger import get_logger
from app.utils.math_utils import round_lots, calculate_pip_value

logger = get_logger("risk.position_sizer")


class PositionSizer:
    """
    PURPOSE: Calculate optimal position sizes using Kelly Criterion variant.

    Uses the formula: lots = (equity * risk_pct / 100) / (sl_points * pip_value)
    Clamps result to [min_lots, max_lots] and rounds to nearest 0.01 step.

    CALLED BY: RiskManager (pre_trade_check)

    Attributes:
        _min_lots: Minimum lot size (from settings).
        _max_lots: Maximum lot size (from settings).
    """

    def __init__(
        self,
        min_lots: float = 0.01,
        max_lots: Optional[float] = None
    ) -> None:
        """
        PURPOSE: Initialize position sizer with size limits.

        Args:
            min_lots: Minimum position size in lots (default 0.01).
            max_lots: Maximum position size in lots. If None, uses settings.
        """
        self._min_lots: float = min_lots
        self._max_lots: float = max_lots or getattr(settings, "MAX_LOT_SIZE", 100.0)

        logger.info(
            "position_sizer_initialized",
            min_lots=self._min_lots,
            max_lots=self._max_lots
        )

    def calculate_position_size(
        self,
        equity: float,
        risk_pct: float,
        sl_distance: float,
        symbol: str
    ) -> float:
        """
        PURPOSE: Calculate position size using Kelly Criterion variant.

        Formula:
          pip_value = calculate_pip_value(symbol, lots)
          lots = (equity * risk_pct / 100) / (sl_distance * pip_value)
          return clamp(round(lots, 0.01), min_lots, max_lots)

        CALLED BY: RiskManager.pre_trade_check

        Args:
            equity: Account equity in currency units.
            risk_pct: Risk percentage of equity (e.g., 1.0 for 1%).
            sl_distance: Stop-loss distance in points/pips from entry.
            symbol: Trading symbol (e.g., "EURUSD", "XAUUSD").

        Returns:
            float: Calculated and clamped position size in lots (rounded to 0.01).

        Raises:
            ValueError: If equity, risk_pct, or sl_distance are invalid.
        """
        if equity <= 0:
            logger.error(
                "calculate_position_size_invalid_equity",
                equity=equity
            )
            raise ValueError(f"Equity must be positive, got {equity}")

        if risk_pct <= 0 or risk_pct > 100:
            logger.error(
                "calculate_position_size_invalid_risk",
                risk_pct=risk_pct
            )
            raise ValueError(f"Risk percentage must be 0-100, got {risk_pct}")

        if sl_distance <= 0:
            logger.error(
                "calculate_position_size_invalid_sl",
                sl_distance=sl_distance
            )
            raise ValueError(f"Stop-loss distance must be positive, got {sl_distance}")

        # Start with minimum lot size to get pip value
        pip_value = calculate_pip_value(symbol, self._min_lots)

        if pip_value <= 0:
            logger.warning(
                "calculate_position_size_invalid_pip_value",
                symbol=symbol,
                pip_value=pip_value
            )
            return self._min_lots

        # Kelly formula: lots = (equity * risk_pct / 100) / (sl_distance * pip_value)
        risk_amount = (equity * risk_pct) / 100.0
        base_lots = risk_amount / (sl_distance * pip_value)

        # Recalculate pip value with actual lots for more accuracy
        if base_lots > 0:
            pip_value = calculate_pip_value(symbol, base_lots)
            base_lots = risk_amount / (sl_distance * pip_value)

        # Clamp to [min_lots, max_lots]
        clamped_lots = max(self._min_lots, min(self._max_lots, base_lots))

        # Round to nearest 0.01 step
        rounded_lots = round_lots(clamped_lots, step=0.01)

        logger.info(
            "calculate_position_size_result",
            equity=equity,
            risk_pct=risk_pct,
            sl_distance=sl_distance,
            symbol=symbol,
            calculated=f"{base_lots:.2f}",
            clamped=f"{clamped_lots:.2f}",
            rounded=f"{rounded_lots:.2f}"
        )

        return rounded_lots

    def validate_position_size(
        self,
        lots: float,
        symbol: Optional[str] = None
    ) -> bool:
        """
        PURPOSE: Validate that position size is within allowed limits.

        CALLED BY: RiskManager (pre_trade_check)

        Args:
            lots: Position size in lots to validate.
            symbol: Trading symbol (optional, for logging).

        Returns:
            bool: True if position size is valid (between min and max lots).
        """
        is_valid = self._min_lots <= lots <= self._max_lots

        logger.info(
            "validate_position_size_result",
            lots=lots,
            min_lots=self._min_lots,
            max_lots=self._max_lots,
            symbol=symbol or "N/A",
            is_valid=is_valid
        )

        return is_valid

    def round_to_step(self, lots: float, step: float = 0.01) -> float:
        """
        PURPOSE: Round lot size to nearest step increment.

        CALLED BY: Position sizing pipeline (internal)

        Args:
            lots: Lot size to round.
            step: Rounding step (default 0.01).

        Returns:
            float: Rounded lot size.
        """
        return round_lots(lots, step=step)

    def get_min_lots(self) -> float:
        """
        PURPOSE: Get minimum allowed lot size.

        Returns:
            float: Minimum lot size.
        """
        return self._min_lots

    def get_max_lots(self) -> float:
        """
        PURPOSE: Get maximum allowed lot size.

        Returns:
            float: Maximum lot size.
        """
        return self._max_lots
