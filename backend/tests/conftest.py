"""
PURPOSE: Pytest fixtures for JSR Hydra integration tests.

Provides shared test data and mock objects including:
- Async SQLite session for database testing
- Test configuration settings
- Sample OHLCV candle data
- Mock event bus for event capture
"""

import pytest
import pytest_asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, AsyncMock, MagicMock


@pytest_asyncio.fixture
async def async_session():
    """
    PURPOSE: In-memory SQLite async session for testing.

    Creates a fresh async SQLite database for each test with all tables created.
    Automatically cleaned up after test completion.

    Returns:
        AsyncSession: SQLAlchemy async session connected to in-memory SQLite.
    """
    # Use in-memory SQLite for fast tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True
    )

    # Import models to ensure tables are created
    from app.models.trade import Trade
    from app.models.account import Account
    from app.models.system import SystemStatus

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Trade.metadata.create_all)
        await conn.run_sync(Account.metadata.create_all)
        await conn.run_sync(SystemStatus.metadata.create_all)

    # Create session factory
    async_session_local = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_local() as session:
        yield session

    # Cleanup
    await engine.dispose()


@pytest.fixture
def test_settings():
    """
    PURPOSE: Settings override with test values.

    Provides a Settings object with test-appropriate defaults:
    - Dry run enabled
    - Debug logging enabled
    - Test database URL
    - Test credentials

    Returns:
        Settings: Configuration object with test values.
    """
    from app.config.settings import Settings

    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/1",  # Test Redis database
        MT5_HOST="localhost",
        MT5_RPYC_PORT=18812,
        MT5_LOGIN=12345,
        MT5_PASSWORD="test_password",
        MT5_SERVER="test_server",
        TELEGRAM_BOT_TOKEN="test_token",
        TELEGRAM_CHAT_ID="test_chat",
        MAX_DRAWDOWN_PCT=15.0,
        DAILY_LOSS_LIMIT_PCT=5.0,
        RISK_PER_TRADE_PCT=1.0,
        DEBUG=True,
        DRY_RUN=True,
        LOG_LEVEL="DEBUG",
        JWT_SECRET="test-secret-key",
        API_KEY="test-api-key",
        ADMIN_USERNAME="test_admin",
        ADMIN_PASSWORD="test_password"
    )

    return settings


@pytest.fixture
def sample_candles():
    """
    PURPOSE: DataFrame with 100 rows of OHLCV data for testing indicators.

    Generates realistic candlestick data with:
    - High >= Close >= Open >= Low (most candles)
    - Positive volume
    - Trending pattern (uptrend first 50 candles, downtrend next 50)

    Returns:
        pd.DataFrame: OHLCV data with columns [Open, High, Low, Close, Volume].
    """
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1H")

    # Generate trending price data
    prices = np.cumsum(np.random.randn(100) * 0.5 + 0.3)  # Slight uptrend
    prices = prices - prices[0] + 100  # Normalize to start at 100

    # Generate OHLCV
    opens = prices + np.random.randn(100) * 0.2
    closes = prices + np.random.randn(100) * 0.2
    highs = np.maximum.reduce([opens, closes, prices + np.abs(np.random.randn(100) * 0.5)])
    lows = np.minimum.reduce([opens, closes, prices - np.abs(np.random.randn(100) * 0.5)])
    volumes = np.random.randint(1000, 10000, 100)

    df = pd.DataFrame({
        "Datetime": dates,
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volumes
    })

    df.set_index("Datetime", inplace=True)

    return df


@pytest.fixture
def mock_event_bus():
    """
    PURPOSE: Mock EventBus that captures published events.

    Creates a mock event bus that tracks all published events in a list
    for assertion in tests.

    Returns:
        MagicMock: Mock EventBus with published_events list.
    """
    mock_bus = MagicMock()
    mock_bus.published_events = []

    async def mock_publish(event_type, data=None, severity="INFO"):
        """Mock publish method that captures events."""
        mock_bus.published_events.append({
            "event_type": event_type,
            "data": data,
            "severity": severity,
            "timestamp": datetime.utcnow()
        })

    mock_bus.publish = AsyncMock(side_effect=mock_publish)
    mock_bus.subscribe = MagicMock()

    return mock_bus


@pytest.fixture
def mock_account_info():
    """
    PURPOSE: Mock AccountInfo with realistic account data.

    Returns:
        Mock: AccountInfo mock with methods for equity, balance, margin.
    """
    mock = Mock()
    mock.get_equity = Mock(return_value=10000.0)
    mock.get_balance = Mock(return_value=10000.0)
    mock.get_margin_level = Mock(return_value=500.0)
    mock.get_free_margin = Mock(return_value=5000.0)
    mock.get_used_margin = Mock(return_value=5000.0)

    return mock


@pytest.fixture
def mock_kill_switch():
    """
    PURPOSE: Mock KillSwitch for risk testing.

    Returns:
        Mock: KillSwitch mock with is_active property.
    """
    mock = Mock()
    mock.is_active = False

    return mock
