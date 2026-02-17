"""
PURPOSE: Structured logging configuration and logger factory for the trading system.
Uses structlog for JSON-formatted logs with automatic context binding.
"""

import structlog
from typing import Optional


def setup_logging(log_level: str = "INFO") -> None:
    """
    PURPOSE: Configure structlog with JSON output format, including timestamp, level, module, and event.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Defaults to "INFO".
    """
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(module_name: str) -> structlog.BoundLogger:
    """
    PURPOSE: Return a bound logger with module context for structured logging.

    Args:
        module_name: The name of the module requesting the logger (e.g., "__name__").

    Returns:
        structlog.BoundLogger: Logger instance with module context bound.
    """
    return structlog.get_logger().bind(module=module_name)
