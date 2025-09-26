"""The Tibber Unofficial integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from collections import defaultdict
import aiohttp

from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    DOMAIN,
    PLATFORMS,
    DEFAULT_REWARDS_SCAN_INTERVAL,
    DEFAULT_GIZMO_SCAN_INTERVAL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_HOME_ID,
    CONF_GIZMO_IDS,
    DESIRED_GIZMO_TYPES,
    GRID_REWARDS_EV_CURRENT_MONTH,
    GRID_REWARDS_HOMEVOLT_CURRENT_MONTH,
    GRID_REWARDS_TOTAL_CURRENT_MONTH,
    GRID_REWARDS_EV_PREVIOUS_MONTH,
    GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH,
    GRID_REWARDS_TOTAL_PREVIOUS_MONTH,
    GRID_REWARDS_EV_YEAR,
    GRID_REWARDS_HOMEVOLT_YEAR,
    GRID_REWARDS_TOTAL_YEAR,
    GRID_REWARDS_EV_CURRENT_DAY,
    GRID_REWARDS_HOMEVOLT_CURRENT_DAY,
    GRID_REWARDS_TOTAL_CURRENT_DAY,
    KEY_CURRENCY,
    COORDINATOR_REWARDS,
    COORDINATOR_GIZMOS,
)
from .api import TibberApiClient, ApiAuthError, ApiError
from .storage import RateLimiterStorage
from .services import async_setup_services, async_unload_services
from .repairs import async_create_issue, async_delete_issue

_LOGGER = logging.getLogger(__name__)

# Debug logging can be enabled in configuration.yaml:
# logger:
#   default: info
#   logs:
#     custom_components.tibber_unofficial: debug


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tibber Unofficial from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    home_id = entry.data[CONF_HOME_ID]
    initial_gizmo_ids = entry.data.get(CONF_GIZMO_IDS, {})

    _LOGGER.info(
        "Setting up Tibber Unofficial for Home ID: %s (version: %s)",
        home_id[:8],
        entry.version,
    )
    _LOGGER.debug(
        "Configuration: email=%s, home_id=%s, gizmos=%s",
        email,
        home_id[:8],
        list(initial_gizmo_ids.keys()) if initial_gizmo_ids else [],
    )

    # Create a dedicated session with connection pooling and timeouts
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    session = async_create_clientsession(hass, timeout=timeout)

    # Store session in hass.data for cleanup
    hass.data[DOMAIN].setdefault("sessions", {})
    hass.data[DOMAIN]["sessions"][entry.entry_id] = session

    # Create storage for rate limiter persistence
    rate_limiter_storage = RateLimiterStorage(hass, entry.entry_id)

    # Store session reference for cleanup
    try:
        api_client = TibberApiClient(
            session=session,
            email=email,
            password=password,
            storage=rate_limiter_storage,
        )
        # Initialize rate limiter with stored state
        await api_client.initialize()
    except Exception:
        await session.close()
        raise

    # Get update intervals from options or use defaults
    rewards_interval_minutes = entry.options.get(
        "rewards_scan_interval", int(DEFAULT_REWARDS_SCAN_INTERVAL.total_seconds() / 60),
    )
    gizmo_interval_hours = entry.options.get(
        "gizmo_scan_interval", int(DEFAULT_GIZMO_SCAN_INTERVAL.total_seconds() / 3600),
    )

    _LOGGER.debug(
        "Initializing rewards coordinator (interval: %d minutes)",
        rewards_interval_minutes,
    )
    rewards_coordinator = GridRewardsCoordinator(
        hass,
        api_client,
        home_id,
        update_interval=timedelta(minutes=rewards_interval_minutes),
    )
    await rewards_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Rewards coordinator initialized successfully")

    _LOGGER.debug(
        "Initializing gizmo coordinator (interval: %d hours)", gizmo_interval_hours,
    )
    gizmo_coordinator = GizmoUpdateCoordinator(
        hass,
        api_client,
        home_id,
        initial_gizmo_ids,
        update_interval=timedelta(hours=gizmo_interval_hours),
    )
    await gizmo_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Gizmo coordinator initialized successfully")

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR_REWARDS: rewards_coordinator,
        COORDINATOR_GIZMOS: gizmo_coordinator,
        "session": session,
    }

    # Subscribe to options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Tibber Unofficial setup complete for %s", email)
    _LOGGER.debug("Entry ID: %s, Platforms loaded: %s", entry.entry_id, PLATFORMS)

    # Log cache efficiency periodically
    async def log_cache_stats() -> None:
        """Log cache statistics periodically."""
        try:
            # Use shorter sleep intervals to respond quickly to cancellation
            intervals_passed = 0
            while entry.entry_id in hass.data.get(DOMAIN, {}):
                # Sleep in 60 second intervals, check every minute
                await asyncio.sleep(60)
                intervals_passed += 1

                # Only log stats every hour (60 intervals)
                if intervals_passed >= 60:
                    intervals_passed = 0
                    if entry.entry_id in hass.data.get(DOMAIN, {}):
                        stats = api_client.get_cache_stats()
                        if stats["total_requests"] > 0:
                            _LOGGER.info(
                                "Cache stats: %d entries, %.1f%% hit rate (%d hits, %d misses)",
                                stats["entries"],
                                stats["hit_rate"],
                                stats["hits"],
                                stats["misses"],
                            )
                    else:
                        break
        except asyncio.CancelledError:
            _LOGGER.debug("Cache stats task cancelled")
            raise
        except Exception:
            pass  # Other exceptions during logging

    # Start cache stats logging task and store reference for cleanup
    cache_task = hass.async_create_background_task(
        log_cache_stats(), "tibber_unofficial_cache_stats"
    )
    hass.data[DOMAIN][entry.entry_id]["cache_task"] = cache_task

    # Setup services (only once for the domain)
    if not hass.services.has_service(DOMAIN, "refresh_rewards"):
        await async_setup_services(hass)

    # Clear any existing authentication issues
    await async_delete_issue(hass, "auth_failed", DOMAIN)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    _LOGGER.info("Options changed - Reloading Tibber Unofficial integration")

    # Update coordinator intervals without full reload if only intervals changed
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        data = hass.data[DOMAIN][entry.entry_id]

        # Get new intervals from options
        rewards_interval_minutes = entry.options.get(
            "rewards_scan_interval",
            int(DEFAULT_REWARDS_SCAN_INTERVAL.total_seconds() / 60),
        )
        gizmo_interval_hours = entry.options.get(
            "gizmo_scan_interval",
            int(DEFAULT_GIZMO_SCAN_INTERVAL.total_seconds() / 3600),
        )

        # Update coordinator intervals
        if COORDINATOR_REWARDS in data:
            data[COORDINATOR_REWARDS].update_interval = timedelta(
                minutes=rewards_interval_minutes,
            )
            _LOGGER.debug(
                "Updated rewards coordinator interval to %d minutes",
                rewards_interval_minutes,
            )

        if COORDINATOR_GIZMOS in data:
            data[COORDINATOR_GIZMOS].update_interval = timedelta(
                hours=gizmo_interval_hours,
            )
            _LOGGER.debug(
                "Updated gizmo coordinator interval to %d hours", gizmo_interval_hours,
            )

        # Request immediate refresh with new intervals
        await data[COORDINATOR_REWARDS].async_request_refresh()
        await data[COORDINATOR_GIZMOS].async_request_refresh()
    else:
        # Fallback to full reload if data structure not found
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        "Unloading Tibber Unofficial for %s", entry.data.get(CONF_EMAIL, "unknown"),
    )
    _LOGGER.debug("Entry ID being unloaded: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            # Cancel cache stats task
            if "cache_task" in hass.data[DOMAIN][entry.entry_id]:
                cache_task = hass.data[DOMAIN][entry.entry_id]["cache_task"]
                if not cache_task.done():
                    cache_task.cancel()
                    try:
                        await asyncio.wait_for(cache_task, timeout=1.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    except Exception as e:
                        _LOGGER.debug("Error cancelling cache task: %s", e)

            # Close the dedicated session
            if "session" in hass.data[DOMAIN][entry.entry_id]:
                session = hass.data[DOMAIN][entry.entry_id]["session"]
                await session.close()

            # Clean up session from sessions dict
            if (
                "sessions" in hass.data[DOMAIN]
                and entry.entry_id in hass.data[DOMAIN]["sessions"]
            ):
                hass.data[DOMAIN]["sessions"].pop(entry.entry_id)

            # Clean up rate limiter storage
            try:
                rate_limiter_storage = RateLimiterStorage(hass, entry.entry_id)
                await rate_limiter_storage.async_remove()
            except Exception:
                pass  # Best effort cleanup

            hass.data[DOMAIN].pop(entry.entry_id)
            _LOGGER.debug("Entry data cleaned up successfully")

        # Unload services if this is the last entry
        remaining_entries = [
            e
            for e in hass.data.get(DOMAIN, {}).keys()
            if e != "sessions" and isinstance(hass.data[DOMAIN].get(e), dict)
        ]
        if not remaining_entries:
            await async_unload_services(hass)
    else:
        _LOGGER.warning("Failed to unload some platforms for entry %s", entry.entry_id)
    return unload_ok


class GridRewardsCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching Grid Rewards data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: TibberApiClient,
        home_id: str,
        update_interval: timedelta | None = None,
    ):
        """Initialize with configurable update interval."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Grid Rewards Data",
            update_interval=update_interval or DEFAULT_REWARDS_SCAN_INTERVAL,
        )
        self.client = client
        self.home_id = home_id
        _LOGGER.debug(
            "GridRewardsCoordinator initialized with interval: %s", self.update_interval,
        )

    async def _fetch_reward_data_for_period(
        self, period_name: str, from_date: datetime, to_date: datetime,
    ) -> Dict[str, Any]:
        from_date_str = from_date.isoformat()
        to_date_str = to_date.isoformat()
        _LOGGER.debug(
            "Fetching %s rewards: %s to %s",
            period_name,
            from_date_str[:10],
            to_date_str[:10],
        )
        try:
            # The API requires 'monthly' resolution - 'daily' is not supported
            # Monthly resolution still provides data for the date range specified
            use_daily_resolution = False
            return await self.client.async_get_grid_rewards_history(
                self.home_id,
                from_date_str,
                to_date_str,
                use_daily_resolution=use_daily_resolution,
            )
        except Exception as e:
            _LOGGER.warning(
                "Failed to fetch %s rewards for home %s: %s",
                period_name,
                self.home_id[:8],
                str(e),
            )
            _LOGGER.debug("Full error details:", exc_info=True)
            return {
                "ev": None,
                "homevolt": None,
                "total": None,
                "currency": None,
                "from_date_api": None,
                "to_date_api": None,
            }

    async def _async_update_data(self) -> Dict[str, Any] | None:
        _LOGGER.debug("Starting rewards data update for home %s", self.home_id[:8])
        try:
            # Use Home Assistant's timezone-aware datetime
            today_datetime = dt_util.now()

            # Calculate date ranges for current month, previous month, and year
            # Ensure we're working in UTC for API calls
            today_utc = today_datetime.astimezone(timezone.utc)
            first_day_current_month = today_utc.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            if today_utc.month == 12:
                first_day_next_month = today_utc.replace(
                    year=today_utc.year + 1,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                first_day_next_month = today_utc.replace(
                    month=today_utc.month + 1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

            last_day_previous_month_calc = first_day_current_month - timedelta(days=1)
            first_day_previous_month = last_day_previous_month_calc.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            first_day_current_year = today_utc.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0,
            )

            # Fetch data for all periods
            current_month_api_data = await self._fetch_reward_data_for_period(
                "Current Month", first_day_current_month, first_day_next_month,
            )
            previous_month_api_data = await self._fetch_reward_data_for_period(
                "Previous Month", first_day_previous_month, first_day_current_month,
            )
            year_api_data = await self._fetch_reward_data_for_period(
                "Year", first_day_current_year, first_day_next_month,
            )

            # Since the API doesn't properly support daily resolution,
            # use current month data for current day sensors
            # This will show month-to-date values
            current_day_api_data = current_month_api_data

            final_currency = (
                current_month_api_data.get("currency")
                or previous_month_api_data.get("currency")
                or year_api_data.get("currency")
                or current_day_api_data.get("currency")
                or "N/A"
            )

            compiled_data = {
                GRID_REWARDS_EV_CURRENT_MONTH: current_month_api_data.get("ev"),
                GRID_REWARDS_HOMEVOLT_CURRENT_MONTH: current_month_api_data.get(
                    "homevolt",
                ),
                GRID_REWARDS_TOTAL_CURRENT_MONTH: current_month_api_data.get("total"),
                "current_month_from": current_month_api_data.get("from_date_api"),
                "current_month_to": current_month_api_data.get("to_date_api"),
                GRID_REWARDS_EV_PREVIOUS_MONTH: previous_month_api_data.get("ev"),
                GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH: previous_month_api_data.get(
                    "homevolt",
                ),
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
                KEY_CURRENCY: final_currency,
            }
            _LOGGER.info(
                "Successfully updated rewards data - Currency: %s, Current month total: %s",
                final_currency,
                compiled_data.get(GRID_REWARDS_TOTAL_CURRENT_MONTH),
            )
            _LOGGER.debug(
                "Full rewards data: Current day: %s, Current month: %s, Year: %s",
                compiled_data.get(GRID_REWARDS_TOTAL_CURRENT_DAY),
                compiled_data.get(GRID_REWARDS_TOTAL_CURRENT_MONTH),
                compiled_data.get(GRID_REWARDS_TOTAL_YEAR),
            )

            # Log cache efficiency
            if hasattr(self.client, "get_cache_stats"):
                stats = self.client.get_cache_stats()
                if stats["total_requests"] > 10:  # Only log after some requests
                    _LOGGER.debug(
                        "API cache performance: %.1f%% hit rate", stats["hit_rate"],
                    )

            return compiled_data
        except ApiAuthError as err:
            _LOGGER.error("Authentication failed during rewards update: %s", str(err))
            # Create repair issue for authentication failure
            await async_create_issue(
                self.hass,
                "auth_failed",
                DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={
                    "entry_title": self.config_entry.title or "Tibber Unofficial",
                },
                data={
                    "entry_id": self.config_entry.entry_id,
                    "entry_title": self.config_entry.title,
                },
            )
            raise ConfigEntryAuthFailed(
                "Authentication failed - Please reconfigure the integration",
            ) from err
        except ApiError as err:
            _LOGGER.error("API error during rewards update: %s", str(err))
            # Check if it's a rate limit error
            if "rate limit" in str(err).lower() or "429" in str(err):
                current_interval = int(self.update_interval.total_seconds() / 60)
                await async_create_issue(
                    self.hass,
                    "rate_limit_exceeded",
                    DOMAIN,
                        translation_key="rate_limit_exceeded",
                    translation_placeholders={
                        "current_interval": str(current_interval),
                        "recommended_interval": str(max(30, current_interval * 2)),
                    },
                    data={
                        "entry_id": self.config_entry.entry_id,
                        "current_interval_minutes": current_interval,
                    },
                )
            raise UpdateFailed(f"Failed to fetch rewards data: {str(err)}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error updating rewards data: %s", str(err))
            raise UpdateFailed(f"Unexpected error: {str(err)}") from err


class GizmoUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching Gizmo data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: TibberApiClient,
        home_id: str,
        initial_gizmos: Dict[str, List[str]],
        update_interval: timedelta | None = None,
    ):
        """Initialize with configurable update interval."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} Gizmo Data",
            update_interval=update_interval or DEFAULT_GIZMO_SCAN_INTERVAL,
        )
        self.client = client
        self.home_id = home_id
        _LOGGER.debug(
            "GizmoUpdateCoordinator initialized with interval: %s", self.update_interval,
        )

    async def _async_update_data(self) -> Dict[str, List[str]]:
        _LOGGER.debug("Starting gizmo data update for home %s", self.home_id[:8])
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
            _LOGGER.info(
                "Successfully updated gizmo data - Found: %s",
                {k: len(v) for k, v in processed_gizmos.items()}
                if processed_gizmos
                else "None",
            )
            _LOGGER.debug("Gizmo details: %s", processed_gizmos)
            return processed_gizmos
        except ApiAuthError as err:
            _LOGGER.error("Authentication failed during gizmo update: %s", str(err))
            # Create repair issue for authentication failure
            await async_create_issue(
                self.hass,
                "auth_failed",
                DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={
                    "entry_title": self.config_entry.title or "Tibber Unofficial",
                },
                data={
                    "entry_id": self.config_entry.entry_id,
                    "entry_title": self.config_entry.title,
                },
            )
            raise ConfigEntryAuthFailed(
                "Authentication failed - Please reconfigure the integration",
            ) from err
        except ApiError as err:
            _LOGGER.error("API error during gizmo update: %s", str(err))
            raise UpdateFailed(f"Failed to fetch gizmo data: {str(err)}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error updating gizmo data: %s", str(err))
            raise UpdateFailed(f"Unexpected error: {str(err)}") from err
