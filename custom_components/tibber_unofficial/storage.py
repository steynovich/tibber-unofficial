"""Storage module for persistent data like rate limiter state."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "tibber_unofficial"


class RateLimiterStorage:
    """Persistent storage for rate limiter state."""

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """Initialize the storage."""
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry_id}.rate_limiter",
        )
        self._data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any]:
        """Load stored rate limiter state."""
        try:
            data = await self._store.async_load()
            if data:
                self._data = data
                _LOGGER.debug("Loaded rate limiter state for %s", self._entry_id)
            else:
                self._data = self._get_default_data()
                _LOGGER.debug("No stored rate limiter state, using defaults")
            return self._data
        except Exception as e:
            _LOGGER.error("Failed to load rate limiter state: %s", e)
            self._data = self._get_default_data()
            return self._data

    async def async_save(self, hourly_tokens: float, burst_tokens: float) -> None:
        """Save rate limiter state."""
        try:
            self._data = {
                "hourly_tokens": hourly_tokens,
                "burst_tokens": burst_tokens,
                "last_update": dt_util.now().isoformat(),
            }
            await self._store.async_save(self._data)
            _LOGGER.debug(
                "Saved rate limiter state: hourly=%.1f, burst=%.1f",
                hourly_tokens,
                burst_tokens,
            )
        except Exception as e:
            _LOGGER.error("Failed to save rate limiter state: %s", e)

    def _get_default_data(self) -> dict[str, Any]:
        """Get default data structure."""
        return {
            "hourly_tokens": 80.0,  # Full capacity
            "burst_tokens": 20.0,  # Full capacity
            "last_update": dt_util.now().isoformat(),
        }

    def get_tokens(self) -> tuple[float, float]:
        """Get stored token counts."""
        return (
            self._data.get("hourly_tokens", 80.0),
            self._data.get("burst_tokens", 20.0),
        )

    async def async_remove(self) -> None:
        """Remove stored data."""
        try:
            await self._store.async_remove()
            _LOGGER.debug("Removed rate limiter storage for %s", self._entry_id)
        except Exception as e:
            _LOGGER.warning("Failed to remove rate limiter storage: %s", e)
