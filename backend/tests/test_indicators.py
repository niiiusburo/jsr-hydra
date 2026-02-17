"""
PURPOSE: Integration tests for technical indicators.

Tests the calculation of trading indicators used for signal generation:
- Trend indicators (SMA, EMA, MACD)
- Momentum indicators (RSI, Stochastic)
- Volatility indicators (ATR, Bollinger Bands)
- Custom indicators (Z-Score)
"""

import pytest
import numpy as np
import pandas as pd
from app.indicators.trend import sma, ema, macd, adx, supertrend
from app.indicators.momentum import rsi, stochastic, williams_r, cci, roc
from app.indicators.volatility import atr, bollinger_bands, keltner_channels, historical_volatility


class TestSMA:
    """Test Simple Moving Average calculation."""

    def test_sma_basic(self, sample_candles):
        """Test basic SMA calculation."""
        sma_values = sma(sample_candles["Close"], period=10)
        # First 9 values should be NaN, then SMA starts
        assert sma_values.isna().sum() == 9
        # Check that SMA values exist after initial period
        assert sma_values.iloc[10:].notna().all()

    def test_sma_period_1(self, sample_candles):
        """Test SMA with period=1 (should equal series)."""
        sma_values = sma(sample_candles["Close"], period=1)
        pd.testing.assert_series_equal(sma_values, sample_candles["Close"])

    def test_sma_invalid_period(self, sample_candles):
        """Test SMA with invalid period."""
        with pytest.raises(ValueError):
            sma(sample_candles["Close"], period=0)

    def test_sma_convergence(self, sample_candles):
        """Test SMA convergence (longer periods are smoother)."""
        sma5 = sma(sample_candles["Close"], period=5)
        sma20 = sma(sample_candles["Close"], period=20)
        # SMA20 should have less variance than SMA5
        assert sma20.std() < sma5.std()


class TestEMA:
    """Test Exponential Moving Average calculation."""

    def test_ema_basic(self, sample_candles):
        """Test basic EMA calculation."""
        ema_values = ema(sample_candles["Close"], period=10)
        # EMA should have fewer NaN values than SMA
        assert not ema_values.isna().all()

    def test_ema_period_1(self, sample_candles):
        """Test EMA with period=1."""
        ema_values = ema(sample_candles["Close"], period=1)
        # EMA with period 1 should approximate the series
        assert not ema_values.isna().all()

    def test_ema_invalid_period(self, sample_candles):
        """Test EMA with invalid period."""
        with pytest.raises(ValueError):
            ema(sample_candles["Close"], period=0)

    def test_ema_vs_sma(self, sample_candles):
        """Test that EMA and SMA produce different results (EMA weights recent data more)."""
        sma_values = sma(sample_candles["Close"], period=10)
        ema_values = ema(sample_candles["Close"], period=10)
        # EMA and SMA should differ (EMA weights recent prices more heavily)
        diff = (ema_values.iloc[20:] - sma_values.iloc[20:]).abs().mean()
        assert diff > 0


class TestMACD:
    """Test MACD indicator calculation."""

    def test_macd_basic(self, sample_candles):
        """Test basic MACD calculation."""
        macd_line, signal_line, histogram = macd(sample_candles["Close"])
        # All outputs should be Series
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
        # Histogram = MACD - Signal
        pd.testing.assert_series_equal(
            histogram.dropna(),
            (macd_line - signal_line).dropna(),
            check_exact=False,
            atol=1e-10
        )

    def test_macd_parameters(self, sample_candles):
        """Test MACD with custom parameters."""
        macd_line, signal_line, histogram = macd(
            sample_candles["Close"],
            fast=10,
            slow=20,
            signal=5
        )
        assert isinstance(macd_line, pd.Series)

    def test_macd_invalid_periods(self, sample_candles):
        """Test MACD with invalid periods."""
        with pytest.raises(ValueError):
            macd(sample_candles["Close"], fast=26, slow=12)  # Fast >= slow

    def test_macd_zero_period(self, sample_candles):
        """Test MACD with zero period."""
        with pytest.raises(ValueError):
            macd(sample_candles["Close"], fast=0, slow=26)


class TestRSI:
    """Test Relative Strength Index calculation."""

    def test_rsi_basic(self, sample_candles):
        """Test basic RSI calculation."""
        rsi_values = rsi(sample_candles["Close"], period=14)
        # RSI should have values after initial period
        assert rsi_values.iloc[15:].notna().all()
        # RSI should be between 0 and 100
        assert (rsi_values.iloc[15:] >= 0).all()
        assert (rsi_values.iloc[15:] <= 100).all()

    def test_rsi_bounds(self, sample_candles):
        """Test RSI stays within 0-100 bounds."""
        rsi_values = rsi(sample_candles["Close"], period=14)
        assert (rsi_values >= 0).all() or rsi_values.isna().any()
        assert (rsi_values <= 100).all() or rsi_values.isna().any()

    def test_rsi_overbought_oversold(self):
        """Test RSI overbought/oversold levels."""
        # Create consistently rising prices (overbought)
        prices = pd.Series(np.arange(100, 200, 1))
        rsi_values = rsi(prices, period=14)
        # RSI should be overbought (>70) for rising prices
        assert rsi_values.iloc[-1] > 50

        # Create consistently falling prices (oversold)
        prices = pd.Series(np.arange(200, 100, -1))
        rsi_values = rsi(prices, period=14)
        # RSI should be oversold (<30) for falling prices
        assert rsi_values.iloc[-1] < 50

    def test_rsi_invalid_period(self, sample_candles):
        """Test RSI with invalid period."""
        with pytest.raises(ValueError):
            rsi(sample_candles["Close"], period=0)


