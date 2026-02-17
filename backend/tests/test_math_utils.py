"""
PURPOSE: Integration tests for mathematical utility functions.

Tests core calculations used throughout the trading system:
- Position sizing and lot rounding
- Performance metrics (drawdown, Sharpe ratio, profit factor)
- Weight normalization for portfolio allocation
"""

import pytest
import numpy as np
from app.utils.math_utils import (
    round_lots,
    calculate_lot_size,
    calculate_drawdown,
    calculate_sharpe,
    calculate_profit_factor,
    normalize_weights,
    calculate_pip_value
)


class TestRoundLots:
    """Test lot rounding functionality."""

    def test_round_lots_default_step(self):
        """Test rounding with default 0.01 step."""
        assert round_lots(1.234) == pytest.approx(1.23, abs=0.001)
        assert round_lots(1.235) == pytest.approx(1.24, abs=0.001)
        assert round_lots(0.567) == pytest.approx(0.57, abs=0.001)

    def test_round_lots_custom_step(self):
        """Test rounding with custom step size."""
        assert round_lots(1.234, step=0.1) == pytest.approx(1.2, abs=0.001)
        assert round_lots(1.567, step=0.1) == pytest.approx(1.6, abs=0.001)
        assert round_lots(5.0, step=0.5) == pytest.approx(5.0, abs=0.001)

    def test_round_lots_zero(self):
        """Test rounding of zero."""
        assert round_lots(0) == 0.0

    def test_round_lots_already_rounded(self):
        """Test value already at step."""
        assert round_lots(1.01, step=0.01) == pytest.approx(1.01, abs=0.001)
        assert round_lots(2.50, step=0.5) == pytest.approx(2.5, abs=0.001)


class TestCalculateLotSize:
    """Test position sizing calculation."""

    def test_calculate_lot_size_normal(self):
        """Test normal lot size calculation."""
        # equity=10000, risk=1%, SL=50 points, pip_value=10 -> lots = (10000*0.01)/(50*10) = 0.2
        lot_size = calculate_lot_size(
            equity=10000.0,
            risk_pct=1.0,
            sl_points=50.0,
            pip_value_per_lot=10.0
        )
        assert lot_size == pytest.approx(0.2, abs=0.01)
        assert lot_size >= 0.01 and lot_size <= 100.0

    def test_calculate_lot_size_small_equity(self):
        """Test with small equity."""
        lot_size = calculate_lot_size(
            equity=1000.0,
            risk_pct=2.0,
            sl_points=10.0,
            pip_value_per_lot=1.0
        )
        # (1000*0.02)/(10*1) = 2.0
        assert lot_size == pytest.approx(2.0, abs=0.01)

    def test_calculate_lot_size_large_equity(self):
        """Test with large equity, should be clamped to max 100."""
        lot_size = calculate_lot_size(
            equity=1000000.0,
            risk_pct=10.0,
            sl_points=1.0,
            pip_value_per_lot=1.0
        )
        # (1000000*0.1)/(1*1) = 100000, clamped to 100
        assert lot_size == pytest.approx(100.0, abs=0.1)

    def test_calculate_lot_size_zero_sl(self):
        """Test with zero stop loss (should return min 0.01)."""
        lot_size = calculate_lot_size(
            equity=10000.0,
            risk_pct=1.0,
            sl_points=0.0,
            pip_value_per_lot=10.0
        )
        assert lot_size == 0.01

    def test_calculate_lot_size_negative_sl(self):
        """Test with negative stop loss (should return min 0.01)."""
        lot_size = calculate_lot_size(
            equity=10000.0,
            risk_pct=1.0,
            sl_points=-50.0,
            pip_value_per_lot=10.0
        )
        assert lot_size == 0.01

    def test_calculate_lot_size_zero_pip_value(self):
        """Test with zero pip value (should return min 0.01)."""
        lot_size = calculate_lot_size(
            equity=10000.0,
            risk_pct=1.0,
            sl_points=50.0,
            pip_value_per_lot=0.0
        )
        assert lot_size == 0.01

    def test_calculate_lot_size_high_risk_high_sl(self):
        """Test with high risk percentage but high stop loss."""
        lot_size = calculate_lot_size(
            equity=50000.0,
            risk_pct=5.0,
            sl_points=500.0,
            pip_value_per_lot=5.0
        )
        # (50000*0.05)/(500*5) = 2500/2500 = 1.0
        assert lot_size == pytest.approx(1.0, abs=0.01)


