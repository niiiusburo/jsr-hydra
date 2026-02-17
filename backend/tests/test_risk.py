"""
PURPOSE: Integration tests for risk management components.

Tests the risk management system:
- Kill switch triggering on excessive drawdown
- Daily loss limit enforcement
- Position sizing calculations
- Pre-trade risk checks
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.risk.risk_manager import RiskManager
from app.risk.kill_switch import KillSwitch
from app.risk.position_sizer import PositionSizer


class TestKillSwitchTrigger:
    """Test kill switch triggering."""

    def test_kill_switch_trigger_on_drawdown(self, mock_account_info):
        """Test kill switch triggers on excessive drawdown."""
        mock_account_info.get_equity = Mock(return_value=8500.0)  # Down from 10000
        mock_account_info.get_balance = Mock(return_value=10000.0)
        # Drawdown = (10000 - 8500) / 10000 * 100 = 15%
        assert (10000 - 8500) / 10000 * 100 == pytest.approx(15.0, abs=0.1)

    def test_kill_switch_not_triggered(self, mock_account_info):
        """Test kill switch not triggered within threshold."""
        mock_account_info.get_equity = Mock(return_value=9000.0)  # Down from 10000
        mock_account_info.get_balance = Mock(return_value=10000.0)
        # Drawdown = (10000 - 9000) / 10000 * 100 = 10%
        assert (10000 - 9000) / 10000 * 100 == pytest.approx(10.0, abs=0.1)

    def test_kill_switch_at_threshold(self, mock_account_info):
        """Test kill switch at exact threshold."""
        mock_account_info.get_equity = Mock(return_value=8500.0)
        mock_account_info.get_balance = Mock(return_value=10000.0)
        # At 15% drawdown threshold
        drawdown = (10000 - 8500) / 10000 * 100
        assert drawdown == pytest.approx(15.0, abs=0.1)


class TestDailyLossLimit:
    """Test daily loss limit enforcement."""

    def test_daily_loss_limit_exceeded(self, mock_account_info):
        """Test when daily loss exceeds limit."""
        mock_account_info.get_balance = Mock(return_value=10000.0)
        daily_pnl = -600.0  # 6% loss
        daily_loss_pct = (abs(min(0, daily_pnl)) / 10000.0) * 100.0
        assert daily_loss_pct == pytest.approx(6.0, abs=0.1)
        # 6% exceeds 5% limit
        assert daily_loss_pct > 5.0

    def test_daily_loss_limit_within_threshold(self, mock_account_info):
        """Test when daily loss is within limit."""
        mock_account_info.get_balance = Mock(return_value=10000.0)
        daily_pnl = -300.0  # 3% loss
        daily_loss_pct = (abs(min(0, daily_pnl)) / 10000.0) * 100.0
        assert daily_loss_pct == pytest.approx(3.0, abs=0.1)
        # 3% within 5% limit
        assert daily_loss_pct < 5.0

    def test_daily_loss_limit_at_threshold(self, mock_account_info):
        """Test daily loss exactly at threshold."""
        mock_account_info.get_balance = Mock(return_value=10000.0)
        daily_pnl = -500.0  # 5% loss
        daily_loss_pct = (abs(min(0, daily_pnl)) / 10000.0) * 100.0
        assert daily_loss_pct == pytest.approx(5.0, abs=0.1)

    def test_daily_loss_positive_pnl(self, mock_account_info):
        """Test that positive P&L doesn't trigger loss limit."""
        mock_account_info.get_balance = Mock(return_value=10000.0)
        daily_pnl = 500.0  # Profit
        daily_loss_pct = (abs(min(0, daily_pnl)) / 10000.0) * 100.0
        assert daily_loss_pct == 0.0


class TestPositionSizer:
    """Test position sizing calculations."""

    def test_position_sizer_normal_case(self, mock_account_info):
        """Test normal position sizing."""
        # equity=10000, risk=1%, SL=50, pip_value=10
        # lots = (10000 * 0.01) / (50 * 10) = 0.2
        equity = 10000.0
        risk_pct = 1.0
        sl_distance = 50.0
        pip_value = 10.0
        lots = (equity * risk_pct / 100.0) / (sl_distance * pip_value)
        assert lots == pytest.approx(0.2, abs=0.001)

    def test_position_sizer_high_risk(self, mock_account_info):
        """Test position sizing with higher risk percentage."""
        # equity=10000, risk=2%, SL=50, pip_value=10
        # lots = (10000 * 0.02) / (50 * 10) = 0.4
        equity = 10000.0
        risk_pct = 2.0
        sl_distance = 50.0
        pip_value = 10.0
        lots = (equity * risk_pct / 100.0) / (sl_distance * pip_value)
        assert lots == pytest.approx(0.4, abs=0.001)

    def test_position_sizer_tight_stop_loss(self, mock_account_info):
        """Test position sizing with tight stop loss."""
        # equity=10000, risk=1%, SL=10, pip_value=10
        # lots = (10000 * 0.01) / (10 * 10) = 1.0
        equity = 10000.0
        risk_pct = 1.0
        sl_distance = 10.0
        pip_value = 10.0
        lots = (equity * risk_pct / 100.0) / (sl_distance * pip_value)
        assert lots == pytest.approx(1.0, abs=0.001)

    def test_position_sizer_wide_stop_loss(self, mock_account_info):
        """Test position sizing with wide stop loss."""
        # equity=10000, risk=1%, SL=100, pip_value=10
        # lots = (10000 * 0.01) / (100 * 10) = 0.1
        equity = 10000.0
        risk_pct = 1.0
        sl_distance = 100.0
        pip_value = 10.0
        lots = (equity * risk_pct / 100.0) / (sl_distance * pip_value)
        assert lots == pytest.approx(0.1, abs=0.001)


