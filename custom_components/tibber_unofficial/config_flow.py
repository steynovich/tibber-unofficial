"""Config flow for Tibber Unofficial."""
import logging
import voluptuous as vol
from typing import Any, Dict, Optional, List
from collections import defaultdict

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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

_LOGGER = logging.getLogger(__name__) # Kept for error logging

USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

class TibberConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tibber Unofficial."""
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    user_auth_data: Dict[str, Any]
    api_client: TibberApiClient
    
    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self.user_auth_data = {}

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the initial step (email/password authentication)."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)
            
            self.api_client = TibberApiClient(session=session, email=email, password=password)
            self.user_auth_data = user_input

            try:
                await self.api_client.authenticate() # API client logs success/failure
                return await self.async_step_select_home()
            except ApiAuthError:
                _LOGGER.error("Authentication failed for %s during config flow.", email)
                errors["base"] = "invalid_auth"
            except ApiError: # Catch other API errors during auth
                _LOGGER.error("API connection error during authentication for %s.", email, exc_info=True)
                errors["base"] = "cannot_connect"
            except Exception: 
                _LOGGER.exception("Unexpected exception during authentication in config flow.")
                errors["base"] = "unknown"
        
        return self.async_show_form(
            step_id="user", data_schema=USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_select_home(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle fetching homes, selecting one, and then fetching gizmos."""
        errors: Dict[str, str] = {}
        try:
            if not hasattr(self, 'api_client') or not self.api_client:
                 _LOGGER.error("API client not initialized before trying to select home. Aborting flow.")
                 return self.async_abort(reason="api_client_not_initialized")

            homes = await self.api_client.async_get_homes()
            if not homes:
                _LOGGER.warning("No homes found for account %s", self.user_auth_data.get(CONF_EMAIL))
                return self.async_abort(reason="no_homes_found")

            suitable_homes = [h for h in homes if h.get("hasSignedEnergyDeal") is True]
            if not suitable_homes:
                _LOGGER.warning("No homes with an active energy deal found for %s", self.user_auth_data.get(CONF_EMAIL))
                return self.async_abort(reason="no_active_deal")
            
            selected_home = suitable_homes[0]
            selected_home_id = selected_home.get("id")
            
            if not selected_home_id:
                 _LOGGER.error("Selected home has no ID: %s. Aborting flow.", selected_home)
                 return self.async_abort(reason="home_id_missing")

            selected_home_display_name = f"Home ({selected_home_id[-6:]})"
            # _LOGGER.info("Selected Home ID: %s for account %s", selected_home_id, self.user_auth_data.get(CONF_EMAIL)) # Removed

            gizmos = await self.api_client.async_get_gizmos(selected_home_id)
            gizmo_ids_by_type: Dict[str, List[str]] = defaultdict(list)
            if isinstance(gizmos, list):
                for gizmo in gizmos:
                    gizmo_type = gizmo.get("type")
                    gizmo_id = gizmo.get("id")
                    if gizmo_type in DESIRED_GIZMO_TYPES and gizmo_id:
                        gizmo_ids_by_type[gizmo_type].append(gizmo_id)
            else:
                _LOGGER.warning("Gizmos data is not a list or is None for home %s: %s", selected_home_id, gizmos)
            
            # _LOGGER.info("Extracted Gizmo IDs for home %s: %s", selected_home_id, dict(gizmo_ids_by_type)) # Removed

            entry_data = {
                CONF_EMAIL: self.user_auth_data[CONF_EMAIL],
                CONF_PASSWORD: self.user_auth_data[CONF_PASSWORD],
                CONF_HOME_ID: selected_home_id,
                CONF_GIZMO_IDS: dict(gizmo_ids_by_type),
            }

            unique_flow_id = f"{self.user_auth_data[CONF_EMAIL].lower()}_{selected_home_id}"
            await self.async_set_unique_id(unique_flow_id)
            self._abort_if_unique_id_configured(updates=entry_data) 

            return self.async_create_entry(
                title=f"Tibber ({selected_home_display_name})",
                data=entry_data,
            )

        except ApiAuthError: # Should be rare here if user step succeeded
            _LOGGER.error("Authentication error occurred during home/gizmo selection phase.")
            return self.async_abort(reason="auth_failed_homes")
        except ApiError:
            _LOGGER.error("API error during home/gizmo selection.", exc_info=True)
            errors["base"] = "cannot_connect_homes" 
            return self.async_show_form(step_id="user", data_schema=USER_DATA_SCHEMA, errors=errors)
        except Exception:
            _LOGGER.exception("Unexpected error during home/gizmo selection.")
            errors["base"] = "unknown_home_select"
            return self.async_show_form(step_id="user", data_schema=USER_DATA_SCHEMA, errors=errors)