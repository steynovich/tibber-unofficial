"""Rate limiting for API calls."""

from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, calls: int, period: float):
        """Initialize rate limiter.

        Args:
            calls: Number of calls allowed per period
            period: Time period in seconds
        """
        self.calls = calls
        self.period = period
        self.tokens: float = float(calls)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a call, waiting if necessary."""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Add tokens based on time elapsed
                tokens_to_add = elapsed * (self.calls / self.period)
                self.tokens = min(self.calls, self.tokens + tokens_to_add)
                self.last_update = now

                if self.tokens >= 1:
                    self.tokens -= 1
                    return

                # Calculate wait time until next token
                tokens_needed = 1 - self.tokens
                wait_time = (tokens_needed * self.period) / self.calls
                _LOGGER.debug("Rate limit reached, waiting %.2f seconds", wait_time)
                await asyncio.sleep(wait_time)

    def reset(self) -> None:
        """Reset the rate limiter to full capacity."""
        self.tokens = self.calls
        self.last_update = time.monotonic()


class MultiTierRateLimiter:
    """Multi-tier rate limiter for different time windows."""

    def __init__(self, storage: Any = None) -> None:
        """Initialize with Tibber API limits.

        Args:
            storage: Optional storage object for persistence
        """
        # Tibber official API: 100 calls/hour
        # We'll be conservative: 80 calls/hour, 20 calls/15min
        self.hourly = RateLimiter(80, 3600)  # 80 calls per hour
        self.burst = RateLimiter(20, 900)  # 20 calls per 15 minutes
        self._storage = storage
        self._last_save_time = time.monotonic()
        self._save_interval = 60  # Save state every minute

    async def initialize(self) -> None:
        """Load saved state from storage if available."""
        if self._storage:
            try:
                await self._storage.async_load()
                hourly_tokens, burst_tokens = self._storage.get_tokens()
                self.hourly.tokens = hourly_tokens
                self.burst.tokens = burst_tokens
                _LOGGER.debug(
                    "Restored rate limiter state: hourly=%.1f, burst=%.1f",
                    hourly_tokens,
                    burst_tokens,
                )
            except Exception as e:
                _LOGGER.warning("Failed to restore rate limiter state: %s", e)

    async def acquire(self) -> None:
        """Acquire permission from all rate limiters."""
        await self.hourly.acquire()
        await self.burst.acquire()

        # Periodically save state
        if self._storage:
            current_time = time.monotonic()
            if current_time - self._last_save_time > self._save_interval:
                await self._save_state()
                self._last_save_time = current_time

    async def _save_state(self) -> None:
        """Save current state to storage."""
        if self._storage:
            try:
                await self._storage.async_save(self.hourly.tokens, self.burst.tokens)
            except Exception as e:
                _LOGGER.debug("Failed to save rate limiter state: %s", e)

    def reset(self) -> None:
        """Reset all rate limiters."""
        self.hourly.reset()
        self.burst.reset()
