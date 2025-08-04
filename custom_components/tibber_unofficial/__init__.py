"""The Tibber Unofficial integration."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict

from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    DOMAIN, PLATFORMS,
    DEFAULT_REWARDS_SCAN_INTERVAL, DEFAULT_GIZMO_SCAN_INTERVAL,
    CONF_EMAIL, CONF_PASSWORD, CONF_HOME_ID, CONF_GIZMO_IDS, DESIRED_GIZMO_TYPES,
    GRID_REWARDS_EV_CURRENT_MONTH, GRID_REWARDS_HOMEVOLT_CURRENT_MONTH, GRID_REWARDS_TOTAL_CURRENT_MONTH,
    GRID_REWARDS_EV_PREVIOUS_MONTH, GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH, GRID_REWARDS_TOTAL_PREVIOUS_MONTH,
    GRID_REWARDS_EV_YEAR, GRID_REWARDS_HOMEVOLT_YEAR, GRID_REWARDS_TOTAL_YEAR,
    GRID_REWARDS_EV_CURRENT_DAY, GRID_REWARDS_HOMEVOLT_CURRENT_DAY, GRID_REWARDS_TOTAL_CURRENT_DAY,
    KEY_CURRENCY,
    COORDINATOR_REWARDS, COORDINATOR_GIZMOS,
)
from .api import TibberApiClient, ApiAuthError, ApiError

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tibber Unofficial from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    home_id = entry.data[CONF_HOME_ID]
    initial_gizmo_ids = entry.data.get(CONF_GIZMO_IDS, {})

    _LOGGER.info("Setting up Tibber Unofficial for Home ID: %s (version: %s)", home_id, entry.version)
    # _LOGGER.debug("Initial Gizmo IDs from config entry: %s", initial_gizmo_ids) # Removed

    session = async_get_clientsession(hass)
    api_client = TibberApiClient(session=session, email=email, password=password)

    rewards_coordinator = GridRewardsCoordinator(hass, api_client, home_id)
    await rewards_coordinator.async_config_entry_first_refresh()

    gizmo_coordinator = GizmoUpdateCoordinator(hass, api_client, home_id, initial_gizmo_ids)
    await gizmo_coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR_REWARDS: rewards_coordinator,
        COORDINATOR_GIZMOS: gizmo_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Tibber Unofficial setup complete for entry ID: %s", entry.entry_id)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Tibber Unofficial for entry ID: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class GridRewardsCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching Grid Rewards data."""
    def __init__(self, hass: HomeAssistant, client: TibberApiClient, home_id: str):
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN} Grid Rewards Data",
            update_interval=DEFAULT_REWARDS_SCAN_INTERVAL,
        )
        self.client = client
        self.home_id = home_id

    async def _fetch_reward_data_for_period(self, period_name: str, from_date: datetime, to_date: datetime) -> Dict[str, Any]:
        from_date_str = from_date.isoformat()
        to_date_str = to_date.isoformat()
        try:
            return await self.client.async_get_grid_rewards_history(
                self.home_id, from_date_str, to_date_str
            )
        except Exception:
            _LOGGER.warning("GridRewardsCoordinator: Failed to fetch %s rewards for home %s.", period_name, self.home_id, exc_info=True)
            return {"ev": None, "homevolt": None, "total": None, "currency": None, "from_date_api": None, "to_date_api": None}

    async def _async_update_data(self) -> Optional[Dict[str, Any]]:
        # _LOGGER.debug("GridRewardsCoordinator _async_update_data CALLED for Home ID: %s", self.home_id) # Removed
        try:
            today_dt_util = dt_util.now()
            today_datetime = datetime.now(today_dt_util.tzinfo)

            # Calculate date ranges for current month, previous month, and year
            first_day_current_month = today_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if today_datetime.month == 12:
                first_day_next_month = today_datetime.replace(year=today_datetime.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                first_day_next_month = today_datetime.replace(month=today_datetime.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            last_day_previous_month_calc = first_day_current_month - timedelta(days=1)
            first_day_previous_month = last_day_previous_month_calc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            first_day_current_year = today_datetime.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

            # Calculate date range for current day
            start_of_day = today_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = today_datetime

            # Fetch data for all periods
            current_month_api_data = await self._fetch_reward_data_for_period("Current Month", first_day_current_month, first_day_next_month)
            previous_month_api_data = await self._fetch_reward_data_for_period("Previous Month", first_day_previous_month, first_day_current_month)
            year_api_data = await self._fetch_reward_data_for_period("Year", first_day_current_year, first_day_next_month)
            current_day_api_data = await self._fetch_reward_data_for_period("Current Day", start_of_day, end_of_day)
            
            final_currency = current_month_api_data.get("currency") or \
                             previous_month_api_data.get("currency") or \
                             year_api_data.get("currency") or \
                             current_day_api_data.get("currency") or \
                             "N/A"

            compiled_data = {
                GRID_REWARDS_EV_CURRENT_MONTH: current_month_api_data.get("ev"),
                GRID_REWARDS_HOMEVOLT_CURRENT_MONTH: current_month_api_data.get("homevolt"),
                GRID_REWARDS_TOTAL_CURRENT_MONTH: current_month_api_data.get("total"),
                "current_month_from": current_month_api_data.get("from_date_api"),
                "current_month_to": current_month_api_data.get("to_date_api"),
                GRID_REWARDS_EV_PREVIOUS_MONTH: previous_month_api_data.get("ev"),
                GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH: previous_month_api_data.get("homevolt"),
                GRID_REWARDS_TOTAL_PREVIOUS_MONTH: previous_month_api_data.get("total"),
                "previous_month_from": previous_month_api_data.get("from_date_api"),
                "previous_month_to": previous_month_api_data.get("to_date_api"),
                GRID_REWARDS_EV_YEAR: year_api_data.get("ev"),
                GRID_REWARDS_HOMEVOLT_YEAR: year_api_data.get("homevolt"),
                GRID_REWARDS_TOTAL_YEAR: year_api_data.get("total"),
                "year_from": year_api_data.get("from_date_api"),
                "year_to": year_api_data.get("to_date_api"),
                GRID_REWARDS_EV_CURRENT_DAY: current_day_api_data.get("ev"),
                GRID_REWARDS_HOMEVOLT_CURRENT_DAY: current_day_api_data.get("homevolt"),
                GRID_REWARDS_TOTAL_CURRENT_DAY: current_day_api_data.get("total"),
                "current_day_from": current_day_api_data.get("from_date_api"),
                "current_day_to": current_day_api_data.get("to_date_api"),
                KEY_CURRENCY: final_currency
            }
            # _LOGGER.debug("GridRewardsCoordinator updated data: %s", compiled_data) # Removed
            return compiled_data
        except ApiAuthError as err:
            _LOGGER.error("Authentication error in GridRewardsCoordinator.")
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            _LOGGER.error("API communication error in GridRewardsCoordinator.")
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error in GridRewardsCoordinator _async_update_data.")
            raise UpdateFailed(f"Unexpected error in GridRewardsCoordinator update: {err}") from err

class GizmoUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching Gizmo data."""
    def __init__(self, hass: HomeAssistant, client: TibberApiClient, home_id: str, initial_gizmos: Dict[str, List[str]]):
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN} Gizmo Data",
            update_interval=DEFAULT_GIZMO_SCAN_INTERVAL,
        )
        self.client = client
        self.home_id = home_id

    async def _async_update_data(self) -> Dict[str, List[str]]:
        # _LOGGER.debug("GizmoUpdateCoordinator _async_update_data CALLED for Home ID: %s", self.home_id) # Removed
        try:
            gizmos_list = await self.client.async_get_gizmos(self.home_id)
            gizmo_ids_by_type: Dict[str, List[str]] = defaultdict(list)
            if isinstance(gizmos_list, list):
                for gizmo in gizmos_list:
                    gizmo_type = gizmo.get("type")
                    gizmo_id = gizmo.get("id")
                    if gizmo_type in DESIRED_GIZMO_TYPES and gizmo_id:
                        gizmo_ids_by_type[gizmo_type].append(gizmo_id)
            
            processed_gizmos = dict(gizmo_ids_by_type)
            # _LOGGER.debug("GizmoUpdateCoordinator updated data: %s", processed_gizmos) # Removed
            return processed_gizmos
        except ApiAuthError as err:
            _LOGGER.error("Authentication error in GizmoUpdateCoordinator.")
            raise ConfigEntryAuthFailed(f"Authentication failed fetching gizmos: {err}") from err
        except ApiError as err:
            _LOGGER.error("API error in GizmoUpdateCoordinator.")
            raise UpdateFailed(f"API error fetching gizmos: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error in GizmoUpdateCoordinator _async_update_data.")
            raise UpdateFailed(f"Unexpected error fetching gizmos: {err}") from err