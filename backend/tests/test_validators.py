"""
PURPOSE: Integration tests for input validation functions.

Tests validation of trading parameters:
- Symbol validation against supported symbols
- Lot size range checks
- Price positivity validation
- Portfolio weight constraints
"""

import pytest
import pandas as pd
from app.utils.validators import (
    validate_symbol,
    validate_lots,
    validate_price,
    validate_allocation_weights,
    validate_ohlcv
)


class TestValidateSymbol:
    """Test symbol validation."""

    def test_validate_symbol_supported(self):
        """Test validation of supported symbols."""
        assert validate_symbol("XAUUSD") is True
        assert validate_symbol("BTCUSD") is True
        assert validate_symbol("EURUSD") is True

    def test_validate_symbol_unsupported(self):
        """Test validation of unsupported symbols."""
        assert validate_symbol("GBPUSD") is False
        assert validate_symbol("USDJPY") is False
        assert validate_symbol("UNKNOWN") is False

    def test_validate_symbol_case_sensitive(self):
        """Test that symbol validation is case-sensitive."""
        assert validate_symbol("xauusd") is False
        assert validate_symbol("Xauusd") is False
        assert validate_symbol("XAUUSD") is True

    def test_validate_symbol_empty_string(self):
        """Test validation of empty symbol."""
        assert validate_symbol("") is False

    def test_validate_symbol_whitespace(self):
        """Test validation with whitespace."""
        assert validate_symbol(" XAUUSD") is False
        assert validate_symbol("XAUUSD ") is False


class TestValidateLots:
    """Test lot size validation."""

    def test_validate_lots_in_range(self):
        """Test lot sizes within default range."""
        assert validate_lots(0.01) is True
        assert validate_lots(1.0) is True
        assert validate_lots(50.0) is True
        assert validate_lots(100.0) is True

    def test_validate_lots_at_boundaries(self):
        """Test lot sizes at min/max boundaries."""
        assert validate_lots(0.01, min_lot=0.01, max_lot=100.0) is True
        assert validate_lots(100.0, min_lot=0.01, max_lot=100.0) is True

    def test_validate_lots_below_minimum(self):
        """Test lot size below minimum."""
        assert validate_lots(0.001, min_lot=0.01, max_lot=100.0) is False
        assert validate_lots(0.0, min_lot=0.01, max_lot=100.0) is False

    def test_validate_lots_above_maximum(self):
        """Test lot size above maximum."""
        assert validate_lots(101.0, min_lot=0.01, max_lot=100.0) is False
        assert validate_lots(1000.0, min_lot=0.01, max_lot=100.0) is False

    def test_validate_lots_custom_range(self):
        """Test with custom min/max range."""
        assert validate_lots(0.5, min_lot=0.1, max_lot=10.0) is True
        assert validate_lots(0.05, min_lot=0.1, max_lot=10.0) is False
        assert validate_lots(15.0, min_lot=0.1, max_lot=10.0) is False

    def test_validate_lots_negative(self):
        """Test negative lot size."""
        assert validate_lots(-1.0) is False

    def test_validate_lots_fractional(self):
        """Test fractional lot sizes."""
        assert validate_lots(0.25) is True
        assert validate_lots(0.555) is True


class TestValidatePrice:
    """Test price validation."""

    def test_validate_price_positive(self):
        """Test positive prices."""
        assert validate_price(100.0) is True
        assert validate_price(0.001) is True
        assert validate_price(99999.99) is True

    def test_validate_price_zero(self):
        """Test zero price (should fail)."""
        assert validate_price(0.0) is False

    def test_validate_price_negative(self):
        """Test negative prices."""
        assert validate_price(-100.0) is False
        assert validate_price(-0.001) is False

    def test_validate_price_very_small(self):
        """Test very small positive price."""
        assert validate_price(1e-10) is True

    def test_validate_price_very_large(self):
        """Test very large price."""
        assert validate_price(1e10) is True


