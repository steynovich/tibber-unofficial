"""Repair flows for Tibber Unofficial integration."""

import logging
from typing import Any

import aiohttp
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, issue_registry as ir
import voluptuous as vol

from .api import ApiAuthError, TibberApiClient

_LOGGER = logging.getLogger(__name__)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create a repair flow."""
    if issue_id == "auth_failed":
        return AuthFailedRepairFlow(hass, issue_id, data)
    elif issue_id == "deprecated_config":
        return DeprecatedConfigRepairFlow(hass, issue_id, data)
    elif issue_id == "rate_limit_exceeded":
        return RateLimitRepairFlow(hass, issue_id, data)

    return ConfirmRepairFlow()


class AuthFailedRepairFlow(RepairsFlow):
    """Handle authentication failure repair."""

    def __init__(
        self,
        hass: HomeAssistant,
        issue_id: str,
        data: dict[str, Any] | None,
    ) -> None:
        """Initialize the repair flow."""
        super().__init__(hass, issue_id, data)
        self.entry_id = data.get("entry_id") if data else None

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                description_placeholders={
                    "entry_title": self.data.get("entry_title", "Unknown"),
                },
                data_schema=vol.Schema(
                    {
                        vol.Required("email"): cv.string,
                        vol.Required("password"): cv.string,
                    },
                ),
            )

        # Validate credentials
        errors = {}
        try:
            # Test authentication with new credentials
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                api_client = TibberApiClient(
                    session=session,
                    email=user_input["email"],
                    password=user_input["password"],
                )
                await api_client.authenticate()
                _LOGGER.info(
                    "Authentication repair successful for %s",
                    user_input["email"],
                )

        except ApiAuthError:
            errors["base"] = "invalid_auth"
        except Exception as e:
            _LOGGER.exception("Unexpected error during authentication repair: %s", e)
            errors["base"] = "unknown"

        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required("email"): cv.string,
                        vol.Required("password"): cv.string,
                    },
                ),
                errors=errors,
            )

        # Update config entry with new credentials
        if self.entry_id:
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry:
                new_data = dict(entry.data)
                new_data["email"] = user_input["email"]
                new_data["password"] = user_input["password"]

                self.hass.config_entries.async_update_entry(entry, data=new_data)

                # Reload the integration
                await self.hass.config_entries.async_reload(entry.entry_id)

        return self.async_create_entry(
            title="Authentication Updated",
            data={},
        )


class DeprecatedConfigRepairFlow(RepairsFlow):
    """Handle deprecated configuration repair."""

    def __init__(
        self,
        hass: HomeAssistant,
        issue_id: str,
        data: dict[str, Any] | None,
    ) -> None:
        """Initialize the repair flow."""
        super().__init__(hass, issue_id, data)

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                description_placeholders={
                    "deprecated_option": self.data.get("deprecated_option", "unknown"),
                    "new_option": self.data.get("new_option", "unknown"),
                },
            )

        # Update config entry to remove deprecated options
        entry_id = self.data.get("entry_id")
        if entry_id:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry:
                # Remove deprecated options
                new_options = dict(entry.options)
                deprecated_keys = self.data.get("deprecated_keys", [])

                for key in deprecated_keys:
                    new_options.pop(key, None)

                self.hass.config_entries.async_update_entry(entry, options=new_options)

        return self.async_create_entry(
            title="Configuration Updated",
            data={},
        )


class RateLimitRepairFlow(RepairsFlow):
    """Handle rate limit exceeded repair."""

    def __init__(
        self,
        hass: HomeAssistant,
        issue_id: str,
        data: dict[str, Any] | None,
    ) -> None:
        """Initialize the repair flow."""
        super().__init__(hass, issue_id, data)

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            current_interval = self.data.get("current_interval_minutes", 15)
            recommended_interval = max(30, current_interval * 2)

            return self.async_show_form(
                step_id="init",
                description_placeholders={
                    "current_interval": str(current_interval),
                    "recommended_interval": str(recommended_interval),
                },
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            "update_interval_minutes",
                            default=recommended_interval,
                        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    },
                ),
            )

        # Update config entry with new interval
        entry_id = self.data.get("entry_id")
        if entry_id:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry:
                new_options = dict(entry.options)
                new_options["rewards_scan_interval"] = user_input[
                    "update_interval_minutes"
                ]

                self.hass.config_entries.async_update_entry(entry, options=new_options)

                # Reload to apply new interval
                await self.hass.config_entries.async_reload(entry.entry_id)

        return self.async_create_entry(
            title="Update Interval Adjusted",
            data={},
        )


async def async_create_issue(
    hass: HomeAssistant,
    issue_id: str,
    issue_domain: str,
    is_fixable: bool = True,
    is_persistent: bool = False,
    learn_more_url: str | None = None,
    severity: ir.IssueSeverity = ir.IssueSeverity.WARNING,
    translation_key: str | None = None,
    translation_placeholders: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Create a repair issue."""
    ir.async_create_issue(
        hass,
        issue_domain,
        issue_id,
        is_fixable=is_fixable,
        is_persistent=is_persistent,
        learn_more_url=learn_more_url,
        severity=severity,
        translation_key=translation_key,
        translation_placeholders=translation_placeholders,
        data=data,
    )


async def async_delete_issue(
    hass: HomeAssistant,
    issue_id: str,
    issue_domain: str,
) -> None:
    """Delete a repair issue."""
    ir.async_delete_issue(hass, issue_domain, issue_id)
