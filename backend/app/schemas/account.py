"""
Account-related Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of trading accounts,
follower accounts, and account metrics.
"""

from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AccountResponse(BaseModel):
    """
    Master trading account response schema.

    Attributes:
        id: Unique account identifier (UUID)
        mt5_login: MetaTrader 5 login number
        broker: Optional broker name
        balance: Account balance
        equity: Current equity
        peak_equity: Peak equity reached
        status: Account status (active/paused/disabled)
        drawdown_pct: Current drawdown percentage
        daily_pnl: Daily profit/loss
        open_positions_count: Number of open positions
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mt5_login: int
    broker: Optional[str] = None
    balance: float
    equity: float
    peak_equity: float
    status: str
    drawdown_pct: float = 0.0
    daily_pnl: float = 0.0
    open_positions_count: int = 0

    @field_validator('mt5_login')
    @classmethod
    def validate_mt5_login(cls, v: int) -> int:
        """Validate MT5 login is positive."""
        if v <= 0:
            raise ValueError('mt5_login must be greater than 0')
        return v

    @field_validator('balance', 'equity', 'peak_equity')
    @classmethod
    def validate_monetary(cls, v: float) -> float:
        """Validate monetary amounts are non-negative."""
        if v < 0:
            raise ValueError('monetary amounts must be non-negative')
        return v

    @field_validator('drawdown_pct')
    @classmethod
    def validate_drawdown(cls, v: float) -> float:
        """Validate drawdown is between 0 and 100."""
        if not 0 <= v <= 100:
            raise ValueError('drawdown_pct must be between 0 and 100')
        return v


class FollowerResponse(BaseModel):
    """
    Follower (copy trading) account response schema.

    Attributes:
        id: Unique follower account identifier (UUID)
        mt5_login: MetaTrader 5 login number
        broker: Optional broker name
        lot_multiplier: Lot size multiplier for copied trades
        status: Account status (active/paused/disabled)
        master_id: Master account identifier being followed
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mt5_login: int
    broker: Optional[str] = None
    lot_multiplier: float
    status: str
    master_id: UUID

    @field_validator('mt5_login')
    @classmethod
    def validate_mt5_login(cls, v: int) -> int:
        """Validate MT5 login is positive."""
        if v <= 0:
            raise ValueError('mt5_login must be greater than 0')
        return v

    @field_validator('lot_multiplier')
    @classmethod
    def validate_lot_multiplier(cls, v: float) -> float:
        """Validate lot multiplier is positive."""
        if v <= 0:
            raise ValueError('lot_multiplier must be greater than 0')
        return v
