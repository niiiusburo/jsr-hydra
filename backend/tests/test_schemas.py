"""
PURPOSE: Integration tests for Pydantic schemas.

Tests validation of trading domain models:
- Trade creation with direction and lot validation
- Trade responses with ORM compatibility
- Portfolio allocation weight validation
"""

import pytest
from datetime import datetime
from uuid import uuid4
from pydantic import ValidationError

from app.schemas.trade import TradeCreate, TradeUpdate, TradeResponse, TradeStats, TradeList


class TestTradeCreateSchema:
    """Test TradeCreate Pydantic schema."""

    def test_trade_create_valid(self):
        """Test creating a valid trade."""
        trade = TradeCreate(
            symbol="EURUSD",
            direction="BUY",
            lots=1.0,
            entry_price=1.2000,
            stop_loss=1.1900,
            take_profit=1.2100
        )
        assert trade.symbol == "EURUSD"
        assert trade.direction == "BUY"
        assert trade.lots == 1.0
        assert trade.entry_price == 1.2000

    def test_trade_create_invalid_direction_lowercase(self):
        """Test that direction is normalized to uppercase."""
        trade = TradeCreate(
            symbol="EURUSD",
            direction="buy",
            lots=1.0,
            entry_price=1.2000
        )
        assert trade.direction == "BUY"

    def test_trade_create_invalid_direction_value(self):
        """Test invalid direction value."""
        with pytest.raises(ValidationError) as exc_info:
            TradeCreate(
                symbol="EURUSD",
                direction="LONG",  # Invalid direction
                lots=1.0,
                entry_price=1.2000
            )
        assert "direction must be either BUY or SELL" in str(exc_info.value)

    def test_trade_create_negative_lots(self):
        """Test with negative lots."""
        with pytest.raises(ValidationError) as exc_info:
            TradeCreate(
                symbol="EURUSD",
                direction="BUY",
                lots=-1.0,
                entry_price=1.2000
            )
        assert "lots must be greater than 0" in str(exc_info.value)

    def test_trade_create_zero_lots(self):
        """Test with zero lots."""
        with pytest.raises(ValidationError) as exc_info:
            TradeCreate(
                symbol="EURUSD",
                direction="BUY",
                lots=0.0,
                entry_price=1.2000
            )
        assert "lots must be greater than 0" in str(exc_info.value)

    def test_trade_create_negative_entry_price(self):
        """Test with negative entry price."""
        with pytest.raises(ValidationError) as exc_info:
            TradeCreate(
                symbol="EURUSD",
                direction="BUY",
                lots=1.0,
                entry_price=-1.2000
            )
        assert "entry_price must be greater than 0" in str(exc_info.value)

    def test_trade_create_zero_entry_price(self):
        """Test with zero entry price."""
        with pytest.raises(ValidationError) as exc_info:
            TradeCreate(
                symbol="EURUSD",
                direction="BUY",
                lots=1.0,
                entry_price=0.0
            )
        assert "entry_price must be greater than 0" in str(exc_info.value)

    def test_trade_create_sell_direction(self):
        """Test creating a SELL trade."""
        trade = TradeCreate(
            symbol="BTCUSD",
            direction="SELL",
            lots=0.5,
            entry_price=45000.0
        )
        assert trade.direction == "SELL"

    def test_trade_create_optional_fields(self):
        """Test optional fields are truly optional."""
        trade = TradeCreate(
            symbol="XAUUSD",
            direction="BUY",
            lots=10.0,
            entry_price=2000.0
        )
        assert trade.stop_loss is None
        assert trade.take_profit is None
        assert trade.strategy_code is None
        assert trade.reason is None

    def test_trade_create_with_optional_fields(self):
        """Test providing all optional fields."""
        trade = TradeCreate(
            symbol="EURUSD",
            direction="BUY",
            lots=2.0,
            entry_price=1.1500,
            stop_loss=1.1400,
            take_profit=1.1600,
            strategy_code="A",
            reason="Breakout above resistance"
        )
        assert trade.stop_loss == 1.1400
        assert trade.take_profit == 1.1600
        assert trade.strategy_code == "A"
        assert trade.reason == "Breakout above resistance"


class TestTradeUpdateSchema:
    """Test TradeUpdate Pydantic schema."""

    def test_trade_update_valid(self):
        """Test creating a valid trade update."""
        update = TradeUpdate(
            exit_price=1.2100,
            profit=100.0,
            commission=-10.0,
            swap=-2.5,
            status="CLOSED"
        )
        assert update.exit_price == 1.2100
        assert update.profit == 100.0

    def test_trade_update_all_optional(self):
        """Test that all fields are optional."""
        update = TradeUpdate()
        assert update.exit_price is None
        assert update.profit is None
        assert update.commission is None
        assert update.swap is None
        assert update.status is None

    def test_trade_update_partial_update(self):
        """Test partial update with only some fields."""
        update = TradeUpdate(
            exit_price=1.2100,
            status="CLOSED"
        )
        assert update.exit_price == 1.2100
        assert update.status == "CLOSED"
        assert update.profit is None


