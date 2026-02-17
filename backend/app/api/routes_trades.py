"""
PURPOSE: Trade-related API routes for JSR Hydra trading system.

Provides endpoints for listing trades with pagination/filtering, retrieving single trades,
creating new trades, and retrieving trade statistics. All routes use proper Pydantic schemas.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.engine import get_db
from app.models.trade import Trade
from app.schemas import TradeCreate, TradeResponse, TradeList, TradeStats
from app.utils.logger import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


# ════════════════════════════════════════════════════════════════
# Trade Retrieval Routes
# ════════════════════════════════════════════════════════════════


@router.get("", response_model=TradeList)
async def list_trades(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(20, ge=1, le=100, description="Trades per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status (open/closed)"),
    strategy_filter: Optional[str] = Query(None, description="Filter by strategy code"),
    symbol_filter: Optional[str] = Query(None, description="Filter by symbol"),
    days_ago: Optional[int] = Query(None, ge=0, description="Trades from last N days"),
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeList:
    """
    PURPOSE: List trades with pagination and optional filtering by status, strategy, symbol, and date range.

    CALLED BY: Frontend trades page, dashboard

    Args:
        page: Page number for pagination (default 1)
        per_page: Number of trades per page (default 20, max 100)
        status_filter: Optional status filter (open/closed)
        strategy_filter: Optional strategy code filter
        symbol_filter: Optional symbol filter
        days_ago: Optional filter for trades from last N days
        current_user: Authenticated username
        db: Database session

    Returns:
        TradeList: Paginated list of trades with metadata

    Raises:
        HTTPException: If database query fails
    """
    try:
        # Build query filters
        filters = []

        if status_filter:
            filters.append(Trade.status == status_filter)

        if strategy_filter:
            from app.models.strategy import Strategy
            strategy_subq = select(Strategy.id).where(Strategy.code == strategy_filter).scalar_subquery()
            filters.append(Trade.strategy_id == strategy_subq)

        if symbol_filter:
            filters.append(Trade.symbol == symbol_filter)

        if days_ago is not None:
            cutoff_date = datetime.utcnow() - timedelta(days=days_ago)
            filters.append(Trade.opened_at >= cutoff_date)

        # Execute count query
        count_stmt = select(Trade)
        if filters:
            count_stmt = count_stmt.where(and_(*filters))

        count_result = await db.execute(count_stmt)
        total = len(count_result.scalars().all())

        # Execute paginated query
        offset = (page - 1) * per_page
        query_stmt = select(Trade)

        if filters:
            query_stmt = query_stmt.where(and_(*filters))

        query_stmt = query_stmt.order_by(Trade.opened_at.desc())
        query_stmt = query_stmt.offset(offset).limit(per_page)

        result = await db.execute(query_stmt)
        trades = result.scalars().all()

        logger.info(
            "trades_listed",
            page=page,
            per_page=per_page,
            total=total,
            count=len(trades),
            filters_applied=bool(filters)
        )

        return TradeList(
            trades=[TradeResponse.model_validate(t) for t in trades],
            total=total,
            page=page,
            per_page=per_page,
        )

    except Exception as e:
        logger.error(
            "trades_list_failed",
            error=str(e),
            page=page,
            per_page=per_page
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trades"
        )


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeResponse:
    """
    PURPOSE: Retrieve a single trade by ID with complete details.

    CALLED BY: Trade detail page, position monitoring

    Args:
        trade_id: UUID of trade to retrieve
        current_user: Authenticated username
        db: Database session

    Returns:
        TradeResponse: Complete trade details

    Raises:
        HTTPException: If trade not found or database error occurs
    """
    try:
        stmt = select(Trade).where(Trade.id == trade_id)
        result = await db.execute(stmt)
        trade = result.scalar_one_or_none()

        if not trade:
            logger.warning("trade_not_found", trade_id=trade_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trade not found"
            )

        logger.info("trade_retrieved", trade_id=trade_id)
        return TradeResponse.model_validate(trade)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_trade_failed",
            trade_id=trade_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trade"
        )


# ════════════════════════════════════════════════════════════════
# Trade Creation
# ════════════════════════════════════════════════════════════════


@router.post("", response_model=TradeResponse)
async def create_trade(
    trade_data: TradeCreate,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeResponse:
    """
    PURPOSE: Create a new trade record in the system.

    CALLED BY: Manual trade entry, external trading systems

    Args:
        trade_data: TradeCreate schema with required trade details
        current_user: Authenticated username
        db: Database session

    Returns:
        TradeResponse: Created trade with all details

    Raises:
        HTTPException: If trade creation fails or validation error
    """
    try:
        # Create trade instance from schema
        new_trade = Trade(
            symbol=trade_data.symbol,
            direction=trade_data.direction,
            lots=trade_data.lots,
            entry_price=trade_data.entry_price,
            stop_loss=trade_data.stop_loss,
            take_profit=trade_data.take_profit,
            strategy_code=trade_data.strategy_code,
            reason=trade_data.reason,
            status="open",
            profit=0.0,
            commission=0.0,
            swap=0.0,
            net_profit=0.0,
            is_simulated=False,
            opened_at=datetime.utcnow(),
        )

        db.add(new_trade)
        await db.commit()
        await db.refresh(new_trade)

        logger.info(
            "trade_created",
            trade_id=str(new_trade.id),
            symbol=new_trade.symbol,
            direction=new_trade.direction
        )

        return TradeResponse.model_validate(new_trade)

    except Exception as e:
        await db.rollback()
        logger.error(
            "trade_creation_failed",
            error=str(e),
            symbol=trade_data.symbol
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create trade"
        )


# ════════════════════════════════════════════════════════════════
# Trade Statistics
# ════════════════════════════════════════════════════════════════


@router.get("/stats/summary", response_model=TradeStats)
async def get_trade_stats(
    days_ago: Optional[int] = Query(None, ge=0, description="Stats for last N days"),
    strategy_filter: Optional[str] = Query(None, description="Filter by strategy code"),
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeStats:
    """
    PURPOSE: Calculate and return trade statistics (win rate, profit factor, sharpe ratio, etc).

    CALLED BY: Dashboard statistics panel, performance monitoring

    Args:
        days_ago: Optional filter for trades from last N days
        strategy_filter: Optional strategy code filter
        current_user: Authenticated username
        db: Database session

    Returns:
        TradeStats: Aggregated trade statistics

    Raises:
        HTTPException: If calculation fails
    """
    try:
        # Build filters
        filters = [Trade.status == "closed"]

        if days_ago is not None:
            cutoff_date = datetime.utcnow() - timedelta(days=days_ago)
            filters.append(Trade.closed_at >= cutoff_date)

        if strategy_filter:
            from app.models.strategy import Strategy
            strategy_subq = select(Strategy.id).where(Strategy.code == strategy_filter).scalar_subquery()
            filters.append(Trade.strategy_id == strategy_subq)

        # Execute query
        stmt = select(Trade).where(and_(*filters))
        result = await db.execute(stmt)
        trades = result.scalars().all()

        if not trades:
            logger.info("no_trades_for_stats", filters=str(filters))
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
                worst_trade=0.0,
            )

        # Calculate statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.net_profit > 0)
        losing_trades = total_trades - winning_trades

        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(t.net_profit for t in trades if t.net_profit > 0)
        gross_loss = abs(sum(t.net_profit for t in trades if t.net_profit < 0))

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        total_profit = sum(t.net_profit for t in trades)
        avg_profit = total_profit / total_trades if total_trades > 0 else 0.0

        best_trade = max((t.net_profit for t in trades), default=0.0)
        worst_trade = min((t.net_profit for t in trades), default=0.0)

        # Simple max drawdown (peak to trough)
        max_drawdown = 0.0
        running_max = 0.0
        cumulative = 0.0
        for trade in sorted(trades, key=lambda t: t.closed_at):
            cumulative += trade.net_profit
            if cumulative > running_max:
                running_max = cumulative
            drawdown = running_max - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Simplified Sharpe ratio (returns / std_dev)
        import statistics
        if len(trades) > 1:
            returns = [t.net_profit for t in trades]
            std_dev = statistics.stdev(returns) if len(returns) > 1 else 1.0
            sharpe_ratio = (sum(returns) / len(returns)) / std_dev if std_dev > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        logger.info(
            "trade_stats_calculated",
            total_trades=total_trades,
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 2),
            total_profit=round(total_profit, 2)
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
            worst_trade=worst_trade,
        )

    except Exception as e:
        logger.error("trade_stats_calculation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate trade statistics"
        )
