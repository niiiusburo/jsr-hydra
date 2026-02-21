"""
PURPOSE: Settings API routes for JSR Hydra trading system.

Provides endpoints to read and update runtime trading settings such as
active trading symbols and brain/learning runtime parameters. Settings are
persisted in Redis so both API and engine processes share the same
configuration.

Authentication required for all endpoints.

CALLED BY:
    - Frontend settings panel
"""

import json
from datetime import datetime, timezone

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.config.constants import SUPPORTED_SYMBOLS
from app.config.runtime_settings import runtime_settings
from app.config.settings import settings
from app.core.rate_limit import limiter, READ_LIMIT, WRITE_LIMIT
from app.engine.engine import SYMBOL_CONFIGS, TRADING_SYMBOLS
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

TRADING_SYMBOLS_REDIS_KEY = "jsr:settings:trading_symbols"


def _get_redis():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


# ════════════════════════════════════════════════════════════════
# Trading Symbols
# ════════════════════════════════════════════════════════════════


@router.get("/trading-symbols")
@limiter.limit(READ_LIMIT)
async def get_trading_symbols(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return active trading symbols, available symbols, and per-symbol configs.

    Falls back to engine defaults (TRADING_SYMBOLS) when no Redis override exists.

    Returns:
        dict: {active_symbols, available_symbols, symbol_configs}

    CALLED BY: Frontend settings panel
    """
    try:
        r = _get_redis()
        raw = r.get(TRADING_SYMBOLS_REDIS_KEY)
        if raw:
            data = json.loads(raw)
            active_symbols = data.get("active_symbols", TRADING_SYMBOLS)
        else:
            active_symbols = list(TRADING_SYMBOLS)
        return {
            "active_symbols": active_symbols,
            "available_symbols": SUPPORTED_SYMBOLS,
            "symbol_configs": SYMBOL_CONFIGS,
        }
    except Exception as e:
        logger.error("settings_route_failed", action="retrieve trading symbols", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve trading symbols")


class TradingSymbolsUpdate(BaseModel):
    active_symbols: list[str]


@router.patch("/trading-symbols")
@limiter.limit(WRITE_LIMIT)
async def update_trading_symbols(
    request: Request,
    body: TradingSymbolsUpdate,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Update the list of actively traded symbols.

    Validates that all requested symbols are in SUPPORTED_SYMBOLS and
    persists the selection to Redis for both API and engine processes.

    Returns:
        dict: {active_symbols, available_symbols, symbol_configs}

    CALLED BY: Frontend settings panel
    """
    if not body.active_symbols:
        raise HTTPException(status_code=400, detail="At least one trading symbol must be selected")

    invalid = [s for s in body.active_symbols if s not in SUPPORTED_SYMBOLS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported symbols: {', '.join(invalid)}. Allowed: {', '.join(SUPPORTED_SYMBOLS)}",
        )

    try:
        r = _get_redis()
        payload = json.dumps({
            "active_symbols": body.active_symbols,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        r.set(TRADING_SYMBOLS_REDIS_KEY, payload)
        return {
            "active_symbols": body.active_symbols,
            "available_symbols": SUPPORTED_SYMBOLS,
            "symbol_configs": SYMBOL_CONFIGS,
        }
    except Exception as e:
        logger.error("settings_route_failed", action="update trading symbols", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update trading symbols")


# ════════════════════════════════════════════════════════════════
# Runtime Settings
# ════════════════════════════════════════════════════════════════


@router.get("/runtime")
@limiter.limit(READ_LIMIT)
async def get_runtime_settings(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return all runtime settings grouped by category.

    Settings are loaded from Redis; falls back to defaults if Redis has no
    stored values yet.

    Returns:
        dict: Settings grouped by category (learning, allocator, risk, patterns,
              exploration_decay).

    CALLED BY: Frontend settings panel
    """
    try:
        return runtime_settings.get_all()
    except Exception as e:
        logger.error("settings_route_failed", action="get runtime settings", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve runtime settings")


@router.patch("/runtime")
@limiter.limit(WRITE_LIMIT)
async def update_runtime_settings(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Update one or more runtime settings.

    Accepts a partial JSON body — only the keys present in the body are
    updated. All values are validated for type and range before being saved.

    Returns:
        dict: Updated grouped settings.

    CALLED BY: Frontend settings panel

    Raises:
        400: If any key is unknown or any value fails validation.
        500: If Redis write fails.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    try:
        runtime_settings.update(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("settings_route_failed", action="update runtime settings", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to persist runtime settings")

    try:
        return runtime_settings.get_all()
    except Exception as e:
        logger.error("settings_route_failed", action="get runtime settings after update", error=str(e))
        raise HTTPException(status_code=500, detail="Settings saved but failed to retrieve updated values")


@router.post("/runtime/reset")
@limiter.limit(WRITE_LIMIT)
async def reset_runtime_settings(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Reset all runtime settings to their factory defaults.

    Returns:
        dict: Grouped settings after reset (all at default values).

    CALLED BY: Frontend settings panel — "Reset to defaults" button
    """
    try:
        result = runtime_settings.reset_to_defaults()
        return result
    except Exception as e:
        logger.error("settings_route_failed", action="reset runtime settings", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to reset runtime settings")


@router.get("/runtime/schema")
@limiter.limit(READ_LIMIT)
async def get_runtime_settings_schema(
    request: Request,
    _current_user: str = Depends(get_current_user),
):
    """
    PURPOSE: Return the full settings schema for frontend form generation.

    Includes label, type, default, min/max or choices, and description for
    every setting, grouped by category with the ordered category list.

    Returns:
        dict: {categories: [...], settings: {category: [{key, label, ...}, ...]}}

    CALLED BY: Frontend settings panel — builds the settings form dynamically
    """
    try:
        return runtime_settings.get_schema()
    except Exception as e:
        logger.error("settings_route_failed", action="get runtime settings schema", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve settings schema")
