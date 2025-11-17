"""Tests for data coordinators."""

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.tibber_unofficial import (
    GizmoUpdateCoordinator,
    GridRewardsCoordinator,
)


@pytest.mark.asyncio
async def test_grid_rewards_coordinator_update_success(mock_hass, mock_config_entry):
    """Test successful update of grid rewards coordinator."""
    mock_api = AsyncMock()
    mock_api.async_get_grid_rewards_history = AsyncMock()

    # Setup different returns based on resolution parameter
    def rewards_side_effect(home_id, from_date, to_date, use_daily_resolution=False):
        if use_daily_resolution:
            return {
                "ev": 1.0,
                "homevolt": 1.5,
                "total": 2.5,
                "currency": "EUR",
                "from_date_api": from_date,
                "to_date_api": to_date,
            }
        else:
            return {
                "ev": 20.0,
                "homevolt": 30.0,
                "total": 50.0,
                "currency": "EUR",
                "from_date_api": from_date,
                "to_date_api": to_date,
            }

    mock_api.async_get_grid_rewards_history.side_effect = rewards_side_effect
    mock_api.get_cache_stats = AsyncMock(
        return_value={"total_requests": 100, "hit_rate": 75.0}
    )

    coordinator = GridRewardsCoordinator(mock_hass, mock_api, mock_config_entry)

    data = await coordinator._async_update_data()

    assert data is not None
    # Check that the coordinator properly aggregates the data
    assert "grid_rewards_total_current_month" in data
    assert "grid_rewards_total_current_day" in data
    assert "currency" in data
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_grid_rewards_coordinator_auth_failed(mock_hass, mock_config_entry):
    """Test authentication failure in grid rewards coordinator."""
    from custom_components.tibber_unofficial.api import ApiAuthError

    mock_api = AsyncMock()
    mock_api.async_get_grid_rewards_history = AsyncMock(
        side_effect=ApiAuthError("Authentication failed: 401")
    )
    mock_api.get_cache_stats = AsyncMock(
        return_value={"total_requests": 0, "hit_rate": 0.0}
    )

    coordinator = GridRewardsCoordinator(mock_hass, mock_api, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_grid_rewards_coordinator_update_failed(mock_hass, mock_config_entry):
    """Test update failure in grid rewards coordinator."""
    from custom_components.tibber_unofficial.api import ApiError

    mock_api = AsyncMock()
    mock_api.async_get_grid_rewards_history = AsyncMock(
        side_effect=ApiError("Network error")
    )
    mock_api.get_cache_stats = AsyncMock(
        return_value={"total_requests": 0, "hit_rate": 0.0}
    )

    coordinator = GridRewardsCoordinator(mock_hass, mock_api, mock_config_entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_grid_rewards_coordinator_partial_failure(mock_hass, mock_config_entry):
    """Test partial failure handling in grid rewards coordinator."""
    mock_api = AsyncMock()

    call_count = 0

    def rewards_side_effect(home_id, from_date, to_date, use_daily_resolution=False):
        nonlocal call_count
        call_count += 1
        if use_daily_resolution:
            raise Exception("Daily query failed")
        return {
            "ev": 20.0,
            "homevolt": 30.0,
            "total": 50.0,
            "currency": "EUR",
            "from_date_api": from_date,
            "to_date_api": to_date,
        }

    mock_api.async_get_grid_rewards_history.side_effect = rewards_side_effect
    mock_api.get_cache_stats = AsyncMock(
        return_value={"total_requests": 0, "hit_rate": 0.0}
    )

    coordinator = GridRewardsCoordinator(mock_hass, mock_api, mock_config_entry)

    # The coordinator should handle the partial failure gracefully
    data = await coordinator._async_update_data()
    assert data is not None
    # Daily data should be None due to failure
    assert data.get("grid_rewards_total_current_day") is None
    # Monthly data should still be available
    assert data.get("grid_rewards_total_current_month") == 50.0


@pytest.mark.asyncio
async def test_gizmo_coordinator_update_success(mock_hass, mock_config_entry):
    """Test successful update of gizmo coordinator."""
    mock_api = AsyncMock()
    mock_api.async_get_gizmos = AsyncMock(
        return_value=[
            {"type": "HOMEVOLT", "name": "Battery", "id": "gizmo1"},
            {"type": "ELECTRIC_VEHICLE", "name": "Car", "id": "gizmo2"},
        ]
    )

    coordinator = GizmoUpdateCoordinator(mock_hass, mock_api, mock_config_entry)

    data = await coordinator._async_update_data()

    assert data is not None
    assert "HOMEVOLT" in data
    assert "ELECTRIC_VEHICLE" in data
    assert len(data["HOMEVOLT"]) == 1
    assert len(data["ELECTRIC_VEHICLE"]) == 1


@pytest.mark.asyncio
async def test_gizmo_coordinator_auth_failed(mock_hass, mock_config_entry):
    """Test authentication failure in gizmo coordinator."""
    from custom_components.tibber_unofficial.api import ApiAuthError

    mock_api = AsyncMock()
    mock_api.async_get_gizmos = AsyncMock(
        side_effect=ApiAuthError("Authentication failed: 401")
    )

    coordinator = GizmoUpdateCoordinator(mock_hass, mock_api, mock_config_entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_gizmo_coordinator_update_failed(mock_hass, mock_config_entry):
    """Test update failure in gizmo coordinator."""
    from custom_components.tibber_unofficial.api import ApiError

    mock_api = AsyncMock()
    mock_api.async_get_gizmos = AsyncMock(side_effect=ApiError("Network error"))

    coordinator = GizmoUpdateCoordinator(mock_hass, mock_api, mock_config_entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_update_intervals(mock_hass, mock_config_entry):
    """Test that coordinators have correct update intervals."""
    mock_api = AsyncMock()

    grid_coordinator = GridRewardsCoordinator(mock_hass, mock_api, mock_config_entry)

    gizmo_coordinator = GizmoUpdateCoordinator(mock_hass, mock_api, mock_config_entry)

    # Check update intervals
    assert grid_coordinator.update_interval == timedelta(minutes=15)
    assert gizmo_coordinator.update_interval == timedelta(hours=12)
