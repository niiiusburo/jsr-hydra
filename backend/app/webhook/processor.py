"""
PURPOSE: TradingView webhook signal processor for JSR Hydra.

Bridges inbound TradingView Pine Script webhook alerts to the internal trading
engine signal format. Normalises symbol names, stores alerts in Redis for
engine pickup, and maintains an in-memory alert history for the dashboard.

CALLED BY:
    - app/api/routes_webhook.py (POST /api/webhook/tradingview)
"""

import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import redis as redis_sync

from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Maximum number of alerts to retain in the in-memory ring buffer
MAX_ALERT_HISTORY = 100

# Redis channel that the engine subscribes to for webhook-sourced signals
REDIS_CHANNEL = "jsr:webhook:tradingview"

# Redis key prefix for the latest alert per symbol (TTL 5 minutes)
REDIS_LATEST_KEY_PREFIX = "jsr:webhook:latest:"
REDIS_LATEST_TTL_SECONDS = 300

# Common TradingView symbol → MT5 symbol mappings
_TV_SYMBOL_MAP: Dict[str, str] = {
    "BTCUSDT": "BTCUSD",
    "ETHUSDT": "ETHUSD",
    "BNBUSDT": "BNBUSD",
    "SOLUSDT": "SOLUSD",
    "XRPUSDT": "XRPUSD",
}


