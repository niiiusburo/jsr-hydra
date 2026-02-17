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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api import api_router
from app.api.routes_ws import router as ws_router
from app.config.settings import settings
from app.events.bus import get_event_bus
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

        # Connect to EventBus
        event_bus = get_event_bus()
        await event_bus.connect()
        logger.info("event_bus_connected")

        # TODO: Register event handlers for background tasks:
        # - Trade closed handler (calculate stats)
        # - Regime changed handler (alert frontend)
        # - Kill switch handler (emergency procedures)
        # - etc.

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

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "detail": "Request validation failed",
            "errors": exc.errors(),
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

    # CORS middleware - allow all origins in development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict to frontend URL in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