class TestValidateAllocationWeights:
    """Test portfolio allocation weight validation."""

    def test_validate_allocation_weights_valid(self):
        """Test valid weight allocation."""
        weights = {"EURUSD": 0.5, "XAUUSD": 0.3, "BTCUSD": 0.2}
        assert validate_allocation_weights(weights) is True

    def test_validate_allocation_weights_sum_less_than_one(self):
        """Test weights that sum to less than 1.0."""
        weights = {"EURUSD": 0.3, "XAUUSD": 0.2}
        assert validate_allocation_weights(weights) is True

    def test_validate_allocation_weights_zero_weights(self):
        """Test with all zero weights."""
        weights = {"EURUSD": 0.0, "XAUUSD": 0.0}
        assert validate_allocation_weights(weights) is True

    def test_validate_allocation_weights_exceeds_one(self):
        """Test weights that exceed 1.0 (should fail)."""
        weights = {"EURUSD": 0.6, "XAUUSD": 0.5}
        assert validate_allocation_weights(weights) is False

    def test_validate_allocation_weights_negative(self):
        """Test with negative weights (should fail)."""
        weights = {"EURUSD": 0.7, "XAUUSD": -0.3}
        assert validate_allocation_weights(weights) is False

    def test_validate_allocation_weights_above_one_single(self):
        """Test single weight above 1.0 (should fail)."""
        weights = {"EURUSD": 1.5}
        assert validate_allocation_weights(weights) is False

    def test_validate_allocation_weights_empty(self):
        """Test empty weights dictionary."""
        weights = {}
        assert validate_allocation_weights(weights) is True

    def test_validate_allocation_weights_floating_point_precision(self):
        """Test weights with floating point precision issues."""
        # Should allow slight overshoot due to floating point
        weights = {"EURUSD": 0.33333, "XAUUSD": 0.33333, "BTCUSD": 0.33334}
        assert validate_allocation_weights(weights) is True

    def test_validate_allocation_weights_exactly_one(self):
        """Test weights that sum to exactly 1.0."""
        weights = {"EURUSD": 0.5, "XAUUSD": 0.5}
        assert validate_allocation_weights(weights) is True


class TestValidateOHLCV:
    """Test OHLCV data validation."""

    def test_validate_ohlcv_valid(self):
        """Test valid OHLCV data."""
        df = pd.DataFrame({
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 2000, 1500]
        })
        assert validate_ohlcv(df) is True

    def test_validate_ohlcv_missing_columns(self):
        """Test OHLCV with missing columns."""
        df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Close": [100.5, 101.5]
            # Missing Low and Volume
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_null_values(self):
        """Test OHLCV with null values in OHLC."""
        df = pd.DataFrame({
            "Open": [100.0, None, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 2000, 1500]
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_high_less_than_low(self):
        """Test OHLCV where High < Low (invalid)."""
        df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [99.0, 100.0],
            "Low": [100.0, 101.0],
            "Close": [100.5, 101.5],
            "Volume": [1000, 2000]
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_negative_open(self):
        """Test OHLCV with negative Open."""
        df = pd.DataFrame({
            "Open": [-100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [1000, 2000]
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_negative_volume(self):
        """Test OHLCV with negative volume."""
        df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [-1000, 2000]
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_empty_dataframe(self):
        """Test empty OHLCV dataframe."""
        df = pd.DataFrame({
            "Open": [],
            "High": [],
            "Low": [],
            "Close": [],
            "Volume": []
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_none(self):
        """Test with None instead of dataframe."""
        assert validate_ohlcv(None) is False

    def test_validate_ohlcv_zero_open(self):
        """Test OHLCV with zero Open (should fail)."""
        df = pd.DataFrame({
            "Open": [0.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [1000, 2000]
        })
        assert validate_ohlcv(df) is False

    def test_validate_ohlcv_realistic_candlestick(self):
        """Test with realistic candlestick pattern."""
        df = pd.DataFrame({
            "Open": [100.0, 101.5, 103.0],
            "High": [102.0, 104.5, 105.0],
            "Low": [99.5, 100.5, 102.0],
            "Close": [101.0, 102.5, 104.0],
            "Volume": [50000, 75000, 60000]
        })
        assert validate_ohlcv(df) is True
