"""
PURPOSE: Strategy-related API routes for JSR Hydra trading system.

Provides endpoints for listing active strategies, retrieving strategy details,
and updating strategy status, allocation percentage, and configuration.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator

from app.api.auth import get_current_user
from app.db.engine import get_db
from app.models.strategy import Strategy
from app.schemas import StrategyResponse, StrategyUpdate
from app.core.rate_limit import limiter, READ_LIMIT, WRITE_LIMIT
from app.utils.logger import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/strategies", tags=["strategies"])

MAX_ACTIVE_STRATEGIES = 4
VALID_STRATEGY_STATUSES = {"active", "paused", "stopped"}
MAX_TOTAL_ALLOCATION_PCT = 100.0
ALLOCATION_EPSILON = 1e-6


class StrategyAllocationsUpdate(BaseModel):
    """Atomic payload for multi-strategy allocation updates."""

    allocations: dict[str, float]

    @field_validator("allocations")
    @classmethod
    def validate_allocations(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("allocations payload must not be empty")

        total = 0.0
        normalized: dict[str, float] = {}
        for raw_code, raw_pct in value.items():
            code = str(raw_code).strip().upper()
            pct = float(raw_pct)
            if not code:
                raise ValueError("strategy code must not be empty")
            if pct < 0 or pct > MAX_TOTAL_ALLOCATION_PCT:
                raise ValueError(f"allocation for {code} must be between 0 and 100")
            normalized[code] = pct
            total += pct

        if total > MAX_TOTAL_ALLOCATION_PCT + ALLOCATION_EPSILON:
            raise ValueError(
                f"total allocation must be <= {MAX_TOTAL_ALLOCATION_PCT:.0f}%, got {total:.2f}%"
            )

        return normalized


def _normalize_status(status_value: Optional[str]) -> str:
    """Normalize strategy status for consistent DB checks."""
    return (status_value or "").strip().lower()


# ════════════════════════════════════════════════════════════════
# Strategy Retrieval Routes
# ════════════════════════════════════════════════════════════════


@router.get("", response_model=list[StrategyResponse])
@limiter.limit(READ_LIMIT)
async def list_strategies(
    request: Request,
    _current_user: str = Depends(get_current_user),
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


@router.patch("/allocations", response_model=list[StrategyResponse])
@limiter.limit(WRITE_LIMIT)
async def update_strategy_allocations(
    request: Request,
    update_data: StrategyAllocationsUpdate,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyResponse]:
    """
    PURPOSE: Atomically update allocations for multiple strategies in one transaction.

    Prevents partial updates where totals can exceed 100% if one individual PATCH fails.
    """
    try:
        requested_codes = sorted(set(update_data.allocations.keys()))

        stmt = select(Strategy).where(Strategy.code.in_(requested_codes))
        result = await db.execute(stmt)
        target_strategies = result.scalars().all()
        strategy_map = {str(s.code).upper(): s for s in target_strategies}

        missing = [code for code in requested_codes if code not in strategy_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown strategy code(s): {', '.join(missing)}",
            )

        all_result = await db.execute(select(Strategy))
        all_strategies = all_result.scalars().all()
        proposed_allocations = {
            str(s.code).upper(): float(s.allocation_pct or 0.0)
            for s in all_strategies
        }
        proposed_allocations.update(update_data.allocations)

        proposed_total = sum(proposed_allocations.values())
        if proposed_total > MAX_TOTAL_ALLOCATION_PCT + ALLOCATION_EPSILON:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Total allocation must not exceed 100%.",
                    "proposed_total_pct": round(proposed_total, 2),
                    "max_total_pct": MAX_TOTAL_ALLOCATION_PCT,
                },
            )

        for code, allocation_pct in update_data.allocations.items():
            strategy_map[code].allocation_pct = allocation_pct

        await db.commit()

        refreshed = await db.execute(select(Strategy).order_by(Strategy.code))
        updated_strategies = refreshed.scalars().all()
        logger.info(
            "strategy_allocations_updated",
            updated_codes=requested_codes,
            total_allocation_pct=round(sum(float(s.allocation_pct or 0.0) for s in updated_strategies), 2),
            updated_by=current_user,
        )
        return [StrategyResponse.model_validate(s) for s in updated_strategies]

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("strategy_allocations_update_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update strategy allocations",
        )


@router.get("/{strategy_code}", response_model=StrategyResponse)
@limiter.limit(READ_LIMIT)
async def get_strategy(
    request: Request,
    strategy_code: str,
    _current_user: str = Depends(get_current_user),
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
@limiter.limit(WRITE_LIMIT)
async def update_strategy(
    request: Request,
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
            requested_status = _normalize_status(update_data.status)
            current_status = _normalize_status(strategy.status)

            if requested_status not in VALID_STRATEGY_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid status '{update_data.status}'. "
                        f"Allowed: {', '.join(sorted(VALID_STRATEGY_STATUSES))}"
                    ),
                )

            # Hard guard: no more than 4 strategies can be active at once.
            if requested_status == "active" and current_status != "active":
                active_count_stmt = (
                    select(func.count())
                    .select_from(Strategy)
                    .where(func.lower(Strategy.status) == "active")
                )
                active_count_result = await db.execute(active_count_stmt)
                active_count = active_count_result.scalar() or 0

                if active_count >= MAX_ACTIVE_STRATEGIES:
                    active_codes_stmt = (
                        select(Strategy.code)
                        .where(func.lower(Strategy.status) == "active")
                        .order_by(Strategy.code)
                    )
                    active_codes_result = await db.execute(active_codes_stmt)
                    active_codes = list(active_codes_result.scalars().all())
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": (
                                f"Maximum of {MAX_ACTIVE_STRATEGIES} active strategies reached. "
                                "Pause one before activating another."
                            ),
                            "max_active": MAX_ACTIVE_STRATEGIES,
                            "active_strategies": active_codes,
                        },
                    )

            strategy.status = requested_status
            updated_fields.append(f"status={requested_status}")

        if update_data.allocation_pct is not None:
            total_others_stmt = (
                select(func.coalesce(func.sum(Strategy.allocation_pct), 0.0))
                .where(Strategy.code != strategy.code)
            )
            total_others_result = await db.execute(total_others_stmt)
            total_others = float(total_others_result.scalar() or 0.0)
            proposed_total = total_others + float(update_data.allocation_pct)

            if proposed_total > MAX_TOTAL_ALLOCATION_PCT + ALLOCATION_EPSILON:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Total allocation must not exceed 100%.",
                        "proposed_total_pct": round(proposed_total, 2),
                        "max_total_pct": MAX_TOTAL_ALLOCATION_PCT,
                    },
                )

            strategy.allocation_pct = update_data.allocation_pct
            updated_fields.append(f"allocation_pct={update_data.allocation_pct}")

        if update_data.config is not None:
            # Merge configs if present
            strategy.config = {
                **(strategy.config or {}),
                **update_data.config,
            }
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
