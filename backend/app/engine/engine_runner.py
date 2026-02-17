"""
PURPOSE: Standalone runner script for the JSR Hydra trading engine.

Entry point for starting the trading engine as a standalone service.
Handles environment setup, signal handling for graceful shutdown,
and asyncio event loop management.

CALLED BY:
    - Docker: python -m app.engine.engine_runner
    - CLI: python -m app.engine.engine_runner
"""

import asyncio
import signal
import sys
from typing import Optional

from app.config.settings import Settings
from app.engine.engine import TradingEngine
from app.utils.logger import setup_logging, get_logger

logger = get_logger("engine.runner")


class EngineRunner:
    """
    PURPOSE: Standalone runner for the trading engine.

    Manages asyncio event loop, signal handling, and graceful shutdown.
    Creates and starts the TradingEngine instance.

    Attributes:
        _engine: TradingEngine instance
        _loop: Asyncio event loop
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        PURPOSE: Initialize EngineRunner with settings.

        Args:
            settings: Optional Settings object (uses global if not provided)

        CALLED BY: main()
        """
        self._settings = settings or Settings()
        self._engine: Optional[TradingEngine] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def run(self) -> None:
        """
        PURPOSE: Start the trading engine and run indefinitely.

        Sets up signal handlers for SIGINT and SIGTERM to enable graceful shutdown.
        Starts the engine and waits for completion.

        CALLED BY: main()
        """
        try:
            logger.info(
                "engine_runner_starting",
                dry_run=self._settings.DRY_RUN,
                log_level=self._settings.LOG_LEVEL
            )

            # Create engine instance
            self._engine = TradingEngine(self._settings)

            # Register signal handlers for graceful shutdown
            self._loop = asyncio.get_event_loop()
            self._loop.add_signal_handler(
                signal.SIGINT,
                lambda: asyncio.create_task(self._handle_shutdown("SIGINT"))
            )
            self._loop.add_signal_handler(
                signal.SIGTERM,
                lambda: asyncio.create_task(self._handle_shutdown("SIGTERM"))
            )

            # Start engine (blocking until shutdown)
            await self._engine.start()

        except KeyboardInterrupt:
            logger.info("keyboard_interrupt_received")
            await self._shutdown()
        except Exception as e:
            logger.error("engine_runner_fatal_error", error=str(e))
            await self._shutdown()
            sys.exit(1)

    async def _handle_shutdown(self, signal_name: str) -> None:
        """
        PURPOSE: Handle shutdown signal and gracefully stop engine.

        Args:
            signal_name: Name of signal received (SIGINT, SIGTERM)

        CALLED BY: Signal handlers
        """
        logger.info("shutdown_signal_received", signal=signal_name)
        await self._shutdown()

    async def _shutdown(self) -> None:
        """
        PURPOSE: Perform graceful shutdown of engine.

        Stops the engine and exits the process.

        CALLED BY: _handle_shutdown(), run() exception handlers
        """
        try:
            if self._engine:
                await self._engine.stop()
            logger.info("engine_runner_shutdown_complete")
        except Exception as e:
            logger.error("shutdown_error", error=str(e))
        finally:
            sys.exit(0)


def main() -> None:
    """
    PURPOSE: Main entry point for the engine runner.

    Initializes logging, loads settings from .env, creates EngineRunner,
    and starts the trading engine.

    CALLED BY:
        - docker-compose (entrypoint)
        - python -m app.engine.engine_runner
    """
    try:
        # Load settings from .env
        settings = Settings()

        # Setup logging
        setup_logging(log_level=settings.LOG_LEVEL)

        logger.info(
            "engine_runner_initialized",
            version="1.0.0",
            codename="Hydra",
            environment="production" if not settings.DRY_RUN else "dry-run"
        )

        # Create and run engine
        runner = EngineRunner(settings)

        # Run asyncio event loop
        asyncio.run(runner.run())

    except Exception as e:
        logger.error("engine_runner_startup_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
