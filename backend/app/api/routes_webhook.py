"""
PURPOSE: TradingView webhook API routes for JSR Hydra trading system.

Provides a public inbound endpoint for TradingView Pine Script alert webhooks
and authenticated endpoints for history, status, and test firing.

The POST /tradingview endpoint is intentionally PUBLIC (no JWT) — TradingView
cannot attach JWT tokens to its outbound webhook calls. Instead, the endpoint
is protected by a shared secret validated from either the X-Webhook-Secret
request header or a "secret" field in the JSON body.

CALLED BY:
    - TradingView Premium alert webhooks (POST, public)
    - Frontend dashboard (GET history / status, JWT-protected)
"""

from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.rate_limit import limiter, READ_LIMIT, WRITE_LIMIT
from app.utils.logger import get_logger
from app.webhook.processor import get_webhook_processor

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Rate limit for the public inbound webhook endpoint
WEBHOOK_LIMIT = "30/minute"


# ════════════════════════════════════════════════════════════════
# Pydantic Models
# ════════════════════════════════════════════════════════════════


class TradingViewAlert(BaseModel):
    """
    PURPOSE: Pydantic model for a TradingView Pine Script webhook alert payload.

    TradingView sends a JSON body when an alert fires. All fields except
    `action` and `symbol` are optional so that users can send minimal payloads
    from simple Pine Script strategies.

    Attributes:
        action:        "buy" or "sell" — maps to internal BUY / SELL direction.
        symbol:        Instrument symbol as sent by TradingView (may include
                       exchange prefix, e.g. "BINANCE:BTCUSDT" or "FX:EURUSD").
        price:         Current price at the time of alert (optional).
        contracts:     Number of contracts/lots suggested by the strategy.
        order_id:      Optional order identifier from the Pine Script strategy.
        position_size: Suggested position size (optional, overrides contracts).
        comment:       Free-text comment attached to the alert.
        strategy:      JSR strategy code hint ("A" through "E") — optional.
        indicators:    Dict of indicator values at alert time
                       (e.g. {"sma44": 67500, "rsi": 45, "ema20": 67800}).
        timeframe:     Chart timeframe string (e.g. "1H", "4H", "1D").
        secret:        Alternative to the X-Webhook-Secret header for auth
                       when the caller cannot set custom headers.
    """

    action: str
    symbol: str
    price: Optional[float] = None
    contracts: Optional[float] = None
    order_id: Optional[str] = None
    position_size: Optional[float] = None
    comment: Optional[str] = ""
    strategy: Optional[str] = None
    indicators: Optional[Dict[str, Any]] = None
    timeframe: Optional[str] = None
    secret: Optional[str] = None


# ════════════════════════════════════════════════════════════════
# Internal Helpers
# ════════════════════════════════════════════════════════════════


def _validate_webhook_secret(
    body_secret: Optional[str],
    header_secret: Optional[str],
) -> None:
    """
    PURPOSE: Validate that the inbound webhook request carries the correct shared secret.

    Checks the X-Webhook-Secret header first; falls back to the `secret` field
    in the JSON body. Raises HTTP 401 if neither matches the configured secret.

    CALLED BY: tradingview_webhook route handler

    Args:
        body_secret:   Value of the `secret` field in the parsed JSON body.
        header_secret: Value of the X-Webhook-Secret HTTP header.

    Raises:
        HTTPException: 401 if neither secret value matches the configured one.
    """
    configured_secret = settings.TRADINGVIEW_WEBHOOK_SECRET

    provided = header_secret or body_secret
    if not provided or provided != configured_secret:
        logger.warning(
            "webhook_auth_failed",
            has_header=bool(header_secret),
            has_body_secret=bool(body_secret),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook secret",
        )


def _raise_webhook_route_error(action: str, error: Exception) -> None:
    """
    PURPOSE: Raise a consistent HTTP 500 response for webhook route failures.

    Logs the failure with structlog before raising so the error appears in the
    structured log stream alongside the action context.

    CALLED BY: Route handlers on unexpected exceptions

    Args:
        action: Human-readable description of the failed operation.
        error:  The caught exception.

    Raises:
        HTTPException: Always raises HTTP 500.
    """
    logger.error(
        "webhook_route_failed",
        action=action,
        error=str(error),
        exception_type=type(error).__name__,
    )
    raise HTTPException(
        status_code=500,
        detail=f"Failed to {action}",
    )


# ════════════════════════════════════════════════════════════════
# Public Inbound Endpoint
# ════════════════════════════════════════════════════════════════


