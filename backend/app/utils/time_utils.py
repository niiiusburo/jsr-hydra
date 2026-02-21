"""
PURPOSE: Time utilities for market hours, session detection, and trading window management.
Handles UTC-based calculations for forex, crypto, and news event windows.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

# Crypto symbols that trade 24/7
CRYPTO_SYMBOLS = {"BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"}


def get_utc_now() -> datetime:
    """
    PURPOSE: Return the current UTC time as a timezone-aware datetime object.

    Returns:
        datetime: Current UTC time with timezone info.
    """
    return datetime.now(timezone.utc)


def is_market_open(symbol: str = "XAUUSD") -> bool:
    """
    PURPOSE: Check if the forex market is currently open for the given symbol.
    Forex markets are open Sunday 17:00 EST to Friday 17:00 EST (with session breaks).

    Args:
        symbol: Trading symbol (default "XAUUSD"). Currently treated as forex hours.

    Returns:
        bool: True if market is currently within trading hours, False otherwise.
    """
    # Crypto trades 24/7
    if symbol.upper() in CRYPTO_SYMBOLS:
        return True

    now = get_utc_now()
    current_weekday = now.weekday()  # Monday=0, Sunday=6
    current_hour_utc = now.hour

    # Sunday 17:00 EST = Sunday 22:00 UTC
    # Friday 17:00 EST = Friday 22:00 UTC
    # Forex is closed Friday 22:00 UTC to Sunday 22:00 UTC

    if current_weekday == 6:    # Sunday
        return current_hour_utc >= 22  # Forex opens Sunday 22:00 UTC
    elif current_weekday == 5:  # Saturday — always closed
        return False
    elif current_weekday == 4:  # Friday
        return current_hour_utc < 22   # Forex closes Friday 22:00 UTC
    else:                        # Monday through Thursday
        return True


def is_weekend() -> bool:
    """
    PURPOSE: Determine if forex market is in weekend closure.

    Forex weekend closure: Friday 22:00 UTC to Sunday 22:00 UTC.
    This aligns with is_market_open() so the two checks don't contradict.

    Returns:
        bool: True if currently in weekend closure period, False otherwise.
    """
    now = get_utc_now()
    weekday = now.weekday()  # Monday=0, Sunday=6
    hour = now.hour

    if weekday == 5:  # Saturday — always closed
        return True
    if weekday == 4 and hour >= 22:  # Friday after 22:00 UTC — closed
        return True
    if weekday == 6 and hour < 22:  # Sunday before 22:00 UTC — still closed
        return True
    return False


def get_session(dt: Optional[datetime] = None) -> str:
    """
    PURPOSE: Determine the current or specified trading session based on UTC time.

    Sessions:
    - ASIAN: 00:00-08:00 UTC
    - LONDON: 08:00-16:00 UTC
    - NEWYORK: 13:00-22:00 UTC
    - CLOSED: Outside all trading hours

    Args:
        dt: Optional datetime to check. If None, uses current UTC time.

    Returns:
        str: Session name (ASIAN, LONDON, NEWYORK, or CLOSED).
    """
    if dt is None:
        dt = get_utc_now()

    hour = dt.hour

    # Session overlap times have priority: NEWYORK > LONDON > ASIAN
    if 13 <= hour < 22:
        return "NEWYORK"
    elif 8 <= hour < 13:
        return "LONDON"
    elif 0 <= hour < 8:
        return "ASIAN"
    else:
        return "CLOSED"


def next_session_open() -> datetime:
    """
    PURPOSE: Calculate when the next trading session opens based on current UTC time.

    Returns:
        datetime: Next session start time in UTC.
    """
    now = get_utc_now()
    hour = now.hour

    # Sessions start at: ASIAN (00:00), LONDON (08:00), NEWYORK (13:00)
    if hour < 0:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif hour < 8:
        return now.replace(hour=8, minute=0, second=0, microsecond=0)
    elif hour < 13:
        return now.replace(hour=13, minute=0, second=0, microsecond=0)
    else:
        # Next ASIAN session is tomorrow at 00:00
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=0, minute=0, second=0, microsecond=0)


def is_high_impact_news_window() -> bool:
    """
    PURPOSE: Placeholder function to detect high-impact news event windows.
    Should be integrated with economic calendar data in future.

    Returns:
        bool: False (placeholder). Returns True when high-impact news is scheduled.
    """
    return False


def seconds_until_daily_reset() -> int:
    """
    PURPOSE: Calculate seconds remaining until the next daily reset at 00:00 UTC.

    Returns:
        int: Number of seconds until next 00:00 UTC.
    """
    now = get_utc_now()
    next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = next_reset - now
    return int(delta.total_seconds())
