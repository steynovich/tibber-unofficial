"""Diagnostics support for Tibber Unofficial integration."""

import logging
from typing import Dict, Any
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN, COORDINATOR_REWARDS, COORDINATOR_GIZMOS

_LOGGER = logging.getLogger(__name__)

# Data to redact for privacy
TO_REDACT = {
    "email",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "home_id",
    "gizmo_id",
    "user_id",
    "account_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    # Get coordinator data
    rewards_coordinator = data.get(COORDINATOR_REWARDS)
    gizmos_coordinator = data.get(COORDINATOR_GIZMOS)
    api_client = data.get("api_client")

    diagnostics_data: Dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "domain": entry.domain,
            "state": entry.state.value,
            "options": dict(entry.options),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "coordinators": {},
        "api_client": {},
        "system_info": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ha_version": hass.config.version,
            "integration_version": entry.version,
        },
        "entities": [],
        "devices": [],
    }

    # Add rewards coordinator diagnostics
    if rewards_coordinator:
        diagnostics_data["coordinators"]["rewards"] = {
            "last_update_success": rewards_coordinator.last_update_success,
            "last_exception": str(rewards_coordinator.last_exception)
            if rewards_coordinator.last_exception
            else None,
            "update_interval": str(rewards_coordinator.update_interval),
            "last_update_time": rewards_coordinator.last_update_success_time.isoformat()
            if rewards_coordinator.last_update_success_time
            else None,
            "data_keys": list(rewards_coordinator.data.keys())
            if rewards_coordinator.data
            else [],
            "home_id_redacted": async_redact_data(
                {"home_id": rewards_coordinator.home_id}, TO_REDACT
            )["home_id"],
        }

    # Add gizmos coordinator diagnostics
    if gizmos_coordinator:
        diagnostics_data["coordinators"]["gizmos"] = {
            "last_update_success": gizmos_coordinator.last_update_success,
            "last_exception": str(gizmos_coordinator.last_exception)
            if gizmos_coordinator.last_exception
            else None,
            "update_interval": str(gizmos_coordinator.update_interval),
            "last_update_time": gizmos_coordinator.last_update_success_time.isoformat()
            if gizmos_coordinator.last_update_success_time
            else None,
            "data_keys": list(gizmos_coordinator.data.keys())
            if gizmos_coordinator.data
            else [],
            "home_id_redacted": async_redact_data(
                {"home_id": gizmos_coordinator.home_id}, TO_REDACT
            )["home_id"],
        }

    # Add API client diagnostics
    if api_client:
        diagnostics_data["api_client"] = {
            "initialized": getattr(api_client, "_initialized", False),
            "has_token": bool(getattr(api_client, "_token", None)),
            "token_expires": (
                expiry_time.isoformat()
                if (expiry_time := getattr(api_client, "_token_expiry_time", None)) is not None
                else None
            ),
            "cache_stats": api_client.get_cache_stats()
            if hasattr(api_client, "get_cache_stats")
            else {},
            "rate_limiter_stats": {
                "hourly_tokens": getattr(
                    api_client._rate_limiter.hourly, "tokens", None
                ),
                "burst_tokens": getattr(api_client._rate_limiter.burst, "tokens", None),
            }
            if hasattr(api_client, "_rate_limiter")
            else {},
        }

    # Add entity diagnostics
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    device_registry = hass.helpers.device_registry.async_get(hass)

    entities = hass.helpers.entity_registry.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    )

    for entity in entities:
        entity_data = {
            "entity_id": entity.entity_id,
            "unique_id": async_redact_data({"uid": entity.unique_id}, TO_REDACT)["uid"],
            "platform": entity.platform,
            "device_class": entity.device_class,
            "unit_of_measurement": entity.unit_of_measurement,
            "enabled": not entity.disabled,
            "disabled_by": entity.disabled_by.value if entity.disabled_by else None,
        }

        # Get entity state
        state = hass.states.get(entity.entity_id)
        if state:
            entity_data["state"] = {
                "state": state.state,
                "attributes": async_redact_data(dict(state.attributes), TO_REDACT),
                "last_changed": state.last_changed.isoformat(),
                "last_updated": state.last_updated.isoformat(),
            }

        diagnostics_data["entities"].append(entity_data)

    # Add device diagnostics
    devices = hass.helpers.device_registry.async_entries_for_config_entry(
        device_registry, entry.entry_id
    )

    for device in devices:
        device_data = {
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
            "hw_version": device.hw_version,
            "identifiers": async_redact_data(
                {"ids": list(device.identifiers)}, TO_REDACT
            )["ids"],
            "connections": list(device.connections),
            "disabled": device.disabled,
            "disabled_by": device.disabled_by.value if device.disabled_by else None,
        }
        diagnostics_data["devices"].append(device_data)

    return diagnostics_data


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> Dict[str, Any]:
    """Return diagnostics for a device entry."""
    data = await async_get_config_entry_diagnostics(hass, entry)

    # Filter to only this device
    device_data = None
    for dev in data.get("devices", []):
        if any(
            identifier in device.identifiers
            for identifier in dev.get("identifiers", [])
        ):
            device_data = dev
            break

    # Filter entities to only those for this device
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    device_entities = hass.helpers.entity_registry.async_entries_for_device(
        entity_registry, device.id
    )

    filtered_entities = []
    for entity in data.get("entities", []):
        if any(e.entity_id == entity["entity_id"] for e in device_entities):
            filtered_entities.append(entity)

    return {
        "device": device_data,
        "entities": filtered_entities,
        "system_info": data["system_info"],
    }
