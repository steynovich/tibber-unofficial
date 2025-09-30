"""Config flow for Tibber Unofficial."""

from __future__ import annotations

import logging
import voluptuous as vol
from typing import Any, Dict, List
from collections import defaultdict
import aiohttp

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_HOME_ID,
    CONF_GIZMO_IDS,
    DESIRED_GIZMO_TYPES,
)
from .api import TibberApiClient, ApiAuthError, ApiError

_LOGGER = logging.getLogger(__name__)

# Debug logging can be enabled in configuration.yaml:
# logger:
#   default: info
#   logs:
#     custom_components.tibber_unofficial: debug





USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): vol.All(cv.string, vol.Length(min=6, max=128)),
    },
)


class TibberConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Tibber Unofficial."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @config_entries.HANDLERS.register(DOMAIN)
    def async_get_options_flow(config_entry: Any) -> Any:
        """Get the options flow for this handler."""
        from .options_flow import TibberOptionsFlow

        return TibberOptionsFlow(config_entry)

    user_auth_data: Dict[str, Any]
    api_client: TibberApiClient

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self.user_auth_data = {}

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> Any:
        """Handle the initial step (email/password authentication)."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            try:
                # Validate and sanitize inputs
                email = user_input[CONF_EMAIL].strip().lower()
                password = user_input[CONF_PASSWORD].strip()
            except vol.Invalid as exc:
                _LOGGER.warning("Input validation failed: %s", exc)
                errors["base"] = "invalid_input"
                return self.async_show_form(
                    step_id="user",
                    data_schema=USER_DATA_SCHEMA,
                    errors=errors,
                    description_placeholders={"error": str(exc)},
                )

            # Create a temporary session for config flow
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
            session = async_create_clientsession(
                self.hass, timeout=timeout,
            )

            try:
                self.api_client = TibberApiClient(
                    session=session, email=email, password=password,
                )
                self.user_auth_data = {
                    CONF_EMAIL: email,
                    CONF_PASSWORD: password,
                }  # Store validated values

                _LOGGER.debug("Starting authentication for %s", email)
                await self.api_client.authenticate()
                _LOGGER.info("Authentication successful for %s", email)
                return await self.async_step_select_home()
            except ApiAuthError as e:
                _LOGGER.error("Authentication failed for %s: %s", email, str(e))
                errors["base"] = "invalid_auth"
            except ApiError as e:
                _LOGGER.error("API connection error for %s: %s", email, str(e))
                _LOGGER.debug("Full API error:", exc_info=True)
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.exception("Unexpected error during authentication: %s", str(e))
                errors["base"] = "unknown"
            finally:
                # Clean up the session on errors (success case handled by HA)
                if errors:
                    await session.close()

        return self.async_show_form(
            step_id="user", data_schema=USER_DATA_SCHEMA, errors=errors,
        )

    async def async_step_select_home(self, user_input: Dict[str, Any] | None = None) -> Any:
        """Handle fetching homes, selecting one, and then fetching gizmos."""
        errors: Dict[str, str] = {}
        try:
            if not hasattr(self, "api_client") or not self.api_client:
                _LOGGER.error("API client not initialized - This should not happen")
                return self.async_abort(reason="api_client_not_initialized")

            _LOGGER.debug("Fetching homes for user selection")
            homes = await self.api_client.async_get_homes()
            if not homes:
                _LOGGER.warning(
                    "No homes found for account %s - User may not have Tibber homes configured",
                    self.user_auth_data.get(CONF_EMAIL),
                )
                return self.async_abort(reason="no_homes_found")

            suitable_homes = [h for h in homes if h.get("hasSignedEnergyDeal") is True]
            if not suitable_homes:
                _LOGGER.warning(
                    "Found %d homes but none with active energy deal for %s",
                    len(homes),
                    self.user_auth_data.get(CONF_EMAIL),
                )
                _LOGGER.debug(
                    "Home energy deal status: %s",
                    [
                        {"id": h.get("id")[:8] if h.get("id") else None, "deal": h.get("hasSignedEnergyDeal")}  # type: ignore[index]
                        for h in homes
                    ],
                )
                return self.async_abort(reason="no_active_deal")

            selected_home = suitable_homes[0]
            selected_home_id = selected_home.get("id")

            if not selected_home_id:
                _LOGGER.error(
                    "Selected home has no ID: %s. Aborting flow.", selected_home,
                )
                return self.async_abort(reason="home_id_missing")

            selected_home_display_name = f"Home ({selected_home_id[-6:]})"
            _LOGGER.info(
                "Selected home %s for %s",
                selected_home_id[:8],
                self.user_auth_data.get(CONF_EMAIL),
            )
            _LOGGER.debug(
                "Home details: %s",
                {k: v for k, v in selected_home.items() if k != "id"},
            )

            _LOGGER.debug("Fetching gizmos for selected home")
            gizmos = await self.api_client.async_get_gizmos(selected_home_id)
            gizmo_ids_by_type: Dict[str, List[str]] = defaultdict(list)
            if isinstance(gizmos, list):
                for gizmo in gizmos:
                    gizmo_type = gizmo.get("type")
                    gizmo_id = gizmo.get("id")
                    if gizmo_type in DESIRED_GIZMO_TYPES and gizmo_id:
                        gizmo_ids_by_type[gizmo_type].append(gizmo_id)
            else:
                _LOGGER.warning(
                    "Invalid gizmos data for home %s - Expected list, got: %s",
                    selected_home_id[:8],
                    type(gizmos),
                )

            _LOGGER.info(
                "Found gizmos for home: %s",
                {k: len(v) for k, v in gizmo_ids_by_type.items()}
                if gizmo_ids_by_type
                else "None",
            )
            _LOGGER.debug("Gizmo IDs: %s", dict(gizmo_ids_by_type))

            entry_data = {
                CONF_EMAIL: self.user_auth_data[CONF_EMAIL],
                CONF_PASSWORD: self.user_auth_data[CONF_PASSWORD],
                CONF_HOME_ID: selected_home_id,
                CONF_GIZMO_IDS: dict(gizmo_ids_by_type),
            }

            unique_flow_id = (
                f"{self.user_auth_data[CONF_EMAIL].lower()}_{selected_home_id}"
            )
            await self.async_set_unique_id(unique_flow_id)
            self._abort_if_unique_id_configured(updates=entry_data)

            _LOGGER.info(
                "Configuration successful for %s - Creating entry",
                self.user_auth_data[CONF_EMAIL],
            )
            return self.async_create_entry(
                title=f"Tibber ({selected_home_display_name})",
                data=entry_data,
            )

        except ApiAuthError as e:
            _LOGGER.error("Authentication failed during home selection: %s", str(e))
            return self.async_abort(reason="auth_failed_homes")
        except ApiError as e:
            _LOGGER.error("API error during home/gizmo selection: %s", str(e))
            _LOGGER.debug("Full API error details:", exc_info=True)
            errors["base"] = "cannot_connect_homes"
            return self.async_show_form(
                step_id="user", data_schema=USER_DATA_SCHEMA, errors=errors,
            )
        except Exception as e:
            _LOGGER.exception(
                "Unexpected error during home/gizmo selection: %s", str(e),
            )
            errors["base"] = "unknown_home_select"
            return self.async_show_form(
                step_id="user", data_schema=USER_DATA_SCHEMA, errors=errors,
            )
