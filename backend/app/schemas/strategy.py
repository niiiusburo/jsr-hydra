"""
Strategy-related Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of strategy configurations,
responses, and performance metrics.
"""

from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class StrategyResponse(BaseModel):
    """
    Complete strategy response schema.

    Attributes:
        id: Unique strategy identifier (UUID)
        name: Strategy name
        code: Strategy code/identifier
        description: Optional strategy description
        status: Strategy status (active/inactive/paused)
        allocation_pct: Allocation percentage (0-100)
        win_rate: Win rate percentage (0-1)
        profit_factor: Profit factor ratio
        total_trades: Total number of trades
        total_profit: Total profit from trades
        config: Strategy configuration dictionary
        created_at: Record creation timestamp
        updated_at: Record last update timestamp
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    description: Optional[str] = None
    status: str
    allocation_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int
    total_profit: float
    config: dict
    created_at: datetime
    updated_at: datetime

    @field_validator('allocation_pct')
    @classmethod
    def validate_allocation(cls, v: float) -> float:
        """Validate allocation is between 0 and 100."""
        if not 0 <= v <= 100:
            raise ValueError('allocation_pct must be between 0 and 100')
        return v

    @field_validator('win_rate')
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Validate win rate is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError('win_rate must be between 0 and 1')
        return v


class StrategyUpdate(BaseModel):
    """
    Schema for updating a strategy.

    Attributes:
        status: Optional new status
        config: Optional configuration updates
        allocation_pct: Optional new allocation percentage
    """

    model_config = ConfigDict(from_attributes=True)

    status: Optional[str] = None
    config: Optional[dict] = None
    allocation_pct: Optional[float] = None

    @field_validator('allocation_pct')
    @classmethod
    def validate_allocation(cls, v: Optional[float]) -> Optional[float]:
        """Validate allocation is between 0 and 100."""
        if v is not None and not 0 <= v <= 100:
            raise ValueError('allocation_pct must be between 0 and 100')
        return v


class StrategyMetrics(BaseModel):
    """
    Strategy performance metrics for dashboard display.

    Attributes:
        code: Strategy code
        name: Strategy name
        win_rate_7d: 7-day win rate (0-1)
        win_rate_30d: 30-day win rate (0-1)
        profit_factor_7d: 7-day profit factor
        profit_factor_30d: 30-day profit factor
        trades_today: Number of trades today
        pnl_today: Profit/loss today
    """

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    win_rate_7d: float
    win_rate_30d: float
    profit_factor_7d: float
    profit_factor_30d: float
    trades_today: int
    pnl_today: float

    @field_validator('win_rate_7d', 'win_rate_30d')
    @classmethod
    def validate_win_rates(cls, v: float) -> float:
        """Validate win rate is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError('win_rate must be between 0 and 1')
        return v
