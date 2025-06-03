"""Sensor platform for Tibber Unofficial."""
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN, 
    ATTR_LAST_UPDATED, 
    ATTR_DATA_PERIOD_FROM, 
    ATTR_DATA_PERIOD_TO,
    GRID_REWARDS_EV_CURRENT_MONTH, 
    GRID_REWARDS_HOMEVOLT_CURRENT_MONTH, 
    GRID_REWARDS_TOTAL_CURRENT_MONTH,
    GRID_REWARDS_EV_PREVIOUS_MONTH, 
    GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH, 
    GRID_REWARDS_TOTAL_PREVIOUS_MONTH,
    GRID_REWARDS_EV_YEAR, 
    GRID_REWARDS_HOMEVOLT_YEAR,
    GRID_REWARDS_TOTAL_YEAR,
    KEY_CURRENCY,
    COORDINATOR_REWARDS,
)
from . import GridRewardsCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_DEFINITIONS = [
    (GRID_REWARDS_EV_CURRENT_MONTH, "EV - Current Month", "mdi:car-electric", "current_month_from", "current_month_to"),
    (GRID_REWARDS_EV_PREVIOUS_MONTH, "EV - Previous Month", "mdi:car-electric", "previous_month_from", "previous_month_to"),
    (GRID_REWARDS_EV_YEAR, "EV - Year", "mdi:car-electric", "year_from", "year_to"),
    (GRID_REWARDS_HOMEVOLT_CURRENT_MONTH, "Homevolt - Current Month", "mdi:home-battery", "current_month_from", "current_month_to"),
    (GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH, "Homevolt - Previous Month", "mdi:home-battery", "previous_month_from", "previous_month_to"),
    (GRID_REWARDS_HOMEVOLT_YEAR, "Homevolt - Year", "mdi:home-battery", "year_from", "year_to"),
    (GRID_REWARDS_TOTAL_CURRENT_MONTH, "Total - Current Month", "mdi:cash-multiple", "current_month_from", "current_month_to"),
    (GRID_REWARDS_TOTAL_PREVIOUS_MONTH, "Total - Previous Month", "mdi:cash-multiple", "previous_month_from", "previous_month_to"),
    (GRID_REWARDS_TOTAL_YEAR, "Total - Year", "mdi:cash-multiple", "year_from", "year_to"),
]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform from a config entry."""
    rewards_coordinator: GridRewardsCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR_REWARDS]
    
    entities = []
    for data_key, name_suffix, icon, period_from_key, period_to_key in SENSOR_DEFINITIONS:
        entities.append(
            GridRewardComponentSensor(
                coordinator=rewards_coordinator,
                config_entry_id=entry.entry_id,
                data_key=data_key,
                name_suffix=name_suffix,
                icon=icon,
                period_from_key=period_from_key,
                period_to_key=period_to_key
            )
        )
    async_add_entities(entities)

class GridRewardComponentSensor(CoordinatorEntity[GridRewardsCoordinator], SensorEntity):
    """Representation of a Tibber Unofficial Grid Reward component sensor."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        coordinator: GridRewardsCoordinator,
        config_entry_id: str,
        data_key: str,
        name_suffix: str,
        icon: str,
        period_from_key: str,
        period_to_key: str
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        object_id_suffix = data_key.replace('-', '_').replace(' ', '_').lower()
        if object_id_suffix.startswith("grid_rewards_"):
            object_id_suffix = object_id_suffix[len("grid_rewards_"):]
        self.entity_id = f"sensor.{DOMAIN}_{object_id_suffix}"

        self._config_entry_id = config_entry_id
        self._data_key = data_key
        self._period_from_key = period_from_key
        self._period_to_key = period_to_key

        self._attr_name = f"Grid Rewards {name_suffix}"
        self._attr_unique_id = f"{self._config_entry_id}_{self._data_key}"
        self._attr_icon = icon

    @property
    def available(self) -> bool:
        """Return True if coordinator has data and the specific sensor key exists and has a non-None value."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get(self._data_key) is not None
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        if self.coordinator.data:
            value = self.coordinator.data.get(self._data_key)
            if isinstance(value, (int, float)):
                return round(value, 2)
            if value is not None: 
                # _LOGGER.warning("Sensor %s (%s) received non-numeric value '%s' of type %s", self.name, self._data_key, value, type(value))
                pass
        return None

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        """Return the unit of measurement."""
        if self.coordinator.data:
            currency = self.coordinator.data.get(KEY_CURRENCY)
            if currency and currency != "N/A":
                return currency
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        attrs = {}
        if self.coordinator.data:
            attrs[ATTR_DATA_PERIOD_FROM] = self.coordinator.data.get(self._period_from_key)
            attrs[ATTR_DATA_PERIOD_TO] = self.coordinator.data.get(self._period_to_key)
            attrs[ATTR_LAST_UPDATED] = dt_util.as_utc(datetime.now()).isoformat()
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping."""
        display_identifier = "Tibber Account"
        client = getattr(self.coordinator, 'client', None)
        email = getattr(client, '_email', None) if client else None
        
        if email:
            display_identifier = email
        
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            name=f"Tibber Api integration ({display_identifier})", 
            manufacturer="Tibber (via unofficial integration)",   
            model="Tibber Api",                                 
            sw_version=self.coordinator.config_entry.version, 
        )