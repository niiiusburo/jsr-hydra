"""
Account service for JSR Hydra trading system.

PURPOSE: Handle master account state management including equity tracking,
balance updates, and account health monitoring.

CALLED BY: app.api.routes.accounts, risk management modules, dashboard
"""

from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import MasterAccount, EquitySnapshot
from app.models.trade import Trade
from app.schemas.account import AccountResponse
from app.events.bus import get_event_bus
from app.utils.logger import get_logger


logger = get_logger("services.account")


class AccountService:
    """
    Service for managing master trading accounts.

    PURPOSE: Provide business logic for account operations including
    balance/equity tracking, health monitoring, and equity curve generation.

    CALLED BY: API routes for account endpoints
    """

    @staticmethod
    async def get_account(
        db: AsyncSession,
        master_id: UUID
    ) -> Optional[AccountResponse]:
        """
        Retrieve master account details with computed metrics.

        PURPOSE: Fetch account information including current balance, equity,
        and derived metrics like drawdown and open position count.

        CALLED BY: GET /api/accounts/{master_id} endpoint

        Args:
            db: Async database session
            master_id: UUID of the master account

        Returns:
            AccountResponse if found, None otherwise
        """
        logger.info("get_account_started", master_id=str(master_id))

        try:
            stmt = select(MasterAccount).where(MasterAccount.id == master_id)
            result = await db.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                logger.info("account_not_found", master_id=str(master_id))
                return None

            # Calculate derived metrics
            drawdown_pct = 0.0
            if account.peak_equity > 0:
                drawdown_pct = ((account.peak_equity - account.equity) / account.peak_equity) * 100

            # Count open positions
            stmt = select(func.count(Trade.id)).where(
                and_(
                    Trade.master_id == master_id,
                    Trade.status == "OPEN"
                )
            )
            result = await db.execute(stmt)
            open_positions_count = result.scalar() or 0

            # Calculate daily P&L from today's closed trades
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_stmt = select(func.coalesce(func.sum(Trade.net_profit), 0.0)).where(
                and_(
                    Trade.master_id == master_id,
                    Trade.status == "CLOSED",
                    Trade.closed_at >= today_start,
                )
            )
            daily_result = await db.execute(daily_stmt)
            daily_pnl = daily_result.scalar() or 0.0

            logger.info(
                "account_retrieved",
                master_id=str(master_id),
                balance=account.balance,
                equity=account.equity
            )

            return AccountResponse(
                id=account.id,
                mt5_login=account.mt5_login,
                broker=account.broker,
                balance=account.balance,
                equity=account.equity,
                peak_equity=account.peak_equity,
                status=account.status,
                drawdown_pct=drawdown_pct,
                daily_pnl=daily_pnl,
                open_positions_count=open_positions_count
            )

        except Exception as e:
            logger.error(
                "get_account_error",
                error=str(e),
                master_id=str(master_id)
            )
            raise

    @staticmethod
    async def update_account_equity(
        db: AsyncSession,
        master_id: UUID,
        equity: float,
        balance: Optional[float] = None
    ) -> AccountResponse:
        """
        Update account equity (and optionally balance).

        PURPOSE: Persist equity updates from MT5 bridge and track peak equity
        for drawdown calculations. Publishes equity_updated event.

        CALLED BY: MT5 sync process, position update handlers

        Args:
            db: Async database session
            master_id: UUID of the master account
            equity: New equity value
            balance: Optional new balance value

        Returns:
            AccountResponse: Updated account

        Raises:
            ValueError: If account not found
        """
        logger.info(
            "update_account_equity_started",
            master_id=str(master_id),
            equity=equity
        )

        try:
            stmt = select(MasterAccount).where(MasterAccount.id == master_id)
            result = await db.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                logger.error("account_not_found", master_id=str(master_id))
                raise ValueError(f"Account {master_id} not found")

            old_equity = account.equity

            # Update equity
            account.equity = equity

            # Update balance if provided
            if balance is not None:
                account.balance = balance

            # Track peak equity
            if equity > account.peak_equity:
                account.peak_equity = equity

            account.updated_at = datetime.utcnow()

            await db.flush()
            await db.commit()

            logger.info(
                "account_equity_updated",
                master_id=str(master_id),
                old_equity=old_equity,
                new_equity=equity,
                peak_equity=account.peak_equity
            )

            # Publish event
            event_bus = get_event_bus()
            await event_bus.publish(
                event_type="equity_updated",
                data={
                    "master_id": str(master_id),
                    "old_equity": old_equity,
                    "new_equity": equity,
                    "balance": account.balance,
                    "peak_equity": account.peak_equity
                },
                source="account_service",
                severity="INFO"
            )

            return await AccountService.get_account(db, master_id)

        except Exception as e:
            logger.error(
                "update_account_equity_error",
                error=str(e),
                master_id=str(master_id)
            )
            await db.rollback()
            raise

    @staticmethod
    async def get_equity_curve(
        db: AsyncSession,
        master_id: UUID,
        days: int = 30
    ) -> list[dict]:
        """
        Retrieve equity curve from periodic snapshots recorded by the engine.

        PURPOSE: Return historical equity values for charting and performance
        analysis.  Data comes from the ``equity_snapshots`` table which the
        engine populates every ~5 minutes.  Falls back to trade-based
        reconstruction if no snapshots exist yet.

        CALLED BY: Dashboard endpoint, equity chart endpoints

        Args:
            db: Async database session
            master_id: UUID of the master account
            days: Number of days to look back (default: 30)

        Returns:
            list[dict]: List of data points with keys:
                - timestamp: ISO-8601 datetime string
                - equity: Equity value at that time
                - balance: Balance at that time
                - margin_used: Margin in use at that time
                - drawdown: Drawdown percentage from peak
        """
        logger.info(
            "get_equity_curve_started",
            master_id=str(master_id),
            days=days
        )

        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # --- Try snapshot-based curve first ---
            try:
                stmt = (
                    select(EquitySnapshot)
                    .where(
                        and_(
                            EquitySnapshot.master_id == master_id,
                            EquitySnapshot.timestamp >= start_date,
                        )
                    )
                    .order_by(EquitySnapshot.timestamp.asc())
                )
                result = await db.execute(stmt)
                snapshots = result.scalars().all()
            except Exception:
                # Table may not exist yet (pre-migration)
                snapshots = []

            if snapshots:
                curve = []
                peak = 0.0
                for snap in snapshots:
                    if snap.equity > peak:
                        peak = snap.equity
                    dd = ((peak - snap.equity) / peak * 100) if peak > 0 else 0.0
                    curve.append({
                        "timestamp": snap.timestamp.isoformat(),
                        "equity": snap.equity,
                        "balance": snap.balance,
                        "margin_used": snap.margin_used,
                        "drawdown": round(dd, 2),
                    })
                logger.info(
                    "equity_curve_from_snapshots",
                    master_id=str(master_id),
                    points=len(curve),
                )
                return curve

            # --- Fallback: reconstruct from closed trades ---
            stmt = select(MasterAccount).where(MasterAccount.id == master_id)
            result = await db.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                logger.error("account_not_found", master_id=str(master_id))
                return []

            stmt = (
                select(Trade)
                .where(
                    and_(
                        Trade.master_id == master_id,
                        Trade.status == "CLOSED",
                        Trade.closed_at >= start_date,
                        Trade.closed_at <= end_date,
                    )
                )
                .order_by(Trade.closed_at)
            )
            result = await db.execute(stmt)
            trades = result.scalars().all()

            curve = []
            running_equity = account.balance
            running_peak = account.balance

            if trades:
                for trade in trades:
                    running_equity += trade.net_profit
                    if running_equity > running_peak:
                        running_peak = running_equity
                    dd = ((running_peak - running_equity) / running_peak * 100) if running_peak > 0 else 0.0
                    curve.append({
                        "timestamp": trade.closed_at.isoformat(),
                        "equity": running_equity,
                        "balance": account.balance,
                        "margin_used": 0.0,
                        "drawdown": round(dd, 2),
                    })
            else:
                dd = 0.0
                if account.peak_equity > 0:
                    dd = ((account.peak_equity - account.equity) / account.peak_equity) * 100
                curve.append({
                    "timestamp": end_date.isoformat(),
                    "equity": account.equity,
                    "balance": account.balance,
                    "margin_used": 0.0,
                    "drawdown": round(dd, 2),
                })

            logger.info(
                "equity_curve_from_trades_fallback",
                master_id=str(master_id),
                points=len(curve),
            )
            return curve

        except Exception as e:
            logger.error(
                "get_equity_curve_error",
                error=str(e),
                master_id=str(master_id)
            )
            raise

    @staticmethod
    async def check_account_health(
        db: AsyncSession,
        master_id: UUID
    ) -> dict:
        """
        Check account health metrics for risk monitoring.

        PURPOSE: Calculate key risk indicators including margin level,
        drawdown, and daily P&L for position management and risk alerts.

        CALLED BY: Risk monitoring endpoints, alert systems

        Args:
            db: Async database session
            master_id: UUID of the master account

        Returns:
            dict: Health metrics with keys:
                - margin_level: Margin level percentage
                - drawdown: Current drawdown percentage
                - daily_pnl: Today's P&L
                - open_positions: Number of open trades
                - risk_level: Computed risk level (low/medium/high/critical)
                - status: Account status (healthy/warning/critical)
        """
        logger.info("check_account_health_started", master_id=str(master_id))

        try:
            # Get account
            stmt = select(MasterAccount).where(MasterAccount.id == master_id)
            result = await db.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                logger.error("account_not_found", master_id=str(master_id))
                return {
                    "margin_level": 0.0,
                    "drawdown": 0.0,
                    "daily_pnl": 0.0,
                    "open_positions": 0,
                    "risk_level": "unknown",
                    "status": "error"
                }

            # Calculate margin level (mock: assuming healthy if equity > balance * 0.5)
            margin_level = (account.equity / account.balance * 100) if account.balance > 0 else 0.0

            # Calculate drawdown
            drawdown = 0.0
            if account.peak_equity > 0:
                drawdown = ((account.peak_equity - account.equity) / account.peak_equity) * 100

            # Calculate daily P&L from today's closed trades
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_stmt = select(func.coalesce(func.sum(Trade.net_profit), 0.0)).where(
                and_(
                    Trade.master_id == master_id,
                    Trade.status == "CLOSED",
                    Trade.closed_at >= today_start,
                )
            )
            daily_result = await db.execute(daily_stmt)
            daily_pnl = daily_result.scalar() or 0.0

            # Count open positions
            stmt = select(func.count(Trade.id)).where(
                and_(
                    Trade.master_id == master_id,
                    Trade.status == "OPEN"
                )
            )
            result = await db.execute(stmt)
            open_positions = result.scalar() or 0

            # Determine risk level and status
            risk_level = "low"
            status = "healthy"

            if margin_level < 50:
                risk_level = "critical"
                status = "critical"
            elif margin_level < 100:
                risk_level = "high"
                status = "warning"
            elif margin_level < 200:
                risk_level = "medium"
                status = "warning"
            else:
                risk_level = "low"
                status = "healthy"

            # Check drawdown threshold
            if drawdown > 15:
                status = "critical"
                risk_level = "critical"
            elif drawdown > 10:
                status = "warning"

            logger.info(
                "account_health_checked",
                master_id=str(master_id),
                margin_level=margin_level,
                drawdown=drawdown,
                daily_pnl=daily_pnl,
                risk_level=risk_level
            )

            return {
                "margin_level": margin_level,
                "drawdown": drawdown,
                "daily_pnl": daily_pnl,
                "open_positions": open_positions,
                "risk_level": risk_level,
                "status": status
            }

        except Exception as e:
            logger.error(
                "check_account_health_error",
                error=str(e),
                master_id=str(master_id)
            )
            raise