class WebhookProcessor:
    """
    PURPOSE: Processes TradingView webhook alerts and routes them to the engine.

    Maintains a rolling in-memory alert history (last 100), exposes status
    information for the dashboard, and writes signals to Redis so the trading
    engine can pick them up on the next cycle.

    Attributes:
        _alert_history: Deque of the last MAX_ALERT_HISTORY alert dicts.
        _total_received: Cumulative count of alerts received since start.
        _enabled: Whether the processor accepts new alerts.
        _last_alert_time: ISO-8601 timestamp of the most recent alert.
        _redis: Synchronous Redis client for cross-process signal delivery.
    """

    def __init__(self) -> None:
        """
        PURPOSE: Initialise the processor with empty state and Redis connection.

        CALLED BY: Module-level singleton factory get_webhook_processor()
        """
        self._alert_history: deque = deque(maxlen=MAX_ALERT_HISTORY)
        self._total_received: int = 0
        self._enabled: bool = True
        self._last_alert_time: Optional[str] = None

        # Synchronous Redis client — matches the pattern used in brain.py
        self._redis: Optional[redis_sync.Redis] = None
        try:
            self._redis = redis_sync.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            self._redis.ping()
            logger.info("webhook_processor_redis_connected")
        except Exception as e:
            logger.warning("webhook_processor_redis_unavailable", error=str(e))
            self._redis = None

    # ════════════════════════════════════════════════════════════════
    # Public API
    # ════════════════════════════════════════════════════════════════

    async def process_alert(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        PURPOSE: Process a validated TradingView webhook alert.

        Maps the raw alert payload to the internal signal format, writes it to
        Redis (both a latest-per-symbol key and the pub/sub channel), and
        appends it to the in-memory history ring buffer.

        CALLED BY: POST /api/webhook/tradingview route handler

        Args:
            alert: Raw alert dict (already validated by TradingViewAlert Pydantic model).

        Returns:
            dict: Internal signal dict including alert_id and timestamp.
        """
        alert_id = str(uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Normalise the symbol from TradingView format to MT5 format
        raw_symbol = alert.get("symbol", "")
        symbol = self._normalize_symbol(raw_symbol)

        signal: Dict[str, Any] = {
            "source": "tradingview_webhook",
            "alert_id": alert_id,
            "symbol": symbol,
            "symbol_raw": raw_symbol,
            "direction": str(alert.get("action", "")).upper(),  # BUY or SELL
            "price": alert.get("price"),
            "contracts": alert.get("contracts"),
            "position_size": alert.get("position_size"),
            "order_id": alert.get("order_id"),
            "strategy_hint": alert.get("strategy"),
            "indicators": alert.get("indicators") or {},
            "timeframe": alert.get("timeframe"),
            "comment": alert.get("comment", ""),
            "timestamp": now_iso,
        }

        # Persist to Redis for engine pickup
        self._publish_to_redis(symbol, signal)

        # Update in-memory ring buffer and counters
        self._alert_history.appendleft(signal)
        self._total_received += 1
        self._last_alert_time = now_iso

        logger.info(
            "webhook_alert_processed",
            alert_id=alert_id,
            symbol=symbol,
            direction=signal["direction"],
            strategy_hint=signal["strategy_hint"],
        )

        return signal

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        PURPOSE: Return recent webhook alerts, newest first.

        CALLED BY: GET /api/webhook/tradingview/history

        Args:
            limit: Maximum number of alerts to return (capped at MAX_ALERT_HISTORY).

        Returns:
            list: Alert dicts in reverse-chronological order.
        """
        cap = min(limit, MAX_ALERT_HISTORY)
        return list(self._alert_history)[:cap]

    def get_status(self) -> Dict[str, Any]:
        """
        PURPOSE: Return current processor status for the dashboard.

        CALLED BY: GET /api/webhook/tradingview/status

        Returns:
            dict: {
                enabled, total_received, last_alert_time,
                redis_connected, history_count
            }
        """
        redis_ok = False
        if self._redis is not None:
            try:
                self._redis.ping()
                redis_ok = True
            except Exception:
                redis_ok = False

        return {
            "enabled": self._enabled,
            "total_received": self._total_received,
            "last_alert_time": self._last_alert_time,
            "redis_connected": redis_ok,
            "history_count": len(self._alert_history),
            "redis_channel": REDIS_CHANNEL,
        }

    # ════════════════════════════════════════════════════════════════
    # Internal Helpers
    # ════════════════════════════════════════════════════════════════

    def _normalize_symbol(self, tv_symbol: str) -> str:
        """
        PURPOSE: Convert a TradingView symbol string to MT5 format.

        Strips any exchange prefix (e.g. "BINANCE:" or "FX:") and applies
        known substitution mappings (e.g. BTCUSDT → BTCUSD).

        CALLED BY: process_alert()

        Args:
            tv_symbol: Raw symbol from TradingView (may include exchange prefix).

        Returns:
            str: Normalised MT5-compatible symbol string.

        Examples:
            "BINANCE:BTCUSDT" → "BTCUSD"
            "FX:EURUSD"       → "EURUSD"
            "XAUUSD"          → "XAUUSD"
        """
        symbol = tv_symbol.strip()

        # Strip exchange/data-provider prefix
        if ":" in symbol:
            symbol = symbol.split(":")[-1]

        # Apply known symbol mappings; fall through unchanged if not mapped
        return _TV_SYMBOL_MAP.get(symbol, symbol)

    def _publish_to_redis(self, symbol: str, signal: Dict[str, Any]) -> None:
        """
        PURPOSE: Write signal to Redis for engine consumption.

        Stores the signal under a latest-per-symbol key (with a 5-minute TTL)
        and publishes it to the shared pub/sub channel so the engine can react
        on its next cycle without polling.

        CALLED BY: process_alert()

        Args:
            symbol: Normalised MT5 symbol string.
            signal: Fully-formed internal signal dict.
        """
        if self._redis is None:
            logger.warning(
                "webhook_redis_unavailable_skipping_publish",
                symbol=symbol,
                alert_id=signal.get("alert_id"),
            )
            return

        payload = json.dumps(signal)

        try:
            # Latest-per-symbol key (engine reads this on the next cycle)
            latest_key = f"{REDIS_LATEST_KEY_PREFIX}{symbol}"
            self._redis.set(latest_key, payload, ex=REDIS_LATEST_TTL_SECONDS)

            # Pub/sub channel for real-time engine notification
            subscriber_count = self._redis.publish(REDIS_CHANNEL, payload)

            logger.info(
                "webhook_signal_published_to_redis",
                alert_id=signal.get("alert_id"),
                symbol=symbol,
                latest_key=latest_key,
                pubsub_subscribers=subscriber_count,
            )
        except Exception as e:
            logger.error(
                "webhook_redis_publish_failed",
                alert_id=signal.get("alert_id"),
                symbol=symbol,
                error=str(e),
                exception_type=type(e).__name__,
            )


# ════════════════════════════════════════════════════════════════
# Module-level singleton
# ════════════════════════════════════════════════════════════════

_processor_instance: Optional[WebhookProcessor] = None


def get_webhook_processor() -> WebhookProcessor:
    """
    PURPOSE: Return the module-level WebhookProcessor singleton.

    Creates the instance on first call; subsequent calls return the same object.
    This matches the get_brain() singleton pattern used elsewhere in the codebase.

    CALLED BY: routes_webhook.py route handlers

    Returns:
        WebhookProcessor: Singleton processor instance.
    """
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = WebhookProcessor()
    return _processor_instance