class TestCalculateDrawdown:
    """Test drawdown calculation."""

    def test_calculate_drawdown_normal(self):
        """Test normal drawdown calculation."""
        # (1000 - 800) / 1000 * 100 = 20%
        drawdown = calculate_drawdown(peak=1000.0, current=800.0)
        assert drawdown == pytest.approx(20.0, abs=0.1)

    def test_calculate_drawdown_no_drawdown(self):
        """Test when current >= peak (no drawdown)."""
        drawdown = calculate_drawdown(peak=1000.0, current=1050.0)
        assert drawdown == pytest.approx(0.0, abs=0.001)

    def test_calculate_drawdown_at_peak(self):
        """Test when current equals peak."""
        drawdown = calculate_drawdown(peak=1000.0, current=1000.0)
        assert drawdown == pytest.approx(0.0, abs=0.001)

    def test_calculate_drawdown_zero_peak(self):
        """Test with zero peak (should return 0)."""
        drawdown = calculate_drawdown(peak=0.0, current=100.0)
        assert drawdown == 0.0

    def test_calculate_drawdown_negative_peak(self):
        """Test with negative peak (should return 0)."""
        drawdown = calculate_drawdown(peak=-1000.0, current=-500.0)
        assert drawdown == 0.0

    def test_calculate_drawdown_severe(self):
        """Test severe drawdown."""
        # (10000 - 500) / 10000 * 100 = 95%
        drawdown = calculate_drawdown(peak=10000.0, current=500.0)
        assert drawdown == pytest.approx(95.0, abs=0.1)


class TestCalculateSharpe:
    """Test Sharpe ratio calculation."""

    def test_calculate_sharpe_positive_returns(self):
        """Test Sharpe with positive returns."""
        returns = [0.01, 0.02, 0.015, 0.018, 0.02]
        sharpe = calculate_sharpe(returns, risk_free=0.0)
        assert sharpe > 0  # Should be positive for positive mean returns
        assert not np.isnan(sharpe)

    def test_calculate_sharpe_negative_returns(self):
        """Test Sharpe with negative returns."""
        returns = [-0.01, -0.02, -0.015, -0.018, -0.02]
        sharpe = calculate_sharpe(returns, risk_free=0.0)
        assert sharpe < 0  # Should be negative for negative mean returns

    def test_calculate_sharpe_zero_volatility(self):
        """Test Sharpe with zero volatility (all same returns)."""
        returns = [0.01, 0.01, 0.01, 0.01, 0.01]
        sharpe = calculate_sharpe(returns, risk_free=0.0)
        assert sharpe == 0.0  # Zero volatility

    def test_calculate_sharpe_empty_returns(self):
        """Test Sharpe with empty returns list."""
        sharpe = calculate_sharpe([], risk_free=0.0)
        assert sharpe == 0.0

    def test_calculate_sharpe_single_return(self):
        """Test Sharpe with single return."""
        returns = [0.01]
        sharpe = calculate_sharpe(returns, risk_free=0.0)
        assert sharpe == 0.0  # Single value = zero variance

    def test_calculate_sharpe_with_risk_free_rate(self):
        """Test Sharpe with non-zero risk-free rate."""
        returns = [0.02, 0.03, 0.025, 0.028]
        sharpe = calculate_sharpe(returns, risk_free=0.01)
        # Should account for risk-free rate in numerator
        assert not np.isnan(sharpe)


