"""
PURPOSE: Strategy-related API routes for JSR Hydra trading system.

Provides endpoints for listing active strategies, retrieving strategy details,
and updating strategy status, allocation percentage, and configuration.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.engine import get_db
from app.models.strategy import Strategy
from app.schemas import StrategyResponse, StrategyUpdate
from app.utils.logger import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/strategies", tags=["strategies"])


# ════════════════════════════════════════════════════════════════
# Strategy Retrieval Routes
# ════════════════════════════════════════════════════════════════


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyResponse]:
    """
    PURPOSE: Retrieve all strategies with current metrics and status.

    CALLED BY: Strategy page, dashboard strategy selector

    Args:
        current_user: Authenticated username
        db: Database session

    Returns:
        list[StrategyResponse]: List of all strategies

    Raises:
        HTTPException: If database query fails
    """
    try:
        stmt = select(Strategy).order_by(Strategy.code)
        result = await db.execute(stmt)
        strategies = result.scalars().all()

        logger.info(
            "strategies_listed",
            count=len(strategies)
        )

        return [StrategyResponse.model_validate(s) for s in strategies]

    except Exception as e:
        logger.error("strategies_list_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve strategies"
        )


@router.get("/{strategy_code}", response_model=StrategyResponse)
async def get_strategy(
    strategy_code: str,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    """
    PURPOSE: Retrieve a single strategy by code with all configuration and metrics.

    CALLED BY: Strategy detail page, allocation control panel

    Args:
        strategy_code: Unique strategy code identifier
        current_user: Authenticated username
        db: Database session

    Returns:
        StrategyResponse: Complete strategy details

    Raises:
        HTTPException: If strategy not found or database error occurs
    """
    try:
        stmt = select(Strategy).where(Strategy.code == strategy_code)
        result = await db.execute(stmt)
        strategy = result.scalar_one_or_none()

        if not strategy:
            logger.warning(
                "strategy_not_found",
                strategy_code=strategy_code
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy '{strategy_code}' not found"
            )

        logger.info("strategy_retrieved", strategy_code=strategy_code)
        return StrategyResponse.model_validate(strategy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_strategy_failed",
            strategy_code=strategy_code,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve strategy"
        )


# ════════════════════════════════════════════════════════════════
# Strategy Update Routes
# ════════════════════════════════════════════════════════════════


@router.patch("/{strategy_code}", response_model=StrategyResponse)
async def update_strategy(
    strategy_code: str,
    update_data: StrategyUpdate,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    """
    PURPOSE: Update strategy configuration including status, allocation percentage, and config parameters.

    CALLED BY: Strategy control panel, configuration editor

    Args:
        strategy_code: Unique strategy code identifier
        update_data: StrategyUpdate schema with fields to update
        current_user: Authenticated username
        db: Database session

    Returns:
        StrategyResponse: Updated strategy details

    Raises:
        HTTPException: If strategy not found or update fails
    """
    try:
        # Fetch strategy
        stmt = select(Strategy).where(Strategy.code == strategy_code)
        result = await db.execute(stmt)
        strategy = result.scalar_one_or_none()

        if not strategy:
            logger.warning(
                "strategy_not_found_for_update",
                strategy_code=strategy_code
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy '{strategy_code}' not found"
            )

        # Apply updates
        updated_fields = []

        if update_data.status is not None:
            strategy.status = update_data.status
            updated_fields.append(f"status={update_data.status}")

        if update_data.allocation_pct is not None:
            strategy.allocation_pct = update_data.allocation_pct
            updated_fields.append(f"allocation_pct={update_data.allocation_pct}")

        if update_data.config is not None:
            # Merge configs if present
            if strategy.config is None:
                strategy.config = {}
            strategy.config.update(update_data.config)
            updated_fields.append("config_updated")

        # Commit changes
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)

        logger.info(
            "strategy_updated",
            strategy_code=strategy_code,
            updates=", ".join(updated_fields),
            updated_by=current_user
        )

        return StrategyResponse.model_validate(strategy)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "strategy_update_failed",
            strategy_code=strategy_code,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update strategy"
        )
