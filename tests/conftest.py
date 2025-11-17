"""Common test fixtures and configuration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MockConfigEntry(
        domain="tibber_unofficial",
        title="test@example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test_password",
            "home_id": "96a14971-525a-4420-aae9-e5aedaa129ff",
            "home_name": "Test Home",
            "bearer_token": "test_bearer_token",
        },
        unique_id="test@example.com",
    )


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    client = AsyncMock()
    client.authenticate = AsyncMock(return_value="test_bearer_token")
    client.async_get_homes = AsyncMock(
        return_value=[
            {
                "id": "96a14971-525a-4420-aae9-e5aedaa129ff",
                "appNickname": "Test Home",
                "address": {"address1": "Test Street 1"},
                "hasSignedEnergyDeal": True,
            }
        ]
    )
    client.async_get_gizmos = AsyncMock(
        return_value=[
            {"type": "HOMEVOLT", "name": "Homevolt Battery", "id": "gizmo1"},
            {"type": "ELECTRIC_VEHICLE", "name": "Test EV", "id": "gizmo2"},
        ]
    )

    # Mock grid rewards data
    mock_rewards = {
        "ev": 4.0,
        "homevolt": 6.5,
        "total": 10.5,
        "currency": "EUR",
        "from_date_api": datetime.now(UTC).isoformat(),
        "to_date_api": datetime.now(UTC).isoformat(),
    }
    client.async_get_grid_rewards_history = AsyncMock(return_value=mock_rewards)
    client.get_cache_stats = AsyncMock(
        return_value={
            "entries": 5,
            "hits": 10,
            "misses": 5,
            "hit_rate": 66.7,
            "total_requests": 15,
        }
    )
    return client


@pytest.fixture
def mock_hass(hass: HomeAssistant):
    """Return a mock Home Assistant instance."""
    return hass
