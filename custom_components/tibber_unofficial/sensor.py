"""Sensor platform for Tibber Unofficial."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import GridRewardsCoordinator
from .const import (
    ATTR_DATA_PERIOD_FROM,
    ATTR_DATA_PERIOD_TO,
    ATTR_LAST_UPDATED,
    COORDINATOR_REWARDS,
    DOMAIN,
    GRID_REWARDS_EV_CURRENT_DAY,
    GRID_REWARDS_EV_CURRENT_MONTH,
    GRID_REWARDS_EV_PREVIOUS_MONTH,
    GRID_REWARDS_EV_YEAR,
    GRID_REWARDS_HOMEVOLT_CURRENT_DAY,
    GRID_REWARDS_HOMEVOLT_CURRENT_MONTH,
    GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH,
    GRID_REWARDS_HOMEVOLT_YEAR,
    GRID_REWARDS_TOTAL_CURRENT_DAY,
    GRID_REWARDS_TOTAL_CURRENT_MONTH,
    GRID_REWARDS_TOTAL_PREVIOUS_MONTH,
    GRID_REWARDS_TOTAL_YEAR,
    KEY_CURRENCY,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_DEFINITIONS = [
    (
        GRID_REWARDS_EV_CURRENT_DAY,
        "EV - Month to Date",
        "mdi:car-electric",
        "current_day_from",
        "current_day_to",
    ),
    (
        GRID_REWARDS_EV_CURRENT_MONTH,
        "EV - Current Month",
        "mdi:car-electric",
        "current_month_from",
        "current_month_to",
    ),
    (
        GRID_REWARDS_EV_PREVIOUS_MONTH,
        "EV - Previous Month",
        "mdi:car-electric",
        "previous_month_from",
        "previous_month_to",
    ),
    (GRID_REWARDS_EV_YEAR, "EV - Year", "mdi:car-electric", "year_from", "year_to"),
    (
        GRID_REWARDS_HOMEVOLT_CURRENT_DAY,
        "Homevolt - Month to Date",
        "mdi:home-battery",
        "current_day_from",
        "current_day_to",
    ),
    (
        GRID_REWARDS_HOMEVOLT_CURRENT_MONTH,
        "Homevolt - Current Month",
        "mdi:home-battery",
        "current_month_from",
        "current_month_to",
    ),
    (
        GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH,
        "Homevolt - Previous Month",
        "mdi:home-battery",
        "previous_month_from",
        "previous_month_to",
    ),
    (
        GRID_REWARDS_HOMEVOLT_YEAR,
        "Homevolt - Year",
        "mdi:home-battery",
        "year_from",
        "year_to",
    ),
    (
        GRID_REWARDS_TOTAL_CURRENT_DAY,
        "Total - Month to Date",
        "mdi:cash-multiple",
        "current_day_from",
        "current_day_to",
    ),
    (
        GRID_REWARDS_TOTAL_CURRENT_MONTH,
        "Total - Current Month",
        "mdi:cash-multiple",
        "current_month_from",
        "current_month_to",
    ),
    (
        GRID_REWARDS_TOTAL_PREVIOUS_MONTH,
        "Total - Previous Month",
        "mdi:cash-multiple",
        "previous_month_from",
        "previous_month_to",
    ),
    (
        GRID_REWARDS_TOTAL_YEAR,
        "Total - Year",
        "mdi:cash-multiple",
        "year_from",
        "year_to",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    rewards_coordinator: GridRewardsCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR_REWARDS
    ]

    entities = []
    # Check initial data from the coordinator to decide if sensors should be enabled by default
    initial_rewards_data = (
        rewards_coordinator.data if rewards_coordinator.last_update_success else {}
    )

    for (
        data_key,
        name_suffix,
        icon,
        period_from_key,
        period_to_key,
    ) in SENSOR_DEFINITIONS:
        # If the specific data_key is None in the initial data, disable the sensor by default.
        # This applies mainly to EV and Homevolt sensors if the user doesn't have those reward types.
        # Total sensors are usually always relevant if any reward data exists.
        initially_available = True  # Default to true
        if initial_rewards_data is None or initial_rewards_data.get(data_key) is None:
            # For EV or Homevolt specific sensors, if their data is None initially, disable them.
            initially_available = False
            _LOGGER.info(
                "Sensor for key '%s' (%s) will be disabled by default as no initial data was found.",
                data_key,
                name_suffix,
            )

        # However, for "Total" sensors, we might always want them enabled if the coordinator itself has data,
        if "total" in data_key.lower():  # If it's a total sensor
            initially_available = True  # Always enable total sensors by default if coordinator has any data
            if (
                initial_rewards_data is None
                or initial_rewards_data.get(data_key) is None
            ):
                _LOGGER.debug(
                    "Total sensor %s has no initial data, but will be enabled by default.",
                    name_suffix,
                )

        entities.append(
            GridRewardComponentSensor(
                coordinator=rewards_coordinator,
                config_entry_id=entry.entry_id,
                data_key=data_key,
                name_suffix=name_suffix,
                icon=icon,
                period_from_key=period_from_key,
                period_to_key=period_to_key,
                enabled_by_default=initially_available,  # Pass the flag
            ),
        )
    async_add_entities(entities)
    _LOGGER.info("Added %d Tibber Unofficial reward sensors.", len(entities))


class GridRewardComponentSensor(
    CoordinatorEntity[GridRewardsCoordinator],
    SensorEntity,
):
    """Representation of a Tibber Unofficial Grid Reward component sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_entity_registry_enabled_default = True  # Default for all sensors
    _attr_suggested_display_precision = 2
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GridRewardsCoordinator,
        config_entry_id: str,
        data_key: str,
        name_suffix: str,
        icon: str,
        period_from_key: str,
        period_to_key: str,
        enabled_by_default: bool = True,  # New parameter
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)

        object_id_suffix = data_key.replace("-", "_").replace(" ", "_").lower()
        if object_id_suffix.startswith("grid_rewards_"):
            object_id_suffix = object_id_suffix[len("grid_rewards_") :]
        self.entity_id = f"sensor.{DOMAIN}_{object_id_suffix}"

        self._config_entry_id = config_entry_id
        self._data_key = data_key
        self._period_from_key = period_from_key
        self._period_to_key = period_to_key

        self._attr_name = f"Grid Rewards {name_suffix}"
        self._attr_unique_id = f"{self._config_entry_id}_{self._data_key}"
        self._attr_icon = icon

        # Set if this entity should be enabled by default in the entity registry
        self._attr_entity_registry_enabled_default = enabled_by_default

        # _LOGGER.debug("Initializing sensor: %s (UID: %s, EID: %s, EnabledByDefault: %s)",
        #               self.name, self.unique_id, self.entity_id, self._attr_entity_registry_enabled_default) # Removed

    @property
    def available(self) -> bool:
        """Return True if coordinator has data and the specific sensor key exists."""
        if not super().available or self.coordinator.data is None:
            return False

        if self._data_key not in self.coordinator.data:
            return False

        # For current day sensors, allow None values (common when no rewards accumulated yet today)
        if "current_day" in self._data_key:
            return True

        # For other sensors, require non-None values
        return self.coordinator.data.get(self._data_key) is not None

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = self.coordinator.data.get(self._data_key)
            if isinstance(value, (int, float)):
                return round(value, 2)
            # For current day sensors, return 0.0 when value is None (no rewards accumulated yet)
            if value is None and "current_day" in self._data_key:
                return 0.0
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        if self.coordinator.data:
            currency = self.coordinator.data.get(KEY_CURRENCY)
            if currency and currency != "N/A":
                return currency
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {}
        if self.coordinator.data:
            attrs[ATTR_DATA_PERIOD_FROM] = self.coordinator.data.get(
                self._period_from_key,
            )
            attrs[ATTR_DATA_PERIOD_TO] = self.coordinator.data.get(self._period_to_key)
            attrs[ATTR_LAST_UPDATED] = dt_util.as_utc(datetime.now()).isoformat()
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping."""
        display_identifier = "Tibber Account"
        client = getattr(self.coordinator, "client", None)
        email = getattr(client, "_email", None) if client else None

        if email:
            display_identifier = email

        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            name=f"Tibber Grid Rewards ({display_identifier})",
            manufacturer="Tibber",
            model="Grid Rewards API",
            sw_version=self.coordinator.config_entry.version,
            configuration_url="https://app.tibber.com",
            entry_type="service",
        )
