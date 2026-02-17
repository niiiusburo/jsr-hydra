"""
PURPOSE: Standalone seed data runner script for JSR Hydra.

Provides a CLI entry point to run database seeding operations.
Can be executed directly or called from other initialization scripts.

Usage:
    python -m app.db.seed_runner
"""

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import AsyncSessionLocal
from app.db.seed import seed_database
from structlog import get_logger

logger = get_logger(__name__)


async def run_seed() -> None:
    """
    PURPOSE: Execute database seeding with proper session management.

    Creates an async database session and runs the seed_database function.
    Handles cleanup and error logging.
    """
    async with AsyncSessionLocal() as session:
        try:
            logger.info("Starting database seeding")
            await seed_database(session)
            logger.info("Database seeding completed")
        except Exception as e:
            logger.error("Database seeding failed", error=str(e), exc_info=True)
            raise


def main() -> None:
    """
    PURPOSE: CLI entry point for seed runner.

    Runs the async seed function using asyncio.run().
    """
    try:
        asyncio.run(run_seed())
    except Exception as e:
        logger.error("Seed runner failed", error=str(e))
        exit(1)


if __name__ == "__main__":
    main()
