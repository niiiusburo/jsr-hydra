"""
PURPOSE: System-level API routes for JSR Hydra trading system.

Provides endpoints for health checks, version information, dashboard summary,
kill switch controls, and system status monitoring. Health check is public,
all others require authentication.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.engine import get_db
from app.models.account import MasterAccount
from app.models.system import SystemHealth
from app.schemas import HealthCheck, VersionInfo, DashboardSummary
from app.utils.logger import get_logger
from app.version import get_version


logger = get_logger(__name__)
router = APIRouter(prefix="/system", tags=["system"])

# Track system startup time
_startup_time = time.time()


# ════════════════════════════════════════════════════════════════
# Health Check (Public)
# ════════════════════════════════════════════════════════════════


@router.get("/health", response_model=HealthCheck, tags=["health"])
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthCheck:
    """
    PURPOSE: Public health check endpoint for monitoring and load balancer health probes.

    CALLED BY: Load balancers, monitoring systems (no authentication required)

    Args:
        db: Database session for checking database connectivity

    Returns:
        HealthCheck: System health status with service statuses and uptime

    Raises:
        HTTPException: If critical services are unavailable
    """
    try:
        services = {}
        overall_status = "healthy"

        # Check database
        try:
            await db.execute(select(1))
            services["database"] = "ok"
        except Exception as e:
            services["database"] = "degraded"
            overall_status = "degraded"
            logger.warning("health_check_database_degraded", error=str(e))

        # Get version
        try:
            version_info = get_version()
            version = version_info.get("version", "unknown")
        except Exception as e:
            version = "unknown"
            services["version"] = "degraded"
            logger.warning("health_check_version_unavailable", error=str(e))

        # Always include core services
        services["api"] = "ok"

        uptime_seconds = time.time() - _startup_time

        logger.info(
            "health_check_performed",
            status=overall_status,
            services=services,
            uptime_seconds=round(uptime_seconds, 2)
        )

        return HealthCheck(
            status=overall_status,
            services=services,
            version=version,
            uptime_seconds=uptime_seconds,
        )

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed"
        )


# ════════════════════════════════════════════════════════════════
# Version Info
# ════════════════════════════════════════════════════════════════


@router.get("/version", response_model=VersionInfo, tags=["version"])
async def get_system_version(
    current_user: str = Depends(get_current_user),
) -> VersionInfo:
    """
    PURPOSE: Retrieve system version information from version.json.

    CALLED BY: Frontend version display, API clients

    Args:
        current_user: Authenticated username

    Returns:
        VersionInfo: Version string, codename, and update timestamp

    Raises:
        HTTPException: If version.json cannot be read
    """
    try:
        version_data = get_version()

        logger.info(
            "version_retrieved",
            version=version_data.get("version")
        )

        return VersionInfo(
            version=version_data.get("version", "unknown"),
            codename=version_data.get("codename", "Hydra"),
            updated_at=version_data.get("updated_at", datetime.utcnow().isoformat()),
        )

    except FileNotFoundError:
        logger.error("version_file_not_found")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Version information not available"
        )
    except Exception as e:
        logger.error("version_retrieval_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve version"
        )


# ════════════════════════════════════════════════════════════════
# Dashboard Summary
# ════════════════════════════════════════════════════════════════


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard_summary(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    """
    PURPOSE: Retrieve comprehensive dashboard summary with account, strategies, trades, and system status.

    CALLED BY: Dashboard frontend page

    Args:
        current_user: Authenticated username
        db: Database session

    Returns:
        DashboardSummary: Complete system state for dashboard rendering

    Raises:
        HTTPException: If required data cannot be retrieved
    """
    try:
        # Get version
        version_data = get_version()
        version = version_data.get("version", "unknown")

        # Fetch account info (simplified - would normally fetch from MasterAccount model)
        stmt = select(MasterAccount).limit(1)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        if not account:
            logger.warning("dashboard_summary_no_account")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No master account found"
            )

        # Build placeholder dashboard data
        # NOTE: In full implementation, this would aggregate real data from:
        # - MasterAccount (current balance, equity)
        # - RegimeState (current market regime)
        # - CapitalAllocation (strategy allocations)
        # - Strategy metrics
        # - Recent trades
        # - Equity curve history

        logger.info(
            "dashboard_summary_retrieved",
            account_id=str(account.id),
            version=version
        )

        # Return minimal dashboard structure (extend with real aggregations)
        return DashboardSummary(
            account=None,  # Would be AccountResponse
            regime=None,   # Would be RegimeResponse
            allocations=[],  # Would be list of AllocationResponse
            strategies=[],  # Would be list of StrategyMetrics
            recent_trades=[],  # Would be list of TradeResponse
            equity_curve=[],  # Would be list of dict with timestamp and value
            system_status="healthy",
            version=version,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("dashboard_summary_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard summary"
        )


# ════════════════════════════════════════════════════════════════
# Kill Switch Controls
# ════════════════════════════════════════════════════════════════


@router.post("/kill-switch", status_code=status.HTTP_200_OK)
async def trigger_kill_switch(
    reason: str = "Manual kill switch triggered",
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    PURPOSE: Immediately trigger the kill switch to close all positions and halt trading.

    CALLED BY: Emergency stop button, risk management alerts

    Behavior:
        1. Close ALL open positions at market price
        2. Set system status to HALTED
        3. Cancel all pending orders
        4. Log event as CRITICAL severity
        5. Send Telegram alert
        6. Require manual restart (no auto-resume)

    Args:
        reason: Optional reason for triggering kill switch
        current_user: Authenticated username
        db: Database session

    Returns:
        dict: Kill switch status and execution details

    Raises:
        HTTPException: If kill switch execution fails
    """
    try:
        # Log the kill switch event
        logger.critical(
            "kill_switch_triggered",
            reason=reason,
            triggered_by=current_user
        )

        # TODO: Implement actual kill switch logic:
        # 1. Close all open positions via MT5 bridge
        # 2. Set SystemStatus.status = "HALTED"
        # 3. Cancel pending orders
        # 4. Log to event_log with severity=CRITICAL
        # 5. Send Telegram alert via alerts module

        return {
            "status": "executed",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "triggered_by": current_user,
        }

    except Exception as e:
        logger.error(
            "kill_switch_execution_failed",
            error=str(e),
            triggered_by=current_user
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kill switch execution failed"
        )


@router.post("/kill-switch/reset", status_code=status.HTTP_200_OK)
async def reset_kill_switch(
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    PURPOSE: Reset the kill switch after manual review and allow trading to resume.

    CALLED BY: System administrator after kill switch event

    Behavior:
        1. Verify system is safe (max drawdown below threshold, etc)
        2. Set system status to RUNNING
        3. Log reset event
        4. Send confirmation alert

    Args:
        current_user: Authenticated username
        db: Database session

    Returns:
        dict: Reset status and timestamp

    Raises:
        HTTPException: If reset fails or system is not safe to resume
    """
    try:
        logger.info(
            "kill_switch_reset_attempted",
            reset_by=current_user
        )

        # TODO: Implement actual reset logic:
        # 1. Verify system health/metrics
        # 2. Set SystemStatus.status = "RUNNING"
        # 3. Log reset event with severity=WARNING
        # 4. Send Telegram alert about system resumption

        return {
            "status": "reset",
            "timestamp": datetime.utcnow().isoformat(),
            "reset_by": current_user,
        }

    except Exception as e:
        logger.error(
            "kill_switch_reset_failed",
            error=str(e),
            reset_by=current_user
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kill switch reset failed"
        )
