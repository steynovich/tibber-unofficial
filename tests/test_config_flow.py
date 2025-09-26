"""Tests for the config flow."""

import pytest
from unittest.mock import AsyncMock, patch
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tibber_unofficial.const import DOMAIN


@pytest.mark.asyncio
async def test_form_valid_auth(mock_hass):
    """Test valid authentication in config flow."""

    with patch(
        "custom_components.tibber_unofficial.config_flow.TibberApiClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.authenticate = AsyncMock(return_value="test_token")
        instance.get_homes = AsyncMock(
            return_value=[
                {
                    "id": "home1",
                    "appNickname": "My Home",
                    "address": {"address1": "123 Test St"},
                },
                {
                    "id": "home2",
                    "appNickname": "Beach House",
                    "address": {"address1": "456 Ocean Ave"},
                },
            ]
        )

        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {}

        result2 = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "test_password",
            },
        )

        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Tibber (Home (home1))"
        assert result2["data"][CONF_USERNAME] == "test@example.com"


@pytest.mark.asyncio
async def test_form_invalid_auth(mock_hass):
    """Test invalid authentication in config flow."""

    with patch(
        "custom_components.tibber_unofficial.config_flow.TibberApiClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.authenticate = AsyncMock(
            side_effect=Exception("Authentication failed")
        )

        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "wrong_password",
            },
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_form_cannot_connect(mock_hass):
    """Test connection error in config flow."""

    with patch(
        "custom_components.tibber_unofficial.config_flow.TibberApiClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.authenticate = AsyncMock(side_effect=ConnectionError("Cannot connect"))

        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "test_password",
            },
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_home_selection(mock_hass):
    """Test home selection step."""

    with patch(
        "custom_components.tibber_unofficial.config_flow.TibberApiClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.authenticate = AsyncMock(return_value="test_token")
        instance.async_get_homes = AsyncMock(
            return_value=[
                {
                    "id": "home1",
                    "appNickname": "My Home",
                    "address": {"address1": "123 Test St"},
                    "hasSignedEnergyDeal": True,
                }
            ]
        )
        instance.async_get_gizmos = AsyncMock(return_value=[])

        # Start flow
        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Submit credentials
        result2 = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "test_password",
            },
        )

        # Should auto-select the only home
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert "test@example.com" in result2["title"] or "home1" in result2["title"]
        assert result2["data"][CONF_USERNAME] == "test@example.com"
        assert result2["data"]["home_id"] == "home1"


@pytest.mark.asyncio
async def test_already_configured(mock_hass, mock_config_entry):
    """Test that the same account cannot be added twice."""
    mock_config_entry.add_to_hass(mock_hass)

    with patch(
        "custom_components.tibber_unofficial.config_flow.TibberApiClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.authenticate = AsyncMock(return_value="test_token")
        instance.async_get_homes = AsyncMock(
            return_value=[
                {
                    "id": "96a14971-525a-4420-aae9-e5aedaa129ff",
                    "appNickname": "My Home",
                    "address": {"address1": "123 Test St"},
                    "hasSignedEnergyDeal": True,
                }
            ]
        )
        instance.async_get_gizmos = AsyncMock(return_value=[])

        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "test_password",
            },
        )

        # Should abort as already configured
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "already_configured"
