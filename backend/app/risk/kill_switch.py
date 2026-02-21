"""
PURPOSE: Kill switch implementation for emergency trading halt.

Monitors drawdown, daily losses, and per-trade risk to automatically
halt trading when thresholds are exceeded. Closes all positions and
prevents new trades until manually reset.
"""

import asyncio
from datetime import datetime
from typing import Optional

from app.bridge.order_manager import OrderManager
from app.config.constants import EventType, MaxDrawdownPct, DailyLossLimitPct
from app.config.settings import settings
from app.events.bus import get_event_bus
from app.utils.logger import get_logger

logger = get_logger("risk.kill_switch")


class KillSwitch:
    """
    PURPOSE: Emergency trading halt mechanism.

    Monitors account drawdown, daily losses, and per-trade risk limits.
    Automatically closes all positions and halts trading when thresholds
    are exceeded. Requires manual reset to resume trading.

    CALLED BY: RiskManager (pre_trade_check, post_trade_update)

    Attributes:
        _is_active: Whether kill switch has been triggered.
        _triggered_at: Timestamp when kill switch was triggered.
        _order_manager: OrderManager instance for closing positions.
        _lock: Asyncio lock for thread-safe operations.
    """

    # Recovery ramp: position size multipliers after kill switch reset
    RECOVERY_RAMP = [0.25, 0.50, 0.75, 1.0]

    def __init__(self, order_manager: OrderManager) -> None:
        """
        PURPOSE: Initialize kill switch with order manager dependency.

        Args:
            order_manager: OrderManager instance for closing all positions.
        """
        self._is_active: bool = False
        self._triggered_at: Optional[datetime] = None
        self._order_manager: OrderManager = order_manager
        self._lock: asyncio.Lock = asyncio.Lock()
        # Recovery mode: ramp position sizes back up after reset
        self._in_recovery: bool = False
        self._recovery_trades_completed: int = 0
        logger.info("kill_switch_initialized")

    def check_drawdown(
        self,
        equity: float,
        peak_equity: float,
        max_drawdown_pct: Optional[float] = None
    ) -> bool:
        """
        PURPOSE: Check if drawdown exceeds maximum threshold.

        CALLED BY: RiskManager.pre_trade_check

        Args:
            equity: Current account equity.
            peak_equity: Peak equity reached since trading started.
            max_drawdown_pct: Maximum drawdown percentage (default from settings).

        Returns:
            bool: True if drawdown exceeds threshold (kill switch should trigger).
        """
        if max_drawdown_pct is None:
            max_drawdown_pct = settings.MAX_DRAWDOWN_PCT

        if peak_equity <= 0:
            logger.warning("check_drawdown_invalid_peak", peak_equity=peak_equity)
            return False

        drawdown_pct = ((peak_equity - equity) / peak_equity) * 100.0
        drawdown_pct = max(0.0, drawdown_pct)

        threshold_exceeded = drawdown_pct >= max_drawdown_pct

        logger.info(
            "check_drawdown_result",
            drawdown_pct=f"{drawdown_pct:.2f}",
            max_drawdown_pct=max_drawdown_pct,
            threshold_exceeded=threshold_exceeded
        )

        return threshold_exceeded

    def check_daily_loss(
        self,
        today_pnl: float,
        starting_balance: float,
        daily_limit_pct: Optional[float] = None
    ) -> bool:
        """
        PURPOSE: Check if daily loss exceeds maximum percentage.

        CALLED BY: RiskManager.post_trade_update

        Args:
            today_pnl: Daily profit/loss in account currency (negative = loss).
            starting_balance: Starting balance for the day.
            daily_limit_pct: Maximum daily loss percentage (default from settings).

        Returns:
            bool: True if daily loss exceeds threshold (kill switch should trigger).
        """
        if daily_limit_pct is None:
            daily_limit_pct = settings.DAILY_LOSS_LIMIT_PCT

        if starting_balance <= 0:
            logger.warning(
                "check_daily_loss_invalid_balance",
                starting_balance=starting_balance
            )
            return False

        daily_loss_pct = (abs(min(0, today_pnl)) / starting_balance) * 100.0

        threshold_exceeded = daily_loss_pct >= daily_limit_pct

        logger.info(
            "check_daily_loss_result",
            daily_loss_pct=f"{daily_loss_pct:.2f}",
            daily_limit_pct=daily_limit_pct,
            threshold_exceeded=threshold_exceeded
        )

        return threshold_exceeded

    def check_per_trade_risk(
        self,
        risk_amount: float,
        equity: float,
        max_pct: float = 1.0
    ) -> bool:
        """
        PURPOSE: Check if per-trade risk exceeds maximum percentage of equity.

        CALLED BY: RiskManager.pre_trade_check

        Args:
            risk_amount: Risk amount for this trade (difference between entry and SL).
            equity: Current account equity.
            max_pct: Maximum risk as percentage of equity (default 1.0%).

        Returns:
            bool: True if per-trade risk exceeds threshold.
        """
        if equity <= 0:
            logger.warning("check_per_trade_risk_invalid_equity", equity=equity)
            return False

        if risk_amount <= 0:
            logger.warning(
                "check_per_trade_risk_invalid_amount",
                risk_amount=risk_amount
            )
            return False

        risk_pct = (risk_amount / equity) * 100.0

        threshold_exceeded = risk_pct > max_pct

        logger.info(
            "check_per_trade_risk_result",
            risk_pct=f"{risk_pct:.2f}",
            max_pct=max_pct,
            threshold_exceeded=threshold_exceeded
        )

        return threshold_exceeded

    async def trigger_kill_switch(self) -> None:
        """
        PURPOSE: Execute kill switch: close all positions and halt trading.

        CALLED BY: RiskManager (when any threshold is exceeded)

        Actions:
        1. Set _is_active flag
        2. Close all open positions via OrderManager
        3. Publish KILL_SWITCH_TRIGGERED event
        4. Log critical severity
        """
        async with self._lock:
            if self._is_active:
                logger.warning("kill_switch_already_active")
                return

            self._is_active = True
            self._triggered_at = datetime.utcnow()

            logger.error(
                "kill_switch_triggered",
                triggered_at=self._triggered_at.isoformat()
            )

            # Close all open positions
            try:
                closed_positions = await self._order_manager.close_all_positions()
                logger.info(
                    "kill_switch_closed_positions",
                    count=len(closed_positions) if closed_positions else 0
                )
            except Exception as e:
                logger.error(
                    "kill_switch_position_close_failed",
                    error=str(e)
                )

            # Publish kill switch event
            try:
                event_bus = get_event_bus()
                await event_bus.publish(
                    event_type=EventType.KILL_SWITCH_TRIGGERED.value,
                    data={
                        "triggered_at": self._triggered_at.isoformat(),
                        "closed_positions": len(closed_positions) if 'closed_positions' in locals() else 0
                    },
                    source="risk.kill_switch",
                    severity="CRITICAL"
                )
            except Exception as e:
                logger.error(
                    "kill_switch_event_publish_failed",
                    error=str(e)
                )

    @property
    def is_active(self) -> bool:
        """
        PURPOSE: Check if kill switch is currently active.

        CALLED BY: RiskManager (pre_trade_check)

        Returns:
            bool: True if kill switch has been triggered and trading is halted.
        """
        return self._is_active

    def reset(self, admin_override: bool = False) -> None:
        """
        PURPOSE: Reset kill switch to allow trading to resume.

        CALLED BY: Admin API endpoint only (requires authentication)

        Args:
            admin_override: Safety flag (must be True to reset).

        Raises:
            ValueError: If admin_override is not True.
        """
        if not admin_override:
            logger.error(
                "kill_switch_reset_unauthorized",
                reason="admin_override not set"
            )
            raise ValueError("Admin override required to reset kill switch")

        self._is_active = False
        self._triggered_at = None
        # Enter recovery mode: ramp position sizes gradually
        self._in_recovery = True
        self._recovery_trades_completed = 0

        logger.warning(
            "kill_switch_reset_by_admin",
            recovery_mode=True,
        )

    @property
    def recovery_multiplier(self) -> float:
        """
        PURPOSE: Get current position size multiplier during recovery.

        Returns 1.0 when not in recovery mode. During recovery, ramps
        from 0.25 → 0.50 → 0.75 → 1.0 over 4 trades.

        CALLED BY: RiskManager.pre_trade_check
        """
        if not self._in_recovery:
            return 1.0
        idx = min(self._recovery_trades_completed, len(self.RECOVERY_RAMP) - 1)
        return self.RECOVERY_RAMP[idx]

    def record_recovery_trade(self) -> None:
        """
        PURPOSE: Record a completed trade during recovery and auto-exit
        recovery mode when the ramp is complete.

        CALLED BY: RiskManager.post_trade_update
        """
        if not self._in_recovery:
            return
        self._recovery_trades_completed += 1
        if self._recovery_trades_completed >= len(self.RECOVERY_RAMP):
            self._in_recovery = False
            logger.info(
                "kill_switch_recovery_complete",
                trades_completed=self._recovery_trades_completed,
            )