class TestTradeResponseSchema:
    """Test TradeResponse Pydantic schema."""

    def test_trade_response_from_dict(self):
        """Test creating trade response from dict."""
        now = datetime.utcnow()
        trade_data = {
            "id": uuid4(),
            "master_id": uuid4(),
            "strategy_id": uuid4(),
            "idempotency_key": "test-key-123",
            "mt5_ticket": 12345,
            "symbol": "EURUSD",
            "direction": "BUY",
            "lots": 1.0,
            "entry_price": 1.2000,
            "exit_price": 1.2100,
            "stop_loss": 1.1900,
            "take_profit": 1.2100,
            "profit": 100.0,
            "commission": -10.0,
            "swap": -2.5,
            "net_profit": 87.5,
            "regime_at_entry": "TRENDING_UP",
            "confidence": 0.85,
            "reason": "Strong signal",
            "status": "CLOSED",
            "is_simulated": False,
            "opened_at": now,
            "closed_at": now,
            "created_at": now,
            "updated_at": now
        }
        trade = TradeResponse(**trade_data)
        assert trade.symbol == "EURUSD"
        assert trade.direction == "BUY"
        assert trade.profit == 100.0

    def test_trade_response_minimal_fields(self):
        """Test trade response with minimal required fields."""
        now = datetime.utcnow()
        trade = TradeResponse(
            id=uuid4(),
            master_id=uuid4(),
            symbol="BTCUSD",
            direction="SELL",
            lots=0.5,
            entry_price=45000.0,
            profit=500.0,
            commission=-25.0,
            swap=0.0,
            net_profit=475.0,
            status="CLOSED",
            is_simulated=True,
            opened_at=now,
            created_at=now,
            updated_at=now
        )
        assert trade.symbol == "BTCUSD"
        assert trade.is_simulated is True
        assert trade.strategy_id is None

    def test_trade_response_orm_compatibility(self):
        """Test ORM mode configuration."""
        # Verify that from_attributes is enabled
        assert TradeResponse.model_config.get("from_attributes") is True


class TestTradeStatsSchema:
    """Test TradeStats Pydantic schema."""

    def test_trade_stats_valid(self):
        """Test creating valid trade statistics."""
        stats = TradeStats(
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=0.6,
            profit_factor=2.5,
            total_profit=5000.0,
            avg_profit=50.0,
            max_drawdown=8.5,
            sharpe_ratio=1.2,
            best_trade=500.0,
            worst_trade=-300.0
        )
        assert stats.total_trades == 100
        assert stats.win_rate == 0.6
        assert float(stats.profit_factor) == pytest.approx(2.5, abs=0.01)

    def test_trade_stats_all_zeros(self):
        """Test with all zero values (no trades)."""
        stats = TradeStats(
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
        assert stats.total_trades == 0

    def test_trade_stats_negative_drawdown(self):
        """Test with negative drawdown value."""
        stats = TradeStats(
            total_trades=10,
            winning_trades=10,
            losing_trades=0,
            win_rate=1.0,
            profit_factor=5.0,
            total_profit=1000.0,
            avg_profit=100.0,
            max_drawdown=-1.0,  # Can be negative (recovery)
            sharpe_ratio=2.0,
            best_trade=1000.0,
            worst_trade=0.0
        )
        assert stats.max_drawdown == -1.0


class TestTradeListSchema:
    """Test TradeList Pydantic schema."""

    def test_trade_list_valid(self):
        """Test creating a valid trade list."""
        now = datetime.utcnow()
        trades = [
            TradeResponse(
                id=uuid4(),
                master_id=uuid4(),
                symbol="EURUSD",
                direction="BUY",
                lots=1.0,
                entry_price=1.2000,
                profit=100.0,
                commission=-10.0,
                swap=0.0,
                net_profit=90.0,
                status="CLOSED",
                is_simulated=False,
                opened_at=now,
                created_at=now,
                updated_at=now
            )
        ]
        trade_list = TradeList(
            trades=trades,
            total=1,
            page=1,
            per_page=10
        )
        assert len(trade_list.trades) == 1
        assert trade_list.total == 1

    def test_trade_list_empty(self):
        """Test empty trade list."""
        trade_list = TradeList(
            trades=[],
            total=0,
            page=1,
            per_page=10
        )
        assert len(trade_list.trades) == 0
        assert trade_list.total == 0

    def test_trade_list_pagination(self):
        """Test trade list with pagination info."""
        trade_list = TradeList(
            trades=[],
            total=100,
            page=2,
            per_page=20
        )
        assert trade_list.page == 2
        assert trade_list.per_page == 20
        assert trade_list.total == 100
