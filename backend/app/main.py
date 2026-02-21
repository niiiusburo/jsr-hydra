"""
PURPOSE: Main FastAPI application factory and lifecycle management for JSR Hydra trading system.

Initializes the FastAPI application with:
- All API routers (auth, trades, strategies, system, websocket)
- CORS middleware for development
- Exception handlers for common errors
- Startup events (EventBus connection, handler registration)
- Shutdown events (resource cleanup)
- Metadata from version.json
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter
from app.api import api_router
from app.api.routes_ws import router as ws_router, setup_ws_event_handlers
from app.config.settings import settings
from app.events.bus import get_event_bus, set_event_bus
from app.events.handlers import register_all_handlers
from app.utils.logger import setup_logging, get_logger
from app.version import get_version


logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════════
# Lifecycle Events
# ════════════════════════════════════════════════════════════════


async def on_startup() -> None:
    """
    PURPOSE: Execute startup tasks including EventBus connection and handler registration.

    CALLED BY: FastAPI lifespan startup

    Tasks:
        1. Setup logging with configured level
        2. Connect to EventBus (Redis)
        3. Register event handlers
        4. Subscribe to Redis channel
    """
    try:
        # Setup logging
        setup_logging(settings.LOG_LEVEL)
        logger.info(
            "application_startup_starting",
            version=get_version().get("version"),
            log_level=settings.LOG_LEVEL,
            dry_run=settings.DRY_RUN
        )

        # Warn about insecure default credentials in dev mode
        insecure = settings.get_insecure_defaults()
        if insecure:
            logger.warning(
                "insecure_default_credentials",
                message="Default credentials detected. Change these before deploying.",
                settings=insecure,
            )

        # Run Alembic migrations to ensure schema is up to date
        try:
            from alembic.config import Config
            from alembic import command
            alembic_cfg = Config("/app/alembic.ini")
            command.upgrade(alembic_cfg, "head")
            logger.info("alembic_upgrade_complete")
        except Exception as e:
            logger.warning("alembic_upgrade_skipped", error=str(e))

        # Connect to EventBus
        event_bus = get_event_bus()
        await event_bus.connect()
        # Store the connected instance as the global singleton so all
        # modules that call get_event_bus() share this connected bus.
        set_event_bus(event_bus)
        logger.info("event_bus_connected")

        # Register event handlers
        register_all_handlers(event_bus)
        logger.info("event_handlers_registered")

        # Register WebSocket broadcast handlers for real-time client updates
        await setup_ws_event_handlers(event_bus)
        logger.info("ws_event_handlers_registered")

        # Start Redis subscription listener as a background task so this
        # process receives events published by other processes (e.g., engine).
        asyncio.create_task(event_bus.subscribe_redis())
        logger.info("redis_subscription_started")

        # Seed default strategies so API endpoints work even without the engine
        try:
            from app.db.engine import AsyncSessionLocal
            from app.models.strategy import Strategy
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                default_rows = [
                    ("A", "Trend Following"),
                    ("B", "Mean Reversion"),
                    ("C", "Session Breakout"),
                    ("D", "Momentum Scalper"),
                    ("E", "Range Scalper (Sideways)"),
                ]
                seeded_count = 0
                for code, name in default_rows:
                    existing = await session.execute(select(Strategy).where(Strategy.code == code))
                    if existing.scalar_one_or_none():
                        continue

                    row_status = "active" if code in {"A", "B", "C", "D"} else "paused"
                    allocation_pct = 25.0 if row_status == "active" else 0.0
                    session.add(
                        Strategy(
                            code=code,
                            name=name,
                            status=row_status,
                            allocation_pct=allocation_pct,
                        )
                    )
                    seeded_count += 1

                if seeded_count > 0:
                    await session.commit()
                    logger.info("default_strategies_seeded", count=seeded_count)
        except Exception as e:
            logger.warning("strategy_seeding_failed", error=str(e))

        # Ensure a MasterAccount row exists so trade endpoints can reference it
        try:
            from app.db.engine import AsyncSessionLocal
            from app.models.account import MasterAccount
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(MasterAccount).limit(1))
                if not result.scalar_one_or_none():
                    master = MasterAccount(
                        mt5_login=settings.MT5_LOGIN or 99999,
                        broker=settings.MT5_SERVER or "Unknown",
                        status="RUNNING",
                    )
                    session.add(master)
                    await session.commit()
                    logger.info("default_master_account_seeded")
        except Exception as e:
            logger.warning("master_account_seeding_failed", error=str(e))

        logger.info("application_startup_complete")

    except Exception as e:
        logger.critical("application_startup_failed", error=str(e))
        raise


async def on_shutdown() -> None:
    """
    PURPOSE: Execute shutdown tasks to gracefully close resources.

    CALLED BY: FastAPI lifespan shutdown

    Tasks:
        1. Disconnect from EventBus
        2. Close database connections
        3. Stop background tasks
    """
    try:
        logger.info("application_shutdown_starting")

        # Disconnect from EventBus
        event_bus = get_event_bus()
        await event_bus.disconnect()
        logger.info("event_bus_disconnected")

        # TODO: Additional cleanup:
        # - Stop background retraining task
        # - Close MT5 bridge connections
        # - Flush any pending logs

        logger.info("application_shutdown_complete")

    except Exception as e:
        logger.error("application_shutdown_error", error=str(e))
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    PURPOSE: Manage application lifespan with startup and shutdown events.

    CALLED BY: FastAPI during application startup and shutdown

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    await on_startup()

    yield

    # Shutdown
    await on_shutdown()


# ════════════════════════════════════════════════════════════════
# Exception Handlers
# ════════════════════════════════════════════════════════════════


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    PURPOSE: Handle Pydantic validation errors with consistent JSON response.

    CALLED BY: FastAPI when request validation fails

    Args:
        request: HTTP request that failed validation
        exc: RequestValidationError with validation details

    Returns:
        JSONResponse: Formatted error response with validation details
    """
    logger.warning(
        "request_validation_failed",
        path=request.url.path,
        method=request.method,
        error_count=len(exc.errors())
    )

    safe_errors = jsonable_encoder(
        exc.errors(),
        custom_encoder={
            ValueError: lambda e: str(e),
            Exception: lambda e: str(e),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "detail": "Request validation failed",
            "errors": safe_errors,
        },
    )


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    PURPOSE: Handle unexpected exceptions with logging and safe error response.

    CALLED BY: FastAPI exception handler middleware

    Args:
        request: HTTP request that raised exception
        exc: Exception that was raised

    Returns:
        JSONResponse: Safe error response without exposing internals
    """
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exception_type=type(exc).__name__
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "detail": "Internal server error",
        },
    )


# ════════════════════════════════════════════════════════════════
# FastAPI Application Factory
# ════════════════════════════════════════════════════════════════


def create_app() -> FastAPI:
    """
    PURPOSE: Create and configure FastAPI application with all routers, middleware, and handlers.

    CALLED BY: Application entrypoint (uvicorn, docker, etc)

    Returns:
        FastAPI: Configured FastAPI application ready to run

    Raises:
        Exception: If version.json is not accessible
    """
    # Fail fast if non-dev config still has insecure defaults.
    # In dev mode, warnings are logged during startup instead.
    settings.validate_credentials()

    # Get version info
    try:
        version_data = get_version()
        title = "JSR Hydra"
        version = version_data.get("version", "unknown")
        description = f"Algorithmic Trading System - {version_data.get('codename', 'Hydra')}"
    except Exception as e:
        logger.warning("version_data_unavailable", error=str(e))
        title = "JSR Hydra"
        version = "unknown"
        description = "Algorithmic Trading System"

    # Create FastAPI instance
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ────────────────────────────────────────────────────────────
    # Middleware
    # ────────────────────────────────────────────────────────────

    # Rate limiting (slowapi) — must be attached before CORS so the
    # limiter state is available on the app instance for all routes.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS middleware - restricted to known frontend origins.
    #
    # H-25 CSRF note: This application uses JWT Bearer tokens sent via the
    # Authorization header (see app/api/auth.py). Browsers do NOT attach
    # custom headers automatically on cross-origin requests, so CSRF attacks
    # cannot forge authenticated requests. Explicit CSRF tokens are therefore
    # not required. CORS is tightened below as defence-in-depth.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://ai.jsralgo.com",
            "http://localhost:3000",
            "http://localhost:8000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-API-Key",
            "X-Request-ID",
        ],
    )

    # ────────────────────────────────────────────────────────────
    # Routes
    # ────────────────────────────────────────────────────────────

    # Include API routers
    app.include_router(api_router)
    app.include_router(ws_router)

    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """
        PURPOSE: Root endpoint for API availability check.

        CALLED BY: Load balancers, basic connectivity tests

        Returns:
            dict: Service information and version
        """
        return {
            "status": "ok",
            "service": "JSR Hydra API",
            "version": version,
        }

    # ────────────────────────────────────────────────────────────
    # Exception Handlers
    # ────────────────────────────────────────────────────────────

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    logger.info(
        "fastapi_application_created",
        title=title,
        version=version,
        api_prefix="/api"
    )

    return app


# Create the application
app = create_app()


if __name__ == "__main__":
    """
    PURPOSE: Run FastAPI application with Uvicorn server.

    Usage:
        python -m app.main
        OR
        uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    """
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
