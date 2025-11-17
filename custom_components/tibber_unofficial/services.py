"""Services for Tibber Unofficial integration."""

import logging

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
import voluptuous as vol

from .const import COORDINATOR_REWARDS, DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH_REWARDS = "refresh_rewards"
SERVICE_CLEAR_CACHE = "clear_cache"

REFRESH_REWARDS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    },
)

CLEAR_CACHE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    },
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Tibber Unofficial integration."""

    async def async_refresh_rewards(call: ServiceCall) -> None:
        """Refresh rewards data for specified entry or all entries."""
        entry_id = call.data.get("entry_id")

        if entry_id:
            # Refresh specific entry
            if entry_id not in hass.data[DOMAIN]:
                _LOGGER.error("Entry ID %s not found", entry_id)
                return

            coordinator = hass.data[DOMAIN][entry_id].get(COORDINATOR_REWARDS)
            if coordinator:
                await coordinator.async_request_refresh()
                _LOGGER.info("Refreshed rewards data for entry %s", entry_id)
            else:
                _LOGGER.error("Rewards coordinator not found for entry %s", entry_id)
        else:
            # Refresh all entries
            refreshed_count = 0
            for _entry_id, data in hass.data[DOMAIN].items():
                if isinstance(data, dict):  # Skip non-dict entries like 'sessions'
                    coordinator = data.get(COORDINATOR_REWARDS)
                    if coordinator:
                        await coordinator.async_request_refresh()
                        refreshed_count += 1

            _LOGGER.info("Refreshed rewards data for %d entries", refreshed_count)

    async def async_clear_cache(call: ServiceCall) -> None:
        """Clear API cache for specified entry or all entries."""
        entry_id = call.data.get("entry_id")

        if entry_id:
            # Clear cache for specific entry
            if entry_id not in hass.data[DOMAIN]:
                _LOGGER.error("Entry ID %s not found", entry_id)
                return

            api_client = hass.data[DOMAIN][entry_id].get("api_client")
            if api_client and hasattr(api_client, "_cache"):
                api_client._cache.invalidate()
                _LOGGER.info("Cleared cache for entry %s", entry_id)
            else:
                _LOGGER.error("API client or cache not found for entry %s", entry_id)
        else:
            # Clear cache for all entries
            cleared_count = 0
            for _entry_id, data in hass.data[DOMAIN].items():
                if isinstance(data, dict):  # Skip non-dict entries like 'sessions'
                    api_client = data.get("api_client")
                    if api_client and hasattr(api_client, "_cache"):
                        api_client._cache.invalidate()
                        cleared_count += 1

            _LOGGER.info("Cleared cache for %d entries", cleared_count)

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_REWARDS,
        async_refresh_rewards,
        schema=REFRESH_REWARDS_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_CACHE,
        async_clear_cache,
        schema=CLEAR_CACHE_SCHEMA,
    )

    _LOGGER.debug("Registered Tibber Unofficial services")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services for Tibber Unofficial integration."""
    hass.services.async_remove(DOMAIN, SERVICE_REFRESH_REWARDS)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_CACHE)
    _LOGGER.debug("Unloaded Tibber Unofficial services")


@callback
def async_get_entity_ids(hass: HomeAssistant, entry_id: str) -> list[str]:
    """Get all entity IDs for a config entry."""
    entity_registry = er.async_get(hass)
    return [
        entity.entity_id
        for entity in er.async_entries_for_config_entry(entity_registry, entry_id)
    ]
