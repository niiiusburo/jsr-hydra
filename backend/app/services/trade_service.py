"""
Trade service for JSR Hydra trading system.

PURPOSE: Handle trade creation, querying, updates, and statistics calculation.
Maintains trade lifecycle from creation to closure while publishing state change events.

CALLED BY: app.api.routes.trades
"""

from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional
from decimal import Decimal

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import EventType
from app.models.trade import Trade
from app.models.strategy import Strategy
from app.schemas.trade import TradeCreate, TradeUpdate, TradeResponse, TradeList, TradeStats
from app.events.bus import get_event_bus
from app.utils.logger import get_logger


logger = get_logger("services.trade")


class TradeService:
    """
    Service for managing trades in the system.

    PURPOSE: Provide business logic for trade operations including creation,
    retrieval, updates, and statistical analysis while publishing events
    for important state changes.

    CALLED BY: API routes for trade endpoints
    """

    @staticmethod
    async def create_trade(
        db: AsyncSession,
        master_id: UUID,
        trade_data: TradeCreate,
        status: str = "PENDING",
        mt5_ticket: Optional[int] = None
    ) -> TradeResponse:
        """
        Create a new trade record in the database.

        PURPOSE: Persist a new trade and publish trade_opened event for
        downstream processing (risk management, position tracking, etc).

        CALLED BY: POST /api/trades endpoint

        Args:
            db: Async database session
            master_id: UUID of the master account opening the trade
            trade_data: TradeCreate schema with trade details
            status: Initial trade status (default "PENDING", pass "OPEN" to skip two-phase write)
            mt5_ticket: Optional MT5 ticket number to set on creation

        Returns:
            TradeResponse: Created trade with all fields populated

        Raises:
            ValueError: If strategy_code is invalid or other validation fails
        """
        logger.info("create_trade_started", master_id=str(master_id))

        try:
            # Resolve strategy_code to strategy_id if provided
            strategy_id = None
            if trade_data.strategy_code:
                stmt = select(Strategy).where(
                    Strategy.code == trade_data.strategy_code
                )
                result = await db.execute(stmt)
                strategy = result.scalar_one_or_none()
                if not strategy:
                    logger.error(
                        "strategy_not_found",
                        strategy_code=trade_data.strategy_code
                    )
                    raise ValueError(f"Strategy '{trade_data.strategy_code}' not found")
                strategy_id = strategy.id

            # Create new trade record
            trade = Trade(
                master_id=master_id,
                strategy_id=strategy_id,
                symbol=trade_data.symbol,
                direction=trade_data.direction.upper(),
                lots=trade_data.lots,
                entry_price=trade_data.entry_price,
                stop_loss=trade_data.stop_loss,
                take_profit=trade_data.take_profit,
                reason=trade_data.reason,
                status=status,
                opened_at=datetime.utcnow()
            )

            if mt5_ticket is not None:
                trade.mt5_ticket = mt5_ticket

            db.add(trade)
            await db.commit()
            await db.refresh(trade)

            logger.info(
                "trade_created",
                trade_id=str(trade.id),
                master_id=str(master_id),
                symbol=trade.symbol,
                direction=trade.direction
            )

            # Publish TRADE_OPENED event (separate from DB transaction — do not rollback on failure)
            try:
                event_bus = get_event_bus()
                await event_bus.publish(
                    event_type=EventType.TRADE_OPENED.value,
                    data={
                        "trade_id": str(trade.id),
                        "master_id": str(master_id),
                        "strategy_id": str(strategy_id) if strategy_id else None,
                        "symbol": trade.symbol,
                        "direction": trade.direction,
                        "lots": trade.lots,
                        "entry_price": trade.entry_price,
                        "stop_loss": trade.stop_loss,
                        "take_profit": trade.take_profit
                    },
                    source="trade_service",
                    severity="INFO"
                )
            except Exception as e:
                logger.warning("event_publish_failed", error=str(e), trade_id=str(trade.id))

            return TradeResponse.model_validate(trade)

        except Exception as e:
            logger.error("create_trade_error", error=str(e), master_id=str(master_id))
            raise

    @staticmethod
    async def get_trade(
        db: AsyncSession,
        trade_id: UUID
    ) -> Optional[TradeResponse]:
        """
        Retrieve a single trade by ID.

        PURPOSE: Fetch detailed trade information for a specific trade.

        CALLED BY: GET /api/trades/{trade_id} endpoint

        Args:
            db: Async database session
            trade_id: UUID of the trade to retrieve

        Returns:
            TradeResponse if found, None otherwise
        """
        logger.info("get_trade_started", trade_id=str(trade_id))

        try:
            stmt = select(Trade).where(Trade.id == trade_id)
            result = await db.execute(stmt)
            trade = result.scalar_one_or_none()

            if not trade:
                logger.info("trade_not_found", trade_id=str(trade_id))
                return None

            logger.info("trade_retrieved", trade_id=str(trade_id))
            return TradeResponse.model_validate(trade)

        except Exception as e:
            logger.error("get_trade_error", error=str(e), trade_id=str(trade_id))
            raise

    @staticmethod
    async def list_trades(
        db: AsyncSession,
        master_id: UUID,
        filters: Optional[dict] = None,
        page: int = 1,
        per_page: int = 50
    ) -> TradeList:
        """
        List trades with optional filtering and pagination.

        PURPOSE: Retrieve paginated list of trades for a master account
        with optional filtering by status, strategy, symbol, or date range.

        CALLED BY: GET /api/trades endpoint

        Args:
            db: Async database session
            master_id: UUID of the master account
            filters: Optional dict with filters:
                - status: Trade status (PENDING, OPEN, CLOSED, CANCELLED)
                - strategy_code: Filter by strategy code
                - symbol: Filter by trading symbol
                - start_date: Filter trades opened after this date
                - end_date: Filter trades opened before this date
            page: Page number (1-indexed)
            per_page: Number of trades per page

        Returns:
            TradeList: Paginated response with trades and metadata
        """
        logger.info(
            "list_trades_started",
            master_id=str(master_id),
            page=page,
            per_page=per_page
        )

        try:
            filters = filters or {}

            # Build query with master_id filter
            stmt = select(Trade).where(Trade.master_id == master_id)

            # Apply optional filters
            if filters.get("status"):
                stmt = stmt.where(Trade.status == filters["status"])

            if filters.get("symbol"):
                stmt = stmt.where(Trade.symbol == filters["symbol"])

            resolved_strategy_id = None
            if filters.get("strategy_code"):
                strategy_stmt = select(Strategy.id).where(
                    Strategy.code == filters["strategy_code"]
                )
                strategy_result = await db.execute(strategy_stmt)
                resolved_strategy_id = strategy_result.scalar_one_or_none()
                if resolved_strategy_id:
                    stmt = stmt.where(Trade.strategy_id == resolved_strategy_id)

            resolved_start_date = None
            if filters.get("start_date"):
                resolved_start_date = filters["start_date"]
                if isinstance(resolved_start_date, str):
                    resolved_start_date = datetime.fromisoformat(resolved_start_date)
                stmt = stmt.where(Trade.opened_at >= resolved_start_date)

            resolved_end_date = None
            if filters.get("end_date"):
                resolved_end_date = filters["end_date"]
                if isinstance(resolved_end_date, str):
                    resolved_end_date = datetime.fromisoformat(resolved_end_date)
                stmt = stmt.where(Trade.opened_at <= resolved_end_date)

            # Count total — rebuild with the same filters to avoid SQLAlchemy 2.x subquery issues
            count_stmt = select(func.count(Trade.id)).where(Trade.master_id == master_id)
            if filters.get("status"):
                count_stmt = count_stmt.where(Trade.status == filters["status"])
            if filters.get("symbol"):
                count_stmt = count_stmt.where(Trade.symbol == filters["symbol"])
            if resolved_strategy_id:
                count_stmt = count_stmt.where(Trade.strategy_id == resolved_strategy_id)
            if resolved_start_date is not None:
                count_stmt = count_stmt.where(Trade.opened_at >= resolved_start_date)
            if resolved_end_date is not None:
                count_stmt = count_stmt.where(Trade.opened_at <= resolved_end_date)
            count_result = await db.execute(count_stmt)
            total = count_result.scalar() or 0

            # Apply ordering and pagination
            offset = (page - 1) * per_page
            stmt = stmt.order_by(desc(Trade.opened_at)).offset(offset).limit(per_page)

            result = await db.execute(stmt)
            trades = result.scalars().all()

            logger.info(
                "trades_retrieved",
                master_id=str(master_id),
                count=len(trades),
                total=total
            )

            trade_responses = [TradeResponse.model_validate(t) for t in trades]

            return TradeList(
                trades=trade_responses,
                total=total,
                page=page,
                per_page=per_page
            )

        except Exception as e:
            logger.error(
                "list_trades_error",
                error=str(e),
                master_id=str(master_id)
            )
            raise

    @staticmethod
    async def update_trade(
        db: AsyncSession,
        trade_id: UUID,
        update: TradeUpdate
    ) -> TradeResponse:
        """
        Update an existing trade's mutable fields.

        PURPOSE: Update trade details like exit price, profit, and status.
        Publishes events for significant state transitions (e.g., CLOSED).

        CALLED BY: PATCH /api/trades/{trade_id} endpoint

        Args:
            db: Async database session
            trade_id: UUID of the trade to update
            update: TradeUpdate schema with fields to update

        Returns:
            TradeResponse: Updated trade

        Raises:
            ValueError: If trade not found
        """
        logger.info("update_trade_started", trade_id=str(trade_id))

        try:
            # Fetch trade
            stmt = select(Trade).where(Trade.id == trade_id)
            result = await db.execute(stmt)
            trade = result.scalar_one_or_none()

            if not trade:
                logger.error("trade_not_found", trade_id=str(trade_id))
                raise ValueError(f"Trade {trade_id} not found")

            # Track if status is changing to CLOSED for event publishing
            old_status = trade.status
            is_closing = (old_status != "CLOSED" and update.status == "CLOSED")

            # Update fields
            update_dict = update.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(trade, field, value)

            trade.updated_at = datetime.utcnow()

            await db.commit()
            await db.refresh(trade)

            logger.info(
                "trade_updated",
                trade_id=str(trade_id),
                old_status=old_status,
                new_status=trade.status
            )

            # Publish event if trade is being closed (separate from DB transaction — do not rollback on failure)
            if is_closing:
                # Look up strategy code if trade has a strategy_id
                strategy_code = None
                if trade.strategy_id:
                    strategy_stmt = select(Strategy).where(Strategy.id == trade.strategy_id)
                    strategy_result = await db.execute(strategy_stmt)
                    strategy_obj = strategy_result.scalar_one_or_none()
                    if strategy_obj:
                        strategy_code = strategy_obj.code

                try:
                    event_bus = get_event_bus()
                    await event_bus.publish(
                        event_type=EventType.TRADE_CLOSED.value,
                        data={
                            "trade_id": str(trade.id),
                            "master_id": str(trade.master_id),
                            "strategy_code": strategy_code,
                            "symbol": trade.symbol,
                            "direction": trade.direction,
                            "entry_price": trade.entry_price,
                            "exit_price": trade.exit_price,
                            "profit": trade.profit,
                            "net_profit": trade.net_profit
                        },
                        source="trade_service",
                        severity="INFO"
                    )
                except Exception as e:
                    logger.warning("event_publish_failed", error=str(e), trade_id=str(trade_id))

            return TradeResponse.model_validate(trade)

        except Exception as e:
            logger.error("update_trade_error", error=str(e), trade_id=str(trade_id))
            raise

    @staticmethod
    async def close_trade(
        db: AsyncSession,
        trade_id: UUID,
        exit_price: float,
        profit: float,
        commission: float = 0.0,
        swap: float = 0.0
    ) -> TradeResponse:
        """
        Close a trade with exit price and profit calculation.

        PURPOSE: Close a trade and record final P&L. Convenience method
        that calls update_trade with CLOSED status and calculates net profit.

        CALLED BY: Trade closure logic, position closing handlers

        Args:
            db: Async database session
            trade_id: UUID of the trade to close
            exit_price: Exit price of the trade
            profit: Profit/loss amount
            commission: Commission paid (optional)
            swap: Swap cost (optional)

        Returns:
            TradeResponse: Closed trade with all final values

        Raises:
            ValueError: If trade not found
        """
        logger.info(
            "close_trade_started",
            trade_id=str(trade_id),
            exit_price=exit_price,
            profit=profit
        )

        try:
            # Calculate net profit
            net_profit = profit - commission - swap

            # Update trade with closure details
            update = TradeUpdate(
                exit_price=exit_price,
                profit=profit,
                commission=commission,
                swap=swap,
                net_profit=net_profit,
                status="CLOSED",
                closed_at=datetime.utcnow()
            )

            return await TradeService.update_trade(db, trade_id, update)

        except Exception as e:
            logger.error("close_trade_error", error=str(e), trade_id=str(trade_id))
            raise

    @staticmethod
    async def get_trade_stats(
        db: AsyncSession,
        master_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> TradeStats:
        """
        Calculate comprehensive trade statistics for a master account.

        PURPOSE: Compute win rate, profit factor, drawdown, and other
        performance metrics for reporting and dashboard display.

        CALLED BY: Dashboard endpoint, performance analysis endpoints

        Args:
            db: Async database session
            master_id: UUID of the master account
            start_date: Optional start date for filtering (default: all time)
            end_date: Optional end date for filtering (default: all time)

        Returns:
            TradeStats: Aggregated statistics object

        Raises:
            Exception: On database errors
        """
        logger.info("get_trade_stats_started", master_id=str(master_id))

        try:
            # Build base query for closed trades only
            stmt = select(Trade).where(
                and_(
                    Trade.master_id == master_id,
                    Trade.status == "CLOSED"
                )
            )

            # Apply date filters
            if start_date:
                stmt = stmt.where(Trade.closed_at >= start_date)
            if end_date:
                stmt = stmt.where(Trade.closed_at <= end_date)

            result = await db.execute(stmt)
            trades = result.scalars().all()

            if not trades:
                logger.info("no_closed_trades_found", master_id=str(master_id))
                return TradeStats(
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    total_profit=0.0,
                    avg_profit=0.0,
                    max_drawdown=0.0,
                    sharpe_ratio=0.0,
                    best_trade=0.0,
                    worst_trade=0.0
                )

            # Calculate statistics
            total_trades = len(trades)
            profits = [t.net_profit or 0.0 for t in trades]
            winning_trades = sum(1 for p in profits if p > 0)
            losing_trades = sum(1 for p in profits if p < 0)
            total_profit = sum(profits)

            # Win rate
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

            # Profit factor (gross profit / gross loss)
            gross_profit = sum(p for p in profits if p > 0)
            gross_loss = abs(sum(p for p in profits if p < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

            # Average profit
            avg_profit = total_profit / total_trades if total_trades > 0 else 0.0

            # Best and worst trades
            best_trade = max(profits) if profits else 0.0
            worst_trade = min(profits) if profits else 0.0

            # Max drawdown (simplified: consecutive losses)
            cumulative = 0.0
            peak = 0.0
            max_drawdown = 0.0
            for profit in profits:
                cumulative += profit
                if cumulative > peak:
                    peak = cumulative
                drawdown = peak - cumulative
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

            # Sharpe ratio (simplified: return / std of returns)
            if len(profits) > 1:
                mean = sum(profits) / len(profits)
                variance = sum((x - mean) ** 2 for x in profits) / len(profits)
                std_dev = variance ** 0.5
                sharpe_ratio = (mean / std_dev) if std_dev > 0 else 0.0
            else:
                sharpe_ratio = 0.0

            logger.info(
                "trade_stats_calculated",
                master_id=str(master_id),
                total_trades=total_trades,
                win_rate=win_rate,
                profit_factor=profit_factor,
                total_profit=total_profit
            )

            return TradeStats(
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                profit_factor=profit_factor,
                total_profit=total_profit,
                avg_profit=avg_profit,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                best_trade=best_trade,
                worst_trade=worst_trade
            )

        except Exception as e:
            logger.error(
                "get_trade_stats_error",
                error=str(e),
                master_id=str(master_id)
            )
            raise