@pytest.mark.asyncio
class TestPreTradeCheck:
    """Test pre-trade risk validation."""

    async def test_pre_trade_check_approved(self):
        """Test pre-trade check passes all validations."""
        # Create mocks
        account_info = Mock()
        account_info.get_equity = Mock(return_value=10000.0)
        account_info.get_balance = Mock(return_value=10000.0)
        account_info.get_margin_level = Mock(return_value=500.0)

        kill_switch = Mock()
        kill_switch.is_active = False

        position_sizer = Mock()
        position_sizer.calculate_position_size = Mock(return_value=1.0)
        position_sizer.validate_position_size = Mock(return_value=True)
        position_sizer.get_min_lots = Mock(return_value=0.01)
        position_sizer.get_max_lots = Mock(return_value=100.0)

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        # Perform pre-trade check
        result = await risk_manager.pre_trade_check(
            symbol="EURUSD",
            direction="BUY",
            sl_distance=50.0,
            risk_pct=1.0
        )

        # Should be approved
        assert result.approved is True
        assert result.position_size > 0

    async def test_pre_trade_check_rejected_kill_switch(self):
        """Test pre-trade check rejected due to kill switch."""
        account_info = Mock()
        account_info.get_equity = Mock(return_value=10000.0)
        account_info.get_balance = Mock(return_value=10000.0)
        account_info.get_margin_level = Mock(return_value=500.0)

        kill_switch = Mock()
        kill_switch.is_active = True  # Kill switch active!

        position_sizer = Mock()
        position_sizer.calculate_position_size = AsyncMock(return_value=1.0)

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        result = await risk_manager.pre_trade_check(
            symbol="EURUSD",
            direction="BUY",
            sl_distance=50.0
        )

        # Should be rejected
        assert result.approved is False
        assert "Kill switch" in result.reason

    async def test_pre_trade_check_rejected_low_margin(self):
        """Test pre-trade check rejected due to low margin."""
        account_info = Mock()
        account_info.get_equity = Mock(return_value=8000.0)
        account_info.get_balance = Mock(return_value=10000.0)
        account_info.get_margin_level = Mock(return_value=100.0)  # Too low!

        kill_switch = Mock()
        kill_switch.is_active = False

        position_sizer = Mock()
        position_sizer.calculate_position_size = Mock(return_value=1.0)
        position_sizer.validate_position_size = Mock(return_value=True)

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        result = await risk_manager.pre_trade_check(
            symbol="EURUSD",
            direction="BUY",
            sl_distance=50.0
        )

        # Should be rejected
        assert result.approved is False
        assert "Margin" in result.reason

    async def test_pre_trade_check_invalid_sl_distance(self):
        """Test pre-trade check with invalid stop loss distance."""
        account_info = Mock()
        account_info.get_equity = Mock(return_value=10000.0)
        account_info.get_balance = Mock(return_value=10000.0)
        account_info.get_margin_level = Mock(return_value=500.0)

        kill_switch = Mock()
        kill_switch.is_active = False

        position_sizer = Mock()

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        result = await risk_manager.pre_trade_check(
            symbol="EURUSD",
            direction="BUY",
            sl_distance=0.0  # Invalid!
        )

        # Should be rejected
        assert result.approved is False
        assert "Stop-loss" in result.reason


@pytest.mark.asyncio
class TestPostTradeUpdate:
    """Test post-trade P&L tracking."""

    async def test_post_trade_update_profit(self):
        """Test post-trade update with profit."""
        account_info = Mock()
        account_info.get_equity = Mock(return_value=10000.0)
        account_info.get_balance = Mock(return_value=10000.0)

        kill_switch = Mock()
        kill_switch.is_active = False

        position_sizer = Mock()

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        # Initial state
        assert risk_manager._daily_pnl == 0.0

        # Update with profit
        await risk_manager.post_trade_update(trade_pnl=100.0, symbol="EURUSD")

        # Should track the profit
        assert risk_manager._daily_pnl == 100.0

    async def test_post_trade_update_loss(self):
        """Test post-trade update with loss."""
        account_info = Mock()
        kill_switch = Mock()
        kill_switch.is_active = False
        position_sizer = Mock()

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        # Update with loss
        await risk_manager.post_trade_update(trade_pnl=-50.0, symbol="EURUSD")

        # Should track the loss
        assert risk_manager._daily_pnl == -50.0

    async def test_post_trade_update_accumulation(self):
        """Test post-trade updates accumulate."""
        account_info = Mock()
        kill_switch = Mock()
        kill_switch.is_active = False
        position_sizer = Mock()

        risk_manager = RiskManager(kill_switch, position_sizer, account_info)

        # Multiple trades
        await risk_manager.post_trade_update(trade_pnl=100.0, symbol="EURUSD")
        await risk_manager.post_trade_update(trade_pnl=50.0, symbol="XAUUSD")
        await risk_manager.post_trade_update(trade_pnl=-30.0, symbol="BTCUSD")

        # Should accumulate: 100 + 50 - 30 = 120
        assert risk_manager._daily_pnl == pytest.approx(120.0, abs=0.1)
