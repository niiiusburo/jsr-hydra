"""
PURPOSE: Pydantic models for risk management data structures.

Defines RiskCheckResult, RiskMetrics, and related models used throughout
the risk manager module for risk validation and metrics reporting.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class RiskCheckResult(BaseModel):
    """
    PURPOSE: Result of a pre-trade risk check.

    Represents the approval/rejection decision and risk metrics for a trade request.

    Attributes:
        approved: Whether the trade passed all risk checks.
        reason: Human-readable explanation of approval/rejection.
        risk_score: Calculated risk score (0.0 - 100.0).
        position_size: Recommended or calculated position size in lots.
        drawdown_pct: Current drawdown percentage at check time.
        daily_pnl: Current daily P&L at check time.
    """

    approved: bool = Field(
        ...,
        description="Whether the trade passed all risk checks"
    )
    reason: str = Field(
        ...,
        description="Explanation of decision (approval or rejection reason)"
    )
    risk_score: float = Field(
        ge=0.0,
        le=100.0,
        description="Risk score from 0 (safe) to 100 (risky)"
    )
    position_size: float = Field(
        ge=0.0,
        description="Recommended position size in lots"
    )
    drawdown_pct: float = Field(
        ge=0.0,
        description="Current drawdown percentage"
    )
    daily_pnl: float = Field(
        description="Current daily P&L in account currency"
    )


class RiskMetrics(BaseModel):
    """
    PURPOSE: Snapshot of risk metrics at a point in time.

    Provides complete risk state for monitoring and reporting.

    Attributes:
        drawdown_pct: Current drawdown from peak equity.
        daily_pnl: Daily realized P&L.
        margin_level: Current margin level as percentage.
        kill_switch_active: Whether kill switch has been triggered.
        daily_limit_hit: Whether daily loss limit has been exceeded.
        timestamp: UTC timestamp when metrics were captured.
    """

    drawdown_pct: float = Field(
        ge=0.0,
        description="Current drawdown percentage from peak"
    )
    daily_pnl: float = Field(
        description="Daily profit/loss in account currency"
    )
    margin_level: float = Field(
        ge=0.0,
        description="Current margin level as percentage"
    )
    kill_switch_active: bool = Field(
        description="Whether kill switch has been triggered"
    )
    daily_limit_hit: bool = Field(
        description="Whether daily loss limit exceeded"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when metrics captured"
    )
