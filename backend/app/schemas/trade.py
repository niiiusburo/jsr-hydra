"""
Trade-related Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of trade creation, updates,
responses, and statistical aggregations.
"""

from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class TradeCreate(BaseModel):
    """
    Schema for creating a new trade.

    Attributes:
        symbol: Trading pair symbol (e.g., 'EURUSD')
        direction: Trade direction, must be 'BUY' or 'SELL'
        lots: Number of lots to trade
        entry_price: Entry price of the trade
        stop_loss: Optional stop loss price
        take_profit: Optional take profit price
        strategy_code: Optional strategy identifier
        reason: Optional trade reason/comment
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    direction: str
    lots: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy_code: Optional[str] = None
    reason: Optional[str] = None

    @field_validator('direction')
    @classmethod
    def validate_direction(cls, v: str) -> str:
        """Validate that direction is either BUY or SELL."""
        if v.upper() not in ('BUY', 'SELL'):
            raise ValueError('direction must be either BUY or SELL')
        return v.upper()

    @field_validator('lots')
    @classmethod
    def validate_lots(cls, v: float) -> float:
        """Validate that lots is a positive number."""
        if v <= 0:
            raise ValueError('lots must be greater than 0')
        return v

    @field_validator('entry_price')
    @classmethod
    def validate_entry_price(cls, v: float) -> float:
        """Validate that entry price is positive."""
        if v <= 0:
            raise ValueError('entry_price must be greater than 0')
        return v


class TradeUpdate(BaseModel):
    """
    Schema for updating an existing trade.

    Attributes:
        exit_price: Optional exit price
        profit: Optional profit amount
        commission: Optional commission paid
        swap: Optional swap cost
        net_profit: Optional net profit after fees
        status: Optional trade status
        closed_at: Optional trade close timestamp
    """

    model_config = ConfigDict(from_attributes=True)

    exit_price: Optional[float] = None
    profit: Optional[float] = None
    commission: Optional[float] = None
    swap: Optional[float] = None
    net_profit: Optional[float] = None
    status: Optional[str] = None
    closed_at: Optional[datetime] = None


class TradeResponse(BaseModel):
    """
    Complete trade response schema.

    Attributes:
        id: Unique trade identifier (UUID)
        master_id: Master account identifier
        strategy_id: Associated strategy identifier
        idempotency_key: Idempotency key for request deduplication
        mt5_ticket: MetaTrader 5 ticket number
        symbol: Trading pair symbol
        direction: Trade direction (BUY/SELL)
        lots: Number of lots
        entry_price: Entry price
        exit_price: Exit price (None if open)
        stop_loss: Stop loss price
        take_profit: Take profit price
        profit: Total profit
        commission: Commission paid
        swap: Swap cost
        net_profit: Net profit after fees
        regime_at_entry: Market regime at entry
        confidence: Confidence score
        reason: Trade reason/comment
        status: Trade status (open/closed)
        is_simulated: Whether this is a simulated trade
        opened_at: Trade open timestamp
        closed_at: Trade close timestamp (None if open)
        created_at: Record creation timestamp
        updated_at: Record last update timestamp
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    master_id: UUID
    strategy_id: Optional[UUID] = None
    idempotency_key: Optional[str] = None
    mt5_ticket: Optional[int] = None
    symbol: str
    direction: str
    lots: float
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    profit: float
    commission: float
    swap: float
    net_profit: float
    regime_at_entry: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    status: str
    is_simulated: bool
    opened_at: datetime
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TradeList(BaseModel):
    """
    Paginated list of trades.

    Attributes:
        trades: List of trade responses
        total: Total number of trades
        page: Current page number
        per_page: Trades per page
    """

    model_config = ConfigDict(from_attributes=True)

    trades: list[TradeResponse]
    total: int
    page: int
    per_page: int


class TradeStats(BaseModel):
    """
    Trade statistics aggregation.

    Attributes:
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate: Win rate percentage (0-1)
        profit_factor: Gross profit / gross loss ratio
        total_profit: Total profit from all trades
        avg_profit: Average profit per trade
        max_drawdown: Maximum drawdown percentage
        sharpe_ratio: Sharpe ratio
        best_trade: Best single trade profit
        worst_trade: Worst single trade loss
    """

    model_config = ConfigDict(from_attributes=True)

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    total_profit: float
    avg_profit: float
    max_drawdown: float
    sharpe_ratio: float
    best_trade: float
    worst_trade: float
