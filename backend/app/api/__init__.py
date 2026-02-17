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

# Create the main API router
api_router = APIRouter(prefix="/api", tags=["api"])

# Include all sub-routers
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(trades_router, tags=["trades"])
api_router.include_router(strategies_router, tags=["strategies"])
api_router.include_router(system_router, tags=["system"])

__all__ = ["api_router"]
