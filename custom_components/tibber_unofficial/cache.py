"""Caching module for Tibber Unofficial integration."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import logging
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)


class ApiCache:
    """Cache for API responses to reduce unnecessary calls."""

    def __init__(self, default_ttl: int = 300):
        """Initialize cache with default TTL in seconds.

        Args:
            default_ttl: Default time-to-live for cache entries in seconds
        """
        self._cache: dict[
            str,
            tuple[Any, float, float],
        ] = {}  # key -> (data, expiry_time, cached_at)
        self._default_ttl = default_ttl
        self._hit_count = 0
        self._miss_count = 0
        _LOGGER.debug("Cache initialized with default TTL: %d seconds", default_ttl)

    def _make_key(self, method: str, **kwargs: Any) -> str:
        """Create a cache key from method name and arguments."""
        # Sort kwargs for consistent key generation
        sorted_kwargs = sorted(kwargs.items())
        key_data = f"{method}:{json.dumps(sorted_kwargs, sort_keys=True, default=str)}"
        # Use SHA256 for better collision resistance
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, method: str, **kwargs: Any) -> Any | None:
        """Get cached data if available and not expired.

        Args:
            method: The API method name
            **kwargs: Method arguments

        Returns:
            Cached data if available and valid, None otherwise
        """
        key = self._make_key(method, **kwargs)

        if key in self._cache:
            data, expiry_time, cached_at = self._cache[key]
            current_time = time.time()

            if current_time < expiry_time:
                self._hit_count += 1
                age = current_time - cached_at
                _LOGGER.debug(
                    "Cache HIT for %s (age: %.1fs, expires in: %.1fs)",
                    method,
                    age,
                    expiry_time - current_time,
                )
                return data

            # Expired entry - remove it
            del self._cache[key]
            _LOGGER.debug("Cache expired for %s", method)

        self._miss_count += 1
        _LOGGER.debug("Cache MISS for %s", method)
        return None

    def set(
        self, method: str, data: Any, ttl: int | None = None, **kwargs: Any
    ) -> None:
        """Store data in cache.

        Args:
            method: The API method name
            data: Data to cache
            ttl: Optional TTL in seconds (uses default if not specified)
            **kwargs: Method arguments
        """
        key = self._make_key(method, **kwargs)
        ttl = ttl if ttl is not None else self._default_ttl
        current_time = time.time()
        expiry_time = current_time + ttl

        self._cache[key] = (data, expiry_time, current_time)
        _LOGGER.debug("Cached %s for %d seconds", method, ttl)

    def invalidate(self, method: str | None = None, **kwargs: Any) -> None:
        """Invalidate cache entries.

        Args:
            method: If specified, invalidate only entries for this method
            **kwargs: If specified with method, invalidate specific entry
        """
        if method is None:
            # Clear entire cache
            count = len(self._cache)
            self._cache.clear()
            _LOGGER.info("Cache cleared (%d entries removed)", count)
        elif kwargs:
            # Clear specific entry
            key = self._make_key(method, **kwargs)
            if key in self._cache:
                del self._cache[key]
                _LOGGER.debug("Invalidated cache for %s with specific args", method)
        else:
            # Clear all entries for a method - delete while iterating safely
            for key in list(self._cache.keys()):
                del self._cache[key]

            if self._cache:
                _LOGGER.debug("Invalidated cache entries for %s", method)

    def cleanup(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = []

        for key, (_, expiry_time, _) in self._cache.items():
            if current_time >= expiry_time:
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            _LOGGER.debug("Cleaned up %d expired cache entries", len(expired_keys))

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._cache),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
        }

    def __str__(self) -> str:
        """String representation of cache stats."""
        stats = self.get_stats()
        return f"Cache: {stats['entries']} entries, {stats['hit_rate']:.1f}% hit rate ({stats['hits']}/{stats['total_requests']})"


class SmartCache(ApiCache):
    """Smart cache with adaptive TTL based on data patterns."""

    def __init__(self) -> None:
        """Initialize smart cache with context-aware TTLs."""
        super().__init__(default_ttl=300)

        # Define TTLs for different data types (in seconds)
        self.ttl_config = {
            "homes": 3600,  # 1 hour - homes rarely change
            "gizmos": 1800,  # 30 minutes - devices change occasionally
            "auth": 3300,  # 55 minutes - token valid for 1 hour
            "rewards_daily": 300,  # 5 minutes - current day data
            "rewards_monthly": 900,  # 15 minutes - current month data
            "rewards_historical": 3600,  # 1 hour - historical data doesn't change
        }

    def set_smart(self, method: str, data: Any, data_type: str, **kwargs: Any) -> None:
        """Store data with intelligent TTL based on data type.

        Args:
            method: The API method name
            data: Data to cache
            data_type: Type of data for TTL selection
            **kwargs: Method arguments
        """
        ttl = self.ttl_config.get(data_type, self._default_ttl)

        # Adaptive TTL based on time patterns
        if data_type == "rewards_daily":
            # Cache for shorter time near end of day (when rewards might update)
            now = datetime.now(UTC)
            hours_until_midnight = 24 - now.hour
            if hours_until_midnight <= 2:
                ttl = 60  # 1 minute cache near midnight
        elif data_type == "rewards_monthly":
            # Cache for shorter time near end of month
            now = datetime.now(UTC)
            days_in_month = 31  # Approximate
            if now.day >= days_in_month - 2:
                ttl = 300  # 5 minute cache near month end

        self.set(method, data, ttl, **kwargs)
        _LOGGER.debug(
            "Smart cached %s as %s type for %d seconds",
            method,
            data_type,
            ttl,
        )