class TestCalculateProfitFactor:
    """Test profit factor calculation."""

    def test_calculate_profit_factor_wins_and_losses(self):
        """Test normal profit factor (wins > losses)."""
        wins = [100.0, 150.0, 200.0]
        losses = [-50.0, -75.0]
        profit_factor = calculate_profit_factor(wins, losses)
        # sum(wins) / abs(sum(losses)) = 450 / 125 = 3.6
        assert profit_factor == pytest.approx(3.6, abs=0.01)

    def test_calculate_profit_factor_losses_exceed_wins(self):
        """Test when losses exceed wins."""
        wins = [50.0, 100.0]
        losses = [-150.0, -200.0]
        profit_factor = calculate_profit_factor(wins, losses)
        # 150 / 350 = 0.428...
        assert profit_factor == pytest.approx(0.428, abs=0.01)

    def test_calculate_profit_factor_no_losses(self):
        """Test with no losses (should return 0)."""
        wins = [100.0, 150.0, 200.0]
        losses = []
        profit_factor = calculate_profit_factor(wins, losses)
        assert profit_factor == 0.0

    def test_calculate_profit_factor_empty_wins(self):
        """Test with no wins."""
        wins = []
        losses = [-50.0, -100.0]
        profit_factor = calculate_profit_factor(wins, losses)
        assert profit_factor == 0.0

    def test_calculate_profit_factor_both_empty(self):
        """Test with empty win and loss lists."""
        profit_factor = calculate_profit_factor([], [])
        assert profit_factor == 0.0

    def test_calculate_profit_factor_breakeven(self):
        """Test breakeven scenario."""
        wins = [100.0, 100.0]
        losses = [-100.0, -100.0]
        profit_factor = calculate_profit_factor(wins, losses)
        # 200 / 200 = 1.0
        assert profit_factor == pytest.approx(1.0, abs=0.001)


class TestNormalizeWeights:
    """Test weight normalization."""

    def test_normalize_weights_normal(self):
        """Test normal weight normalization."""
        weights = {"EURUSD": 0.3, "XAUUSD": 0.5, "BTCUSD": 0.2}
        normalized = normalize_weights(weights)
        # Sum = 1.0, already normalized
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.001)
        assert normalized["EURUSD"] == pytest.approx(0.3, abs=0.001)

    def test_normalize_weights_non_normalized(self):
        """Test normalizing non-normalized weights."""
        weights = {"EURUSD": 1.0, "XAUUSD": 2.0, "BTCUSD": 1.0}
        normalized = normalize_weights(weights)
        # Sum = 4.0, should normalize to sum 1.0
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.001)
        assert normalized["EURUSD"] == pytest.approx(0.25, abs=0.001)
        assert normalized["XAUUSD"] == pytest.approx(0.5, abs=0.001)
        assert normalized["BTCUSD"] == pytest.approx(0.25, abs=0.001)

    def test_normalize_weights_single_symbol(self):
        """Test with single symbol."""
        weights = {"EURUSD": 5.0}
        normalized = normalize_weights(weights)
        assert sum(normalized.values()) == pytest.approx(1.0, abs=0.001)
        assert normalized["EURUSD"] == pytest.approx(1.0, abs=0.001)

    def test_normalize_weights_zero_sum(self):
        """Test with zero sum (should return empty dict)."""
        weights = {"EURUSD": 0.0, "XAUUSD": 0.0}
        normalized = normalize_weights(weights)
        assert len(normalized) == 0

    def test_normalize_weights_empty(self):
        """Test with empty weights dict."""
        normalized = normalize_weights({})
        assert len(normalized) == 0

    def test_normalize_weights_very_small(self):
        """Test with very small weights."""
        weights = {"EURUSD": 1e-10, "XAUUSD": 1e-10, "BTCUSD": 1e-10}
        normalized = normalize_weights(weights)
        assert sum(normalized.values()) == pytest.approx(1.0, abs=1e-9)


class TestCalculatePipValue:
    """Test pip value calculation."""

    def test_calculate_pip_value_xauusd(self):
        """Test pip value for XAUUSD."""
        pip_value = calculate_pip_value("XAUUSD", 1.0)
        assert pip_value == pytest.approx(10.0, abs=0.1)

    def test_calculate_pip_value_eurusd(self):
        """Test pip value for EURUSD."""
        pip_value = calculate_pip_value("EURUSD", 1.0)
        assert pip_value == pytest.approx(10.0, abs=0.1)

    def test_calculate_pip_value_btcusd(self):
        """Test pip value for BTCUSD."""
        pip_value = calculate_pip_value("BTCUSD", 1.0)
        assert pip_value == pytest.approx(1.0, abs=0.1)

    def test_calculate_pip_value_multiple_lots(self):
        """Test pip value with multiple lots."""
        pip_value = calculate_pip_value("EURUSD", 2.5)
        # 2.5 * 10 = 25
        assert pip_value == pytest.approx(25.0, abs=0.1)

    def test_calculate_pip_value_unknown_symbol(self):
        """Test pip value for unknown symbol (should use default)."""
        pip_value = calculate_pip_value("UNKNOWN", 1.0)
        # Default is 10
        assert pip_value == pytest.approx(10.0, abs=0.1)
