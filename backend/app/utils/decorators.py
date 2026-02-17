"""
PURPOSE: Decorators for retry logic, execution timing, and circuit breaker pattern.
Provides resilience patterns for API calls and external service interactions.
"""

import functools
import time
import asyncio
import threading
from typing import Callable, Optional, Tuple, Any

from app.utils.logger import get_logger

logger = get_logger(__name__)


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,)
) -> Callable:
    """
    PURPOSE: Retry decorator with exponential backoff for both sync and async functions.
    Automatically retries on specified exceptions up to max_retries times.

    Args:
        max_retries: Maximum number of retry attempts (default 3).
        delay: Initial delay between retries in seconds (default 1.0).
        backoff: Exponential backoff multiplier (default 2.0).
        exceptions: Tuple of exception types to catch and retry on (default (Exception,)).

    Returns:
        Callable: Decorated function with retry logic.
    """
    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                current_delay = delay
                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_retries:
                            logger.info(
                                f"Retry attempt {attempt + 1}/{max_retries}",
                                function=func.__name__,
                                delay=current_delay,
                                error=str(e)
                            )
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            logger.error(
                                f"Max retries exceeded for {func.__name__}",
                                function=func.__name__,
                                error=str(e)
                            )

                raise last_exception

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                current_delay = delay
                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_retries:
                            logger.info(
                                f"Retry attempt {attempt + 1}/{max_retries}",
                                function=func.__name__,
                                delay=current_delay,
                                error=str(e)
                            )
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            logger.error(
                                f"Max retries exceeded for {func.__name__}",
                                function=func.__name__,
                                error=str(e)
                            )

                raise last_exception

            return sync_wrapper

    return decorator


def timed(logger_name: str = "default") -> Callable:
    """
    PURPOSE: Timing decorator that logs function execution time in milliseconds.
    Works for both sync and async functions.

    Args:
        logger_name: Logger name for output (default "default").

    Returns:
        Callable: Decorated function with execution timing.
    """
    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    elapsed_ms = (time.time() - start_time) * 1000
                    logger.info(
                        f"{func.__name__} executed",
                        function=func.__name__,
                        elapsed_ms=f"{elapsed_ms:.2f}"
                    )

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    elapsed_ms = (time.time() - start_time) * 1000
                    logger.info(
                        f"{func.__name__} executed",
                        function=func.__name__,
                        elapsed_ms=f"{elapsed_ms:.2f}"
                    )

            return sync_wrapper

    return decorator


class CircuitBreakerOpen(Exception):
    """
    PURPOSE: Exception raised when circuit breaker is in OPEN state.
    Indicates that the resource is temporarily unavailable.
    """
    pass


class CircuitBreaker:
    """
    PURPOSE: Circuit breaker pattern implementation for handling failures.
    Transitions between CLOSED, OPEN, and HALF_OPEN states to prevent cascading failures.
    Thread-safe with internal locking.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0):
        """
        PURPOSE: Initialize circuit breaker with failure threshold and reset timeout.

        Args:
            failure_threshold: Number of consecutive failures before opening (default 5).
            reset_timeout: Seconds to wait before attempting reset (default 60.0).
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = self.CLOSED
        self._lock = threading.Lock()
        self.logger = get_logger(__name__)

    def __call__(self, func: Callable) -> Callable:
        """
        PURPOSE: Make CircuitBreaker usable as a decorator.

        Args:
            func: Function to decorate.

        Returns:
            Callable: Decorated function with circuit breaker logic.
        """
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                return await self._execute_async(func, args, kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                return self._execute(func, args, kwargs)
            return sync_wrapper

    def _execute(self, func: Callable, args: Tuple, kwargs: dict) -> Any:
        """
        PURPOSE: Execute function with circuit breaker protection (sync).

        Args:
            func: Function to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Any: Function result.

        Raises:
            CircuitBreakerOpen: If circuit is OPEN and reset timeout not elapsed.
        """
        with self._lock:
            if self.state == self.OPEN:
                if self._should_attempt_reset():
                    self.state = self.HALF_OPEN
                    self.logger.info(
                        "Circuit breaker entering HALF_OPEN",
                        function=func.__name__
                    )
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker OPEN for {func.__name__}"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(func.__name__)
            raise

    async def _execute_async(self, func: Callable, args: Tuple, kwargs: dict) -> Any:
        """
        PURPOSE: Execute async function with circuit breaker protection.

        Args:
            func: Async function to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Any: Function result.

        Raises:
            CircuitBreakerOpen: If circuit is OPEN and reset timeout not elapsed.
        """
        with self._lock:
            if self.state == self.OPEN:
                if self._should_attempt_reset():
                    self.state = self.HALF_OPEN
                    self.logger.info(
                        "Circuit breaker entering HALF_OPEN",
                        function=func.__name__
                    )
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker OPEN for {func.__name__}"
                    )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(func.__name__)
            raise

    def _should_attempt_reset(self) -> bool:
        """
        PURPOSE: Check if enough time has elapsed to attempt reset from OPEN state.

        Returns:
            bool: True if reset timeout has elapsed, False otherwise.
        """
        if self.last_failure_time is None:
            return False

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.reset_timeout

    def _on_success(self) -> None:
        """
        PURPOSE: Handle successful function execution.
        Resets failure count and transitions HALF_OPEN -> CLOSED.
        """
        with self._lock:
            self.failure_count = 0
            if self.state == self.HALF_OPEN:
                self.state = self.CLOSED
                self.logger.info("Circuit breaker reset to CLOSED")

    def _on_failure(self, func_name: str) -> None:
        """
        PURPOSE: Handle function execution failure.
        Increments failure count and transitions to OPEN if threshold reached.

        Args:
            func_name: Name of the function that failed.
        """
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                self.logger.error(
                    "Circuit breaker opened",
                    function=func_name,
                    failure_count=self.failure_count
                )
            elif self.state == self.HALF_OPEN:
                self.state = self.OPEN
                self.logger.error(
                    "Circuit breaker reopened from HALF_OPEN",
                    function=func_name
                )
