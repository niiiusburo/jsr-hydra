"""
Dashboard service for JSR Hydra trading system.

PURPOSE: Assemble comprehensive dashboard data from multiple sources
(account, strategies, allocations, regime, recent trades, equity curve)
into a single cohesive response.

CALLED BY: app.api.routes.dashboard, web UI dashboard endpoint
"""

from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import MasterAccount
from app.models.trade import Trade
from app.models.strategy import Strategy
from app.models.allocation import CapitalAllocation
from app.schemas.dashboard import DashboardSummary
from app.schemas.account import AccountResponse
from app.schemas.allocation import AllocationResponse
from app.schemas.regime import RegimeResponse
from app.schemas.strategy import StrategyMetrics
from app.schemas.trade import TradeResponse
from app.config.settings import settings
from app.services.account_service import AccountService
from app.services.regime_service import RegimeService
from app.services.strategy_service import StrategyService
from app.events.bus import get_event_bus
from app.utils.logger import get_logger


logger = get_logger("services.dashboard")


class DashboardService:
    """
    Service for assembling comprehensive dashboard summary.

    PURPOSE: Aggregate data from multiple services and data sources into
    a single dashboard response optimized for UI rendering and analysis.

    CALLED BY: Dashboard API endpoints
    """

    @staticmethod
    async def get_dashboard_summary(
        db: AsyncSession,
        master_id: UUID
    ) -> DashboardSummary:
        """
        Assemble comprehensive dashboard summary for a master account.

        PURPOSE: Fetch and combine account state, regime, allocations,
        strategy metrics, recent trades, and equity curve into a single
        cohesive response for dashboard display.

        CALLED BY: GET /api/dashboard/{master_id} endpoint

        Args:
            db: Async database session
            master_id: UUID of the master account

        Returns:
            DashboardSummary: Comprehensive dashboard data

        Raises:
            ValueError: If master account not found
        """
        logger.info("get_dashboard_summary_started", master_id=str(master_id))

        try:
            # 1. Get account
            account = await AccountService.get_account(db, master_id)
            if not account:
                logger.error("account_not_found", master_id=str(master_id))
                raise ValueError(f"Master account {master_id} not found")

            # 2. Get current regime
            regime = await RegimeService.get_current_regime(db)

            # 3. Get allocations
            allocations = await DashboardService._get_allocations(db, master_id)

            # 4. Get strategy metrics
            strategies = await DashboardService._get_strategy_metrics(db, master_id)

            # 5. Get recent trades
            recent_trades = await DashboardService._get_recent_trades(db, master_id, limit=10)

            # 6. Get equity curve
            equity_curve = await AccountService.get_equity_curve(db, master_id, days=30)

            # 7. Determine system status
            system_status = await DashboardService._determine_system_status(db, master_id)

            logger.info(
                "dashboard_summary_assembled",
                master_id=str(master_id),
                allocations=len(allocations),
                strategies=len(strategies),
                recent_trades=len(recent_trades),
                equity_points=len(equity_curve)
            )

            # Publish event
            event_bus = get_event_bus()
            await event_bus.publish(
                event_type="dashboard_accessed",
                data={
                    "master_id": str(master_id),
                    "timestamp": datetime.utcnow().isoformat(),
                    "account_equity": account.equity,
                    "system_status": system_status
                },
                source="dashboard_service",
                severity="INFO"
            )

            return DashboardSummary(
                account=account,
                regime=regime,
                allocations=allocations,
                strategies=strategies,
                recent_trades=recent_trades,
                equity_curve=equity_curve,
                system_status=system_status,
                version=settings.VERSION if hasattr(settings, "VERSION") else "1.0.0"
            )

        except Exception as e:
            logger.error(
                "get_dashboard_summary_error",
                error=str(e),
                master_id=str(master_id)
            )
            raise

    @staticmethod
    async def _get_allocations(
        db: AsyncSession,
        master_id: UUID
    ) -> list[AllocationResponse]:
        """
        Retrieve current capital allocations for a master account.

        PURPOSE: Internal method to fetch strategy allocations with strategy
        names and regime information.

        CALLED BY: get_dashboard_summary

        Args:
            db: Async database session
            master_id: UUID of the master account

        Returns:
            list[AllocationResponse]: Current allocations
        """
        logger.info("_get_allocations_started", master_id=str(master_id))

        try:
            # Get latest allocations per strategy
            stmt = (
                select(CapitalAllocation)
                .where(CapitalAllocation.master_id == master_id)
                .order_by(
                    CapitalAllocation.strategy_id,
                    desc(CapitalAllocation.allocated_at)
                )
            )
            result = await db.execute(stmt)
            allocations = result.scalars().all()

            # Group by strategy, keeping latest
            latest_allocations = {}
            for alloc in allocations:
                if alloc.strategy_id not in latest_allocations:
                    latest_allocations[alloc.strategy_id] = alloc

            # Build responses
            responses = []
            for alloc in latest_allocations.values():
                # Fetch strategy info
                stmt = select(Strategy).where(Strategy.id == alloc.strategy_id)
                result = await db.execute(stmt)
                strategy = result.scalar_one_or_none()

                if strategy:
                    regime_name = None
                    if alloc.regime_id:
                        from app.models.regime import RegimeState
                        stmt = select(RegimeState).where(RegimeState.id == alloc.regime_id)
                        result = await db.execute(stmt)
                        regime = result.scalar_one_or_none()
                        if regime:
                            regime_name = regime.regime

                    responses.append(
                        AllocationResponse(
                            strategy_code=strategy.code,
                            strategy_name=strategy.name,
                            weight=alloc.weight,
                            source=alloc.source,
                            regime=regime_name,
                            allocated_at=alloc.allocated_at
                        )
                    )

            logger.info(
                "_get_allocations_completed",
                master_id=str(master_id),
                count=len(responses)
            )

            return responses

        except Exception as e:
            logger.error("_get_allocations_error", error=str(e))
            return []

    @staticmethod
    async def _get_strategy_metrics(
        db: AsyncSession,
        master_id: UUID
    ) -> list[StrategyMetrics]:
        """
        Retrieve performance metrics for all strategies used by the account.

        PURPOSE: Internal method to fetch strategy metrics for dashboard display.

        CALLED BY: get_dashboard_summary

        Args:
            db: Async database session
            master_id: UUID of the master account

        Returns:
            list[StrategyMetrics]: Performance metrics for active strategies
        """
        logger.info("_get_strategy_metrics_started", master_id=str(master_id))

        try:
            # Get strategies used by this account (from trades)
            stmt = (
                select(Strategy.code)
                .distinct()
                .select_from(Trade)
                .join(Strategy, Trade.strategy_id == Strategy.id)
                .where(Trade.master_id == master_id)
            )
            result = await db.execute(stmt)
            strategy_codes = result.scalars().all()

            metrics = []
            for code in strategy_codes:
                try:
                    metric = await StrategyService.get_strategy_metrics(db, code, period_days=30)
                    metrics.append(metric)
                except Exception as e:
                    logger.warning("failed_to_get_metrics_for_strategy", code=code, error=str(e))
                    continue

            logger.info(
                "_get_strategy_metrics_completed",
                master_id=str(master_id),
                count=len(metrics)
            )

            return metrics

        except Exception as e:
            logger.error("_get_strategy_metrics_error", error=str(e))
            return []

    @staticmethod
    async def _get_recent_trades(
        db: AsyncSession,
        master_id: UUID,
        limit: int = 10
    ) -> list[TradeResponse]:
        """
        Retrieve recently closed trades for the account.

        PURPOSE: Internal method to fetch recent trade history for dashboard display.

        CALLED BY: get_dashboard_summary

        Args:
            db: Async database session
            master_id: UUID of the master account
            limit: Maximum number of recent trades to retrieve

        Returns:
            list[TradeResponse]: Recent closed trades, newest first
        """
        logger.info(
            "_get_recent_trades_started",
            master_id=str(master_id),
            limit=limit
        )

        try:
            stmt = (
                select(Trade)
                .where(
                    and_(
                        Trade.master_id == master_id,
                        Trade.status == "CLOSED"
                    )
                )
                .order_by(desc(Trade.closed_at))
                .limit(limit)
            )
            result = await db.execute(stmt)
            trades = result.scalars().all()

            logger.info(
                "_get_recent_trades_completed",
                master_id=str(master_id),
                count=len(trades)
            )

            return [TradeResponse.model_validate(t) for t in trades]

        except Exception as e:
            logger.error("_get_recent_trades_error", error=str(e))
            return []

    @staticmethod
    async def _determine_system_status(
        db: AsyncSession,
        master_id: UUID
    ) -> str:
        """
        Determine overall system status based on account and market conditions.

        PURPOSE: Internal method to compute system-wide status for dashboard header.

        CALLED BY: get_dashboard_summary

        Args:
            db: Async database session
            master_id: UUID of the master account

        Returns:
            str: System status (operational/warning/critical/offline)
        """
        logger.info("_determine_system_status_started", master_id=str(master_id))

        try:
            # Get account
            stmt = select(MasterAccount).where(MasterAccount.id == master_id)
            result = await db.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                return "offline"

            # Check account status
            if account.status != "RUNNING":
                return "critical"

            # Check drawdown
            drawdown = 0.0
            if account.peak_equity > 0:
                drawdown = ((account.peak_equity - account.equity) / account.peak_equity) * 100

            if drawdown > 15:
                return "critical"
            elif drawdown > 10:
                return "warning"

            # Check margin (simplified)
            margin_level = (account.equity / account.balance * 100) if account.balance > 0 else 0.0

            if margin_level < 50:
                return "critical"
            elif margin_level < 100:
                return "warning"

            return "operational"

        except Exception as e:
            logger.error("_determine_system_status_error", error=str(e))
            return "offline"