@router.post("/tradingview")
@limiter.limit(WEBHOOK_LIMIT)
async def tradingview_webhook(
    request: Request,
    alert: TradingViewAlert,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
) -> Dict[str, Any]:
    """
    PURPOSE: Receive a TradingView Pine Script alert webhook and queue it for the engine.

    This endpoint is PUBLIC — no JWT authentication is required. TradingView
    Premium cannot attach JWT tokens to outbound webhooks. Authentication is
    instead provided via a shared secret in either:
      - The X-Webhook-Secret request header, OR
      - The `secret` field in the JSON body.

    On receipt the alert is:
      1. Secret-validated (HTTP 401 on failure).
      2. Logged via structlog.
      3. Processed by WebhookProcessor (normalised, Redis-published, history-stored).
      4. Acknowledged with a unique alert_id.

    Rate limit: 30 requests/minute per IP address.

    Args:
        request:          FastAPI Request (required by slowapi rate limiter).
        alert:            Parsed TradingViewAlert body.
        x_webhook_secret: Value of the X-Webhook-Secret header (optional).

    Returns:
        dict: {"status": "received", "alert_id": "<uuid>"}

    Raises:
        HTTP 401: Invalid or missing webhook secret.
        HTTP 422: Malformed JSON body (FastAPI built-in).
        HTTP 429: Rate limit exceeded.
        HTTP 500: Internal processing failure.
    """
    # Auth: header takes precedence over body field
    _validate_webhook_secret(
        body_secret=alert.secret,
        header_secret=x_webhook_secret,
    )

    logger.info(
        "webhook_alert_received",
        symbol=alert.symbol,
        action=alert.action,
        strategy=alert.strategy,
        timeframe=alert.timeframe,
        has_indicators=bool(alert.indicators),
    )

    try:
        processor = get_webhook_processor()
        signal = await processor.process_alert(alert.model_dump(exclude={"secret"}))
        return {"status": "received", "alert_id": signal["alert_id"]}
    except HTTPException:
        raise
    except Exception as e:
        _raise_webhook_route_error("process TradingView alert", e)


# ════════════════════════════════════════════════════════════════
# Authenticated Read Endpoints
# ════════════════════════════════════════════════════════════════


@router.get("/tradingview/history")
@limiter.limit(READ_LIMIT)
async def get_webhook_history(
    request: Request,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Return the last 50 TradingView webhook alerts received.

    Pulls from the in-memory ring buffer maintained by WebhookProcessor.
    Newest alerts appear first.

    Returns:
        dict: {alerts: [...], count: int, total_received: int}

    CALLED BY: Frontend dashboard — webhook history panel.

    Raises:
        HTTP 401: Missing or invalid JWT token.
        HTTP 500: Unexpected error.
    """
    try:
        processor = get_webhook_processor()
        alerts = processor.get_history(limit=50)
        status_info = processor.get_status()
        return {
            "alerts": alerts,
            "count": len(alerts),
            "total_received": status_info["total_received"],
        }
    except Exception as e:
        _raise_webhook_route_error("retrieve webhook history", e)


@router.get("/tradingview/status")
@limiter.limit(READ_LIMIT)
async def get_webhook_status(
    request: Request,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Return TradingView webhook endpoint status and configuration hint.

    Provides the dashboard with operational state: whether the processor is
    enabled, how many alerts have been received, the timestamp of the most
    recent alert, and the URL users should configure in TradingView.

    Returns:
        dict: {
            enabled, total_received, last_alert_time,
            redis_connected, history_count, redis_channel,
            webhook_url_hint
        }

    CALLED BY: Frontend dashboard — webhook status card.

    Raises:
        HTTP 401: Missing or invalid JWT token.
        HTTP 500: Unexpected error.
    """
    try:
        processor = get_webhook_processor()
        status_data = processor.get_status()
        status_data["webhook_url_hint"] = "/api/webhook/tradingview"
        return status_data
    except Exception as e:
        _raise_webhook_route_error("retrieve webhook status", e)


# ════════════════════════════════════════════════════════════════
# Authenticated Test Endpoint
# ════════════════════════════════════════════════════════════════


@router.post("/tradingview/test")
@limiter.limit(WRITE_LIMIT)
async def test_webhook(
    request: Request,
    _current_user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    PURPOSE: Fire a synthetic test alert through the full webhook processing pipeline.

    Generates a dummy TradingView alert (BUY EURUSD) and passes it through
    WebhookProcessor so the user can verify that Redis is reachable and the
    pipeline is functioning end-to-end without requiring an actual TradingView
    alert to fire.

    Returns:
        dict: {
            status: "test_alert_sent",
            alert_id: str,
            signal: dict (full processed signal)
        }

    CALLED BY: Frontend dashboard — "Send Test Alert" button.

    Raises:
        HTTP 401: Missing or invalid JWT token.
        HTTP 500: Unexpected processing failure.
    """
    test_alert = {
        "action": "buy",
        "symbol": "EURUSD",
        "price": 1.08500,
        "contracts": 0.01,
        "comment": "Test alert from JSR Hydra dashboard",
        "strategy": "A",
        "indicators": {"test": True},
        "timeframe": "1H",
        "order_id": f"TEST-{str(uuid4())[:8].upper()}",
    }

    logger.info(
        "webhook_test_alert_fired",
        user=_current_user,
        symbol=test_alert["symbol"],
    )

    try:
        processor = get_webhook_processor()
        signal = await processor.process_alert(test_alert)
        return {
            "status": "test_alert_sent",
            "alert_id": signal["alert_id"],
            "signal": signal,
        }
    except Exception as e:
        _raise_webhook_route_error("send test webhook alert", e)
