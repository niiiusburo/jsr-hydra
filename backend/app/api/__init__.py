"""
PURPOSE: API router initialization and exports for JSR Hydra.

This module aggregates all API routers (auth, trades, strategies, system, websocket)
into a single api_router that is included in the main FastAPI application.
"""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.routes_trades import router as trades_router
from app.api.routes_strategies import router as strategies_router
from app.api.routes_system import router as system_router
from app.api.routes_brain import router as brain_router
from app.api.routes_settings import router as settings_router
from app.api.routes_webhook import router as webhook_router
from app.api.routes_chart_vision import router as chart_vision_router
from app.api.routes_strategy_builder import router as strategy_builder_router

# Create the main API router
api_router = APIRouter(prefix="/api", tags=["api"])

# Include all sub-routers
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(trades_router, tags=["trades"])
api_router.include_router(strategies_router, tags=["strategies"])
api_router.include_router(system_router, tags=["system"])
api_router.include_router(brain_router, tags=["brain"])
api_router.include_router(settings_router, tags=["settings"])
api_router.include_router(webhook_router, tags=["webhook"])
api_router.include_router(chart_vision_router, tags=["chart-vision"])
api_router.include_router(strategy_builder_router, tags=["strategy-builder"])

__all__ = ["api_router"]
