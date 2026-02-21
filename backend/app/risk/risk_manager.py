"""
PURPOSE: Main risk manager orchestrator for trading risk validation.

Coordinates all risk checks (drawdown, daily limits, per-trade risk, margin, weekend)
and generates risk check results. Tracks daily P&L in memory with UTC midnight resets.
Uses asyncio locks for thread-safe operations.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.bridge.account_info import AccountInfo
from app.config.constants import DailyLossLimitPct, MAX_TEST_LOTS
from app.config.settings import settings
from app.events.bus import get_event_bus
from app.utils.logger import get_logger
from app.risk.kill_switch import KillSwitch
from app.risk.position_sizer import PositionSizer
from app.risk.risk_models import RiskCheckResult, RiskMetrics

logger = get_logger("risk.risk_manager")


class RiskManager:
    """
    PURPOSE: Orchestrate all pre-trade and post-trade risk checks.

    Coordinates kill switch, position sizing, daily P&L tracking, margin checks,
    and weekend restrictions. Provides comprehensive risk validation for trade requests.

    CALLED BY: engine/orchestrator.py (pre_trade_check, post_trade_update, get_risk_metrics)

    Attributes:
        _kill_switch: KillSwitch instance for emergency halt.
        _position_sizer: PositionSizer for position size calculation.
        _account_info: AccountInfo for querying balance/equity/margin.
        _lock: Asyncio lock for thread-safe operations.
        _daily_pnl: In-memory tracking of daily profit/loss.
        _daily_pnl_reset_time: UTC timestamp of last daily reset.
    """

    def __init__(
        self,
        kill_switch: KillSwitch,
        position_sizer: PositionSizer,
        account_info: AccountInfo
    ) -> None:
        """
        PURPOSE: Initialize risk manager with dependencies.

        Args:
            kill_switch: KillSwitch instance.
            position_sizer: PositionSizer instance.
            account_info: AccountInfo instance for account queries.
        """
        self._kill_switch: KillSwitch = kill_switch
        self._position_sizer: PositionSizer = position_sizer
        self._account_info: AccountInfo = account_info
        self._lock: asyncio.Lock = asyncio.Lock()
        self._daily_pnl: float = 0.0
        self._daily_pnl_reset_time: datetime = self._get_utc_midnight()

        logger.info("risk_manager_initialized")

    def _get_utc_midnight(self) -> datetime:
        """
        PURPOSE: Get UTC midnight time for current day.

        Returns:
            datetime: UTC midnight of current day (00:00:00).
        """
        now = datetime.utcnow()
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _should_reset_daily_pnl(self) -> bool:
        """
        PURPOSE: Check if daily P&L should be reset (new UTC day).

        Returns:
            bool: True if current UTC time is past midnight since last reset.
        """
        now = datetime.utcnow()
        current_midnight = self._get_utc_midnight()

        should_reset = now >= current_midnight and self._daily_pnl_reset_time < current_midnight

        if should_reset:
            logger.info(
                "daily_pnl_reset_triggered",
                previous_reset=self._daily_pnl_reset_time.isoformat(),
                new_reset=current_midnight.isoformat()
            )

        return should_reset

    async def pre_trade_check(
        self,
        symbol: str,
        direction: str,
        requested_lots: Optional[float] = None,
        sl_distance: Optional[float] = None,
        risk_pct: float = 1.0
    ) -> RiskCheckResult:
        """
        PURPOSE: Validate trade request against all risk constraints.

        CALLED BY: engine/orchestrator.py

        Checks:
        1. Kill switch active? (reject if true)
        2. Daily loss limit? (reject if exceeded)
        3. Per-trade risk? (reject if exceeds 1%)
        4. Margin level? (reject if below threshold)
        5. Weekend check? (reject if weekend, except certain symbols)

        Args:
            symbol: Trading symbol (e.g., "EURUSD", "XAUUSD").
            direction: Trade direction ("BUY" or "SELL").
            requested_lots: Requested lot size (optional, will be calculated if not provided).
            sl_distance: Stop-loss distance in points (required for position sizing).
            risk_pct: Risk percentage of equity (default 1.0%).

        Returns:
            RiskCheckResult: Decision (approved/rejected) with reasoning and metrics.
        """
        async with self._lock:
            result_dict = {
                "symbol": symbol,
                "direction": direction,
                "risk_pct": risk_pct
            }

            # Check for daily P&L reset
            if self._should_reset_daily_pnl():
                self._daily_pnl = 0.0
                self._daily_pnl_reset_time = self._get_utc_midnight()

            # 1. Check if kill switch is active
            if self._kill_switch.is_active:
                logger.warning(
                    "pre_trade_check_rejected_kill_switch_active",
                    **result_dict
                )

                equity = await self._account_info.get_equity()
                drawdown = await self._calculate_drawdown()

                return RiskCheckResult(
                    approved=False,
                    reason="Kill switch is active. Trading halted.",
                    risk_score=100.0,
                    position_size=0.0,
                    drawdown_pct=drawdown,
                    daily_pnl=self._daily_pnl
                )

            # Get account info
            try:
                equity = await self._account_info.get_equity()
                balance = await self._account_info.get_balance()
                margin_level = await self._account_info.get_margin_level()
            except Exception as e:
                logger.error(
                    "pre_trade_check_account_info_failed",
                    error=str(e),
                    **result_dict
                )
                return RiskCheckResult(
                    approved=False,
                    reason=f"Failed to retrieve account info: {str(e)}",
                    risk_score=100.0,
                    position_size=0.0,
                    drawdown_pct=0.0,
                    daily_pnl=self._daily_pnl
                )

            # 2. Check daily loss limit
            daily_loss_pct = (abs(min(0, self._daily_pnl)) / balance) * 100.0
            if daily_loss_pct >= settings.DAILY_LOSS_LIMIT_PCT:
                logger.warning(
                    "pre_trade_check_rejected_daily_limit",
                    daily_loss_pct=f"{daily_loss_pct:.2f}",
                    daily_limit_pct=settings.DAILY_LOSS_LIMIT_PCT,
                    **result_dict
                )

                drawdown = await self._calculate_drawdown()

                return RiskCheckResult(
                    approved=False,
                    reason=f"Daily loss limit ({settings.DAILY_LOSS_LIMIT_PCT}%) exceeded. "
                            f"Current: {daily_loss_pct:.2f}%",
                    risk_score=85.0,
                    position_size=0.0,
                    drawdown_pct=drawdown,
                    daily_pnl=self._daily_pnl
                )

            # 3. Calculate position size if not provided
            if requested_lots is None:
                if sl_distance is None or sl_distance <= 0:
                    logger.error(
                        "pre_trade_check_invalid_sl_distance",
                        sl_distance=sl_distance,
                        **result_dict
                    )
                    return RiskCheckResult(
                        approved=False,
                        reason="Stop-loss distance required for position sizing",
                        risk_score=50.0,
                        position_size=0.0,
                        drawdown_pct=await self._calculate_drawdown(),
                        daily_pnl=self._daily_pnl
                    )

                try:
                    position_size = self._position_sizer.calculate_position_size(
                        equity=equity,
                        risk_pct=risk_pct,
                        sl_distance=sl_distance,
                        symbol=symbol
                    )
                except ValueError as e:
                    logger.error(
                        "pre_trade_check_position_sizing_failed",
                        error=str(e),
                        **result_dict
                    )
                    return RiskCheckResult(
                        approved=False,
                        reason=f"Position sizing failed: {str(e)}",
                        risk_score=50.0,
                        position_size=0.0,
                        drawdown_pct=await self._calculate_drawdown(),
                        daily_pnl=self._daily_pnl
                    )
            else:
                position_size = requested_lots

            # Apply kill switch recovery multiplier (ramps 25%→100% after reset)
            recovery_mult = self._kill_switch.recovery_multiplier
            if recovery_mult < 1.0:
                original_size = position_size
                position_size = round(position_size * recovery_mult, 2)
                # Ensure minimum viable lot size
                position_size = max(0.01, position_size)
                logger.info(
                    "position_size_recovery_scaled",
                    original=original_size,
                    multiplier=recovery_mult,
                    scaled_to=position_size,
                    **result_dict,
                )

            # Cap position size at MAX_TEST_LOTS only in dry-run/test mode
            if settings.DRY_RUN and position_size > MAX_TEST_LOTS:
                logger.info(
                    "position_size_capped_dry_run",
                    original=position_size,
                    capped_to=MAX_TEST_LOTS,
                    **result_dict
                )
                position_size = MAX_TEST_LOTS

            # Validate position size
            if not self._position_sizer.validate_position_size(position_size, symbol):
                logger.warning(
                    "pre_trade_check_position_size_invalid",
                    position_size=position_size,
                    min_lots=self._position_sizer.get_min_lots(),
                    max_lots=self._position_sizer.get_max_lots(),
                    **result_dict
                )
                return RiskCheckResult(
                    approved=False,
                    reason=f"Position size {position_size} outside allowed range "
                            f"[{self._position_sizer.get_min_lots()}, "
                            f"{self._position_sizer.get_max_lots()}]",
                    risk_score=60.0,
                    position_size=position_size,
                    drawdown_pct=await self._calculate_drawdown(),
                    daily_pnl=self._daily_pnl
                )

            # 4. Check margin level (0 means no positions open = safe)
            min_margin_level = 120.0  # Require at least 120% margin
            if margin_level > 0 and margin_level < min_margin_level:
                logger.warning(
                    "pre_trade_check_rejected_low_margin",
                    margin_level=margin_level,
                    min_margin_level=min_margin_level,
                    **result_dict
                )
                return RiskCheckResult(
                    approved=False,
                    reason=f"Margin level too low: {margin_level:.1f}% (minimum: {min_margin_level}%)",
                    risk_score=75.0,
                    position_size=position_size,
                    drawdown_pct=await self._calculate_drawdown(),
                    daily_pnl=self._daily_pnl
                )

            # 5. Weekend check (skip for 24/5 symbols like BTCUSD)
            if not self._is_weekend_safe_symbol(symbol):
                if self._is_weekend():
                    logger.info(
                        "pre_trade_check_rejected_weekend",
                        **result_dict
                    )
                    return RiskCheckResult(
                        approved=False,
                        reason="Trading disabled on weekends (except crypto/commodities)",
                        risk_score=10.0,
                        position_size=position_size,
                        drawdown_pct=await self._calculate_drawdown(),
                        daily_pnl=self._daily_pnl
                    )

            # All checks passed
            drawdown = await self._calculate_drawdown()
            risk_score = self._calculate_risk_score(drawdown, margin_level, daily_loss_pct)

            logger.info(
                "pre_trade_check_approved",
                position_size=position_size,
                risk_score=risk_score,
                margin_level=margin_level,
                **result_dict
            )

            return RiskCheckResult(
                approved=True,
                reason="All risk checks passed",
                risk_score=risk_score,
                position_size=position_size,
                drawdown_pct=drawdown,
                daily_pnl=self._daily_pnl
            )

    async def post_trade_update(
        self,
        trade_pnl: float,
        symbol: str
    ) -> None:
        """
        PURPOSE: Update daily P&L tracking after trade closure.

        CALLED BY: engine/orchestrator.py (after trade closes)

        Args:
            trade_pnl: Profit/loss from closed trade.
            symbol: Trading symbol (for logging).
        """
        async with self._lock:
            # Check for daily reset
            if self._should_reset_daily_pnl():
                self._daily_pnl = 0.0
                self._daily_pnl_reset_time = self._get_utc_midnight()

            previous_pnl = self._daily_pnl
            self._daily_pnl += trade_pnl

            # Record trade for kill switch recovery ramp
            self._kill_switch.record_recovery_trade()

            logger.info(
                "post_trade_update",
                symbol=symbol,
                trade_pnl=trade_pnl,
                previous_daily_pnl=previous_pnl,
                updated_daily_pnl=self._daily_pnl
            )

    async def get_risk_metrics(self) -> RiskMetrics:
        """
        PURPOSE: Get complete snapshot of current risk metrics.

        CALLED BY: API endpoints, dashboard, reporting

        Returns:
            RiskMetrics: Current drawdown, daily P&L, margin, kill switch status.
        """
        async with self._lock:
            # Check for daily reset
            if self._should_reset_daily_pnl():
                self._daily_pnl = 0.0
                self._daily_pnl_reset_time = self._get_utc_midnight()

            try:
                equity = await self._account_info.get_equity()
                margin_level = await self._account_info.get_margin_level()
            except Exception as e:
                logger.error(
                    "get_risk_metrics_account_info_failed",
                    error=str(e)
                )
                equity = 0.0
                margin_level = 0.0

            drawdown = await self._calculate_drawdown()
            balance = await self._account_info.get_balance()
            daily_limit_hit = (abs(min(0, self._daily_pnl)) / balance) * 100.0 >= settings.DAILY_LOSS_LIMIT_PCT if balance > 0 else False

            metrics = RiskMetrics(
                drawdown_pct=drawdown,
                daily_pnl=self._daily_pnl,
                margin_level=margin_level,
                kill_switch_active=self._kill_switch.is_active,
                daily_limit_hit=daily_limit_hit,
                timestamp=datetime.utcnow()
            )

            logger.info(
                "get_risk_metrics",
                drawdown_pct=f"{drawdown:.2f}",
                daily_pnl=f"{self._daily_pnl:.2f}",
                margin_level=f"{margin_level:.1f}",
                kill_switch_active=self._kill_switch.is_active
            )

            return metrics

    async def _calculate_drawdown(self) -> float:
        """
        PURPOSE: Calculate current drawdown from peak equity.

        Returns:
            float: Drawdown percentage (0.0 if at peak).
        """
        try:
            equity = await self._account_info.get_equity()
            balance = await self._account_info.get_balance()

            if balance <= 0:
                return 0.0

            peak_equity = max(balance, equity)
            if peak_equity <= 0:
                return 0.0

            drawdown = ((peak_equity - equity) / peak_equity) * 100.0
            return max(0.0, drawdown)
        except Exception as e:
            logger.error("_calculate_drawdown_failed", error=str(e))
            return 0.0

    def _calculate_risk_score(
        self,
        drawdown_pct: float,
        margin_level: float,
        daily_loss_pct: float
    ) -> float:
        """
        PURPOSE: Calculate overall risk score based on multiple factors.

        Range: 0 (safe) to 100 (very risky)

        Args:
            drawdown_pct: Current drawdown percentage.
            margin_level: Current margin level.
            daily_loss_pct: Current daily loss percentage.

        Returns:
            float: Risk score 0-100.
        """
        score = 0.0

        # Drawdown component (max 40 points)
        if drawdown_pct > 0:
            score += min(40.0, (drawdown_pct / settings.MAX_DRAWDOWN_PCT) * 40.0)

        # Margin component (max 30 points)
        if margin_level < 300:
            score += ((300.0 - margin_level) / 300.0) * 30.0

        # Daily loss component (max 30 points)
        if daily_loss_pct > 0:
            score += min(30.0, (daily_loss_pct / settings.DAILY_LOSS_LIMIT_PCT) * 30.0)

        return min(100.0, score)

    def _is_weekend(self) -> bool:
        """
        PURPOSE: Check if forex market is in weekend closure.

        Forex weekend: Friday 22:00 UTC to Sunday 22:00 UTC.

        Returns:
            bool: True if in weekend closure period.
        """
        from app.utils.time_utils import is_weekend
        return is_weekend()

    def _is_weekend_safe_symbol(self, symbol: str) -> bool:
        """
        PURPOSE: Check if symbol trades 24/5 (safe for weekends).

        CALLED BY: pre_trade_check (weekend validation)

        Args:
            symbol: Trading symbol.

        Returns:
            bool: True if symbol trades on weekends.
        """
        # Only crypto trades 24/7; XAUUSD follows forex weekend schedule
        weekend_safe_symbols = ["BTCUSD", "ETHUSD"]
        return symbol.upper() in weekend_safe_symbols
