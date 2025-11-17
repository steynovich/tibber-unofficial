"""Options flow for Tibber Unofficial."""

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DEFAULT_GIZMO_SCAN_INTERVAL, DEFAULT_REWARDS_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Options keys
CONF_REWARDS_SCAN_INTERVAL = "rewards_scan_interval"
CONF_GIZMO_SCAN_INTERVAL = "gizmo_scan_interval"

# Minimum intervals to prevent API overload
MIN_REWARDS_INTERVAL = 5  # minutes
MIN_GIZMO_INTERVAL = 1  # hours


class TibberOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Tibber Unofficial."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            _LOGGER.info("Options updated for Tibber Unofficial: %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        # Get current values or defaults
        rewards_interval = self.config_entry.options.get(
            CONF_REWARDS_SCAN_INTERVAL,
            int(DEFAULT_REWARDS_SCAN_INTERVAL.total_seconds() / 60),
        )
        gizmo_interval = self.config_entry.options.get(
            CONF_GIZMO_SCAN_INTERVAL,
            int(DEFAULT_GIZMO_SCAN_INTERVAL.total_seconds() / 3600),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REWARDS_SCAN_INTERVAL,
                        default=rewards_interval,
                    ): vol.All(
                        cv.positive_int,
                        vol.Range(min=MIN_REWARDS_INTERVAL, max=1440),  # Max 24 hours
                    ),
                    vol.Required(
                        CONF_GIZMO_SCAN_INTERVAL,
                        default=gizmo_interval,
                    ): vol.All(
                        cv.positive_int,
                        vol.Range(min=MIN_GIZMO_INTERVAL, max=168),  # Max 1 week
                    ),
                },
            ),
            description_placeholders={
                "rewards_min": str(MIN_REWARDS_INTERVAL),
                "gizmo_min": str(MIN_GIZMO_INTERVAL),
            },
        )


@callback
def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> TibberOptionsFlow:
    """Get the options flow for this handler."""
    return TibberOptionsFlow(config_entry)
