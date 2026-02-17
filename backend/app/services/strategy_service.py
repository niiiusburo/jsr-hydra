"""
Strategy service for JSR Hydra trading system.

PURPOSE: Handle strategy lifecycle management including creation, retrieval,
updates, and performance metrics calculation.

CALLED BY: app.api.routes.strategies, internal modules for strategy performance updates
"""

from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy
from app.models.trade import Trade
from app.schemas.strategy import StrategyResponse, StrategyUpdate, StrategyMetrics
from app.events.bus import get_event_bus
from app.utils.logger import get_logger


logger = get_logger("services.strategy")


class StrategyService:
    """
    Service for managing trading strategies.

    PURPOSE: Provide business logic for strategy operations including retrieval,
    configuration updates, and performance metrics calculation.

    CALLED BY: API routes for strategy endpoints
    """

    @staticmethod
    async def get_all_strategies(
        db: AsyncSession
    ) -> list[StrategyResponse]:
        """
        Retrieve all strategies from the system.

        PURPOSE: Get a list of all available strategies with their
        current configurations and performance metrics.

        CALLED BY: GET /api/strategies endpoint

        Args:
            db: Async database session

        Returns:
            list[StrategyResponse]: List of all strategies
        """
        logger.info("get_all_strategies_started")

        try:
            stmt = select(Strategy).order_by(Strategy.code)
            result = await db.execute(stmt)
            strategies = result.scalars().all()

            logger.info("all_strategies_retrieved", count=len(strategies))

            return [StrategyResponse.model_validate(s) for s in strategies]

        except Exception as e:
            logger.error("get_all_strategies_error", error=str(e))
            raise

    @staticmethod
    async def get_strategy_by_code(
        db: AsyncSession,
        code: str
    ) -> Optional[StrategyResponse]:
        """
        Retrieve a single strategy by its code.

        PURPOSE: Fetch detailed strategy configuration and metrics
        for a specific strategy code.

        CALLED BY: GET /api/strategies/{code} endpoint

        Args:
            db: Async database session
            code: Strategy code (e.g., 'TREND_FOLLOW')

        Returns:
            StrategyResponse if found, None otherwise
        """
        logger.info("get_strategy_by_code_started", code=code)

        try:
            stmt = select(Strategy).where(Strategy.code == code)
            result = await db.execute(stmt)
            strategy = result.scalar_one_or_none()

            if not strategy:
                logger.info("strategy_not_found", code=code)
                return None

            logger.info("strategy_retrieved", code=code)
            return StrategyResponse.model_validate(strategy)

        except Exception as e:
            logger.error("get_strategy_by_code_error", error=str(e), code=code)
            raise

    @staticmethod
    async def update_strategy(
        db: AsyncSession,
        code: str,
        update: StrategyUpdate
    ) -> StrategyResponse:
        """
        Update a strategy's configuration and status.

        PURPOSE: Modify strategy settings like status, allocation percentage,
        and configuration parameters.

        CALLED BY: PATCH /api/strategies/{code} endpoint

        Args:
            db: Async database session
            code: Strategy code to update
            update: StrategyUpdate schema with fields to update

        Returns:
            StrategyResponse: Updated strategy

        Raises:
            ValueError: If strategy not found
        """
        logger.info("update_strategy_started", code=code)

        try:
            stmt = select(Strategy).where(Strategy.code == code)
            result = await db.execute(stmt)
            strategy = result.scalar_one_or_none()

            if not strategy:
                logger.error("strategy_not_found", code=code)
                raise ValueError(f"Strategy '{code}' not found")

            # Track old status for event publishing
            old_status = strategy.status

            # Update fields
            update_dict = update.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(strategy, field, value)

            strategy.updated_at = datetime.utcnow()

            await db.flush()
            await db.commit()

            logger.info(
                "strategy_updated",
                code=code,
                old_status=old_status,
                new_status=strategy.status
            )

            # Publish event if status changed
            if old_status != strategy.status:
                event_bus = get_event_bus()
                await event_bus.publish(
                    event_type="strategy_status_changed",
                    data={
                        "strategy_id": str(strategy.id),
                        "strategy_code": strategy.code,
                        "old_status": old_status,
                        "new_status": strategy.status
                    },
                    source="strategy_service",
                    severity="INFO"
                )

            return StrategyResponse.model_validate(strategy)

        except Exception as e:
            logger.error("update_strategy_error", error=str(e), code=code)
            await db.rollback()
            raise

    @staticmethod
    async def get_strategy_metrics(
        db: AsyncSession,
        code: str,
        period_days: int = 30
    ) -> StrategyMetrics:
        """
        Calculate detailed performance metrics for a strategy over a period.

        PURPOSE: Compute win rate, profit factor, and daily performance
        for a given strategy over the specified period.

        CALLED BY: Dashboard endpoint, analytics endpoints

        Args:
            db: Async database session
            code: Strategy code
            period_days: Number of days to look back (default: 30)

        Returns:
            StrategyMetrics: Performance metrics for the period

        Raises:
            ValueError: If strategy not found
        """
        logger.info("get_strategy_metrics_started", code=code, period_days=period_days)

        try:
            # Get strategy
            stmt = select(Strategy).where(Strategy.code == code)
            result = await db.execute(stmt)
            strategy = result.scalar_one_or_none()

            if not strategy:
                logger.error("strategy_not_found", code=code)
                raise ValueError(f"Strategy '{code}' not found")

            # Calculate period dates
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=period_days)
            today = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            # Fetch closed trades for strategy in period
            stmt = select(Trade).where(
                and_(
                    Trade.strategy_id == strategy.id,
                    Trade.status == "CLOSED",
                    Trade.closed_at >= start_date,
                    Trade.closed_at <= end_date
                )
            )
            result = await db.execute(stmt)
            period_trades = result.scalars().all()

            # Fetch today's trades
            stmt = select(Trade).where(
                and_(
                    Trade.strategy_id == strategy.id,
                    Trade.opened_at >= today,
                    Trade.opened_at <= end_date
                )
            )
            result = await db.execute(stmt)
            today_trades = result.scalars().all()

            # Calculate period metrics (7d and 30d)
            period_7d_start = end_date - timedelta(days=7)
            stmt = select(Trade).where(
                and_(
                    Trade.strategy_id == strategy.id,
                    Trade.status == "CLOSED",
                    Trade.closed_at >= period_7d_start,
                    Trade.closed_at <= end_date
                )
            )
            result = await db.execute(stmt)
            trades_7d = result.scalars().all()

            trades_30d = period_trades

            # Calculate metrics
            def calc_metrics(trades):
                if not trades:
                    return 0.0, 0.0

                profits = [t.net_profit for t in trades]
                winning = sum(1 for p in profits if p > 0)
                total = len(profits)
                win_rate = winning / total if total > 0 else 0.0

                gross_profit = sum(p for p in profits if p > 0)
                gross_loss = abs(sum(p for p in profits if p < 0))
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

                return win_rate, profit_factor

            win_rate_7d, profit_factor_7d = calc_metrics(trades_7d)
            win_rate_30d, profit_factor_30d = calc_metrics(trades_30d)

            # Today's metrics
            trades_today = len([t for t in today_trades if t.status == "CLOSED"])
            pnl_today = sum(t.net_profit for t in today_trades)

            logger.info(
                "strategy_metrics_calculated",
                code=code,
                trades_30d=len(trades_30d),
                win_rate_30d=win_rate_30d,
                pnl_today=pnl_today
            )

            return StrategyMetrics(
                code=code,
                name=strategy.name,
                win_rate_7d=win_rate_7d,
                win_rate_30d=win_rate_30d,
                profit_factor_7d=profit_factor_7d,
                profit_factor_30d=profit_factor_30d,
                trades_today=trades_today,
                pnl_today=pnl_today
            )

        except Exception as e:
            logger.error(
                "get_strategy_metrics_error",
                error=str(e),
                code=code
            )
            raise

    @staticmethod
    async def update_strategy_performance(
        db: AsyncSession,
        code: str,
        trade: Trade
    ) -> None:
        """
        Update strategy performance metrics after a trade closes.

        PURPOSE: Recalculate win_rate, profit_factor, and total_trades
        whenever a trade closes to keep metrics current.

        CALLED BY: Trade service when closing trades, batch update jobs

        Args:
            db: Async database session
            code: Strategy code to update
            trade: The closed trade that triggered the update

        Returns:
            None

        Raises:
            ValueError: If strategy not found
        """
        logger.info("update_strategy_performance_started", code=code)

        try:
            # Get strategy
            stmt = select(Strategy).where(Strategy.code == code)
            result = await db.execute(stmt)
            strategy = result.scalar_one_or_none()

            if not strategy:
                logger.error("strategy_not_found", code=code)
                raise ValueError(f"Strategy '{code}' not found")

            # Get all closed trades for this strategy
            stmt = select(Trade).where(
                and_(
                    Trade.strategy_id == strategy.id,
                    Trade.status == "CLOSED"
                )
            )
            result = await db.execute(stmt)
            trades = result.scalars().all()

            if not trades:
                logger.info("no_closed_trades_for_strategy", code=code)
                strategy.total_trades = 0
                strategy.win_rate = 0.0
                strategy.profit_factor = 0.0
                strategy.total_profit = 0.0
            else:
                # Calculate metrics
                profits = [t.net_profit for t in trades]
                total_trades = len(trades)
                winning_trades = sum(1 for p in profits if p > 0)
                total_profit = sum(profits)

                # Win rate
                win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

                # Profit factor
                gross_profit = sum(p for p in profits if p > 0)
                gross_loss = abs(sum(p for p in profits if p < 0))
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

                # Update strategy
                strategy.total_trades = total_trades
                strategy.win_rate = win_rate
                strategy.profit_factor = profit_factor
                strategy.total_profit = total_profit

            strategy.updated_at = datetime.utcnow()

            await db.flush()
            await db.commit()

            logger.info(
                "strategy_performance_updated",
                code=code,
                total_trades=strategy.total_trades,
                win_rate=strategy.win_rate,
                profit_factor=strategy.profit_factor
            )

            # Publish event
            event_bus = get_event_bus()
            await event_bus.publish(
                event_type="strategy_performance_updated",
                data={
                    "strategy_id": str(strategy.id),
                    "strategy_code": strategy.code,
                    "total_trades": strategy.total_trades,
                    "win_rate": strategy.win_rate,
                    "profit_factor": strategy.profit_factor,
                    "total_profit": strategy.total_profit
                },
                source="strategy_service",
                severity="INFO"
            )

        except Exception as e:
            logger.error(
                "update_strategy_performance_error",
                error=str(e),
                code=code
            )
            await db.rollback()
            raise
