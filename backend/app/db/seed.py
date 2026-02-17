"""
PURPOSE: Database seeding functionality for JSR Hydra trading system.

Provides idempotent seed functions to initialize database with default data
including master accounts, strategies, allocations, and system health records.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    MasterAccount,
    Strategy,
    CapitalAllocation,
    SystemHealth,
)
from app.config.settings import settings
from structlog import get_logger

logger = get_logger(__name__)


async def seed_database(db: AsyncSession) -> None:
    """
    PURPOSE: Seed database with initial data if not already present.

    Creates:
    - Default MasterAccount from MT5_LOGIN setting
    - Four default strategies (A, B, C, D) with equal allocations
    - Initial allocation records (25% each)
    - System health records for core services

    Idempotent: Safe to run multiple times - checks for existing data.

    Args:
        db: AsyncSession database connection
    """
    try:
        await seed_master_account(db)
        await seed_strategies(db)
        await seed_system_health(db)

        await db.commit()
        logger.info("Database seeding completed successfully")

    except Exception as e:
        await db.rollback()
        logger.error("Database seeding failed", error=str(e))
        raise


async def seed_master_account(db: AsyncSession) -> None:
    """
    PURPOSE: Create default master account if it doesn't exist.

    Uses MT5_LOGIN from settings to create the master account with default values.
    Idempotent: Returns early if master account already exists.

    Args:
        db: AsyncSession database connection

    Raises:
        ValueError: If MT5_LOGIN is not configured
    """
    if settings.MT5_LOGIN == 0:
        logger.warning("MT5_LOGIN not configured, skipping master account creation")
        return

    # Check if master account already exists
    result = await db.execute(
        select(MasterAccount).where(MasterAccount.mt5_login == settings.MT5_LOGIN)
    )
    existing = result.scalars().first()

    if existing:
        logger.info("Master account already exists", mt5_login=settings.MT5_LOGIN)
        return

    master = MasterAccount(
        id=uuid4(),
        mt5_login=settings.MT5_LOGIN,
        broker="JSR Broker",
        balance=0.0,
        equity=0.0,
        peak_equity=0.0,
        daily_start_balance=0.0,
        status="RUNNING",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(master)
    await db.flush()
    logger.info("Created master account", mt5_login=settings.MT5_LOGIN, master_id=str(master.id))


async def seed_strategies(db: AsyncSession) -> None:
    """
    PURPOSE: Create default strategies and allocations if they don't exist.

    Creates four strategies:
    - A: Trend Following (TF)
    - B: Mean Reversion Grid (MRG)
    - C: Session Breakout (SB)
    - D: Volatility Harvester (VH)

    Each gets 25% allocation.
    Idempotent: Returns early if strategies already exist.

    Args:
        db: AsyncSession database connection
    """
    # Check if strategies already exist
    result = await db.execute(select(Strategy))
    existing_strategies = result.scalars().all()

    if len(existing_strategies) > 0:
        logger.info("Strategies already exist", count=len(existing_strategies))
        return

    # Get master account
    master_result = await db.execute(select(MasterAccount).limit(1))
    master = master_result.scalars().first()

    if not master:
        logger.warning("No master account found, cannot create strategies")
        return

    strategies_data = [
        {
            "name": "Trend Following",
            "code": "A",
            "description": "Momentum-based trend following strategy",
            "config": {"lookback": 50, "threshold": 1.5},
        },
        {
            "name": "Mean Reversion Grid",
            "code": "B",
            "description": "Grid-based mean reversion strategy",
            "config": {"grid_levels": 5, "reversion_threshold": 2.0},
        },
        {
            "name": "Session Breakout",
            "code": "C",
            "description": "Session-based breakout strategy",
            "config": {"sessions": ["ASIA", "LONDON", "NEW_YORK"], "breakout_pips": 50},
        },
        {
            "name": "Volatility Harvester",
            "code": "D",
            "description": "Volatility-based option harvesting strategy",
            "config": {"vol_regime": "HIGH", "target_delta": 0.3},
        },
    ]

    strategies = []
    for data in strategies_data:
        strategy = Strategy(
            id=uuid4(),
            name=data["name"],
            code=data["code"],
            description=data["description"],
            status="PAUSED",
            allocation_pct=25.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            total_profit=0.0,
            config=data["config"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        strategies.append(strategy)
        db.add(strategy)

    await db.flush()
    logger.info("Created strategies", count=len(strategies), codes=[s.code for s in strategies])

    # Create allocations for each strategy
    for strategy in strategies:
        allocation = CapitalAllocation(
            id=uuid4(),
            master_id=master.id,
            strategy_id=strategy.id,
            regime_id=None,
            weight=0.25,
            source="SEED",
            allocated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(allocation)

    await db.flush()
    logger.info("Created allocations", count=len(strategies), weight_per_strategy=0.25)


async def seed_system_health(db: AsyncSession) -> None:
    """
    PURPOSE: Create initial system health records for core services.

    Creates health records for:
    - API Server
    - Database
    - Redis Cache
    - MT5 Connection
    - Trade Executor
    - Market Data

    Idempotent: Skips services that already have health records.

    Args:
        db: AsyncSession database connection
    """
    services = [
        ("api_server", "HEALTHY"),
        ("database", "HEALTHY"),
        ("redis_cache", "HEALTHY"),
        ("mt5_connection", "CHECKING"),
        ("trade_executor", "IDLE"),
        ("market_data", "RUNNING"),
    ]

    for service_name, default_status in services:
        # Check if health record already exists
        result = await db.execute(
            select(SystemHealth).where(SystemHealth.service_name == service_name)
        )
        existing = result.scalars().first()

        if existing:
            logger.info("Health record already exists", service=service_name)
            continue

        health = SystemHealth(
            id=uuid4(),
            service_name=service_name,
            status=default_status,
            last_heartbeat=None,
            metrics={},
            version="1.0.0",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(health)

    await db.flush()
    logger.info("Created system health records", count=len(services))