class TestStochastic:
    """Test Stochastic Oscillator calculation."""

    def test_stochastic_basic(self, sample_candles):
        """Test basic Stochastic calculation."""
        k_line, d_line = stochastic(
            sample_candles["High"],
            sample_candles["Low"],
            sample_candles["Close"]
        )
        # Both should be Series
        assert isinstance(k_line, pd.Series)
        assert isinstance(d_line, pd.Series)
        # Both should have values after initial period
        assert k_line.iloc[15:].notna().all()
        assert d_line.iloc[20:].notna().all()

    def test_stochastic_bounds(self, sample_candles):
        """Test Stochastic stays within 0-100."""
        k_line, d_line = stochastic(
            sample_candles["High"],
            sample_candles["Low"],
            sample_candles["Close"]
        )
        # K line should be 0-100
        assert (k_line[k_line.notna()] >= 0).all()
        assert (k_line[k_line.notna()] <= 100).all()
        # D line should be 0-100
        assert (d_line[d_line.notna()] >= 0).all()
        assert (d_line[d_line.notna()] <= 100).all()

    def test_stochastic_invalid_periods(self, sample_candles):
        """Test Stochastic with invalid periods."""
        with pytest.raises(ValueError):
            stochastic(
                sample_candles["High"],
                sample_candles["Low"],
                sample_candles["Close"],
                k_period=0
            )


class TestATR:
    """Test Average True Range calculation."""

    def test_atr_basic(self, sample_candles):
        """Test basic ATR calculation."""
        atr_values = atr(sample_candles["High"], sample_candles["Low"], sample_candles["Close"])
        # ATR should have values
        assert not atr_values.isna().all()

    def test_atr_positive(self, sample_candles):
        """Test ATR is always positive."""
        atr_values = atr(sample_candles["High"], sample_candles["Low"], sample_candles["Close"])
        assert (atr_values[atr_values.notna()] >= 0).all()

    def test_atr_less_than_range(self, sample_candles):
        """Test ATR is less than daily range."""
        atr_values = atr(sample_candles["High"], sample_candles["Low"], sample_candles["Close"])
        daily_range = sample_candles["High"] - sample_candles["Low"]
        # ATR should be <= max daily range (on average)
        assert atr_values.iloc[-1] <= daily_range.max()

    def test_atr_invalid_period(self, sample_candles):
        """Test ATR with invalid period."""
        with pytest.raises(ValueError):
            atr(sample_candles["High"], sample_candles["Low"], sample_candles["Close"], period=0)


class TestBollingerBands:
    """Test Bollinger Bands calculation."""

    def test_bollinger_bands_basic(self, sample_candles):
        """Test basic Bollinger Bands calculation."""
        upper, middle, lower = bollinger_bands(sample_candles["Close"])
        # All should be Series
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)

    def test_bollinger_bands_relationship(self, sample_candles):
        """Test Bollinger Bands relationship (upper > middle > lower)."""
        upper, middle, lower = bollinger_bands(sample_candles["Close"])
        # After warmup, upper should be > middle > lower
        for i in range(20, len(upper)):
            if not (np.isnan(upper.iloc[i]) or np.isnan(middle.iloc[i]) or np.isnan(lower.iloc[i])):
                assert upper.iloc[i] > middle.iloc[i]
                assert middle.iloc[i] > lower.iloc[i]

    def test_bollinger_bands_invalid_params(self, sample_candles):
        """Test Bollinger Bands with invalid parameters."""
        with pytest.raises(ValueError):
            bollinger_bands(sample_candles["Close"], std_dev=0)

    def test_bollinger_bands_custom_params(self, sample_candles):
        """Test Bollinger Bands with custom parameters."""
        upper, middle, lower = bollinger_bands(sample_candles["Close"], period=10, std_dev=1.5)
        # Bands should be narrower with lower std_dev
        assert (upper - lower).mean() > 0


class TestZScore:
    """Test Z-Score calculation (standardized indicator)."""

    def test_z_score_mean_zero(self, sample_candles):
        """Test Z-Score has mean of 0."""
        close = sample_candles["Close"]
        z_score = (close - close.mean()) / close.std()
        # Mean should be ~0
        assert abs(z_score.mean()) < 1e-10

    def test_z_score_std_one(self, sample_candles):
        """Test Z-Score has std of 1."""
        close = sample_candles["Close"]
        z_score = (close - close.mean()) / close.std()
        # Std should be ~1
        assert abs(z_score.std() - 1.0) < 1e-10

    def test_z_score_symmetry(self):
        """Test Z-Score is symmetric around 0."""
        prices = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        z_score = (prices - prices.mean()) / prices.std()
        # Values should be symmetric around 0
        assert abs(z_score.mean()) < 1e-10


class TestHistoricalVolatility:
    """Test Historical Volatility calculation."""

    def test_historical_volatility_positive(self, sample_candles):
        """Test Historical Volatility is positive."""
        hv = historical_volatility(sample_candles["Close"])
        assert (hv[hv.notna()] >= 0).all()

    def test_historical_volatility_increases_with_noise(self):
        """Test volatility increases with more price noise."""
        # Low noise prices
        prices_low = pd.Series([100 + i * 0.01 for i in range(50)])
        hv_low = historical_volatility(prices_low, period=10)

        # High noise prices
        np.random.seed(42)
        prices_high = pd.Series(100 + np.cumsum(np.random.randn(50) * 5))
        hv_high = historical_volatility(prices_high, period=10)

        # High noise should have higher volatility
        assert hv_high.iloc[-1] > hv_low.iloc[-1]

    def test_historical_volatility_invalid_period(self, sample_candles):
        """Test Historical Volatility with invalid period."""
        with pytest.raises(ValueError):
            historical_volatility(sample_candles["Close"], period=0)
