"""Test suite for Gold standard features in Tibber Unofficial integration."""

import asyncio
from datetime import UTC, datetime
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.tibber_unofficial import async_setup_entry, async_unload_entry
from custom_components.tibber_unofficial.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from custom_components.tibber_unofficial.repairs import (
    AuthFailedRepairFlow,
    DeprecatedConfigRepairFlow,
    RateLimitRepairFlow,
    async_create_issue,
    async_delete_issue,
)
from custom_components.tibber_unofficial.services import (
    async_setup_services,
    async_unload_services,
)


@pytest.fixture
async def mock_hass():
    """Mock Home Assistant instance."""
    hass = Mock()
    hass.data = {"tibber_unofficial": {}}
    hass.async_create_task = asyncio.create_task
    hass.config = Mock()
    hass.config.version = "2025.1.0"
    hass.services = Mock()
    hass.services.has_service = Mock(return_value=False)
    hass.services.async_register = Mock()
    hass.services.async_remove = Mock()

    # Mock helpers
    hass.helpers = Mock()
    hass.helpers.entity_registry = Mock()
    hass.helpers.device_registry = Mock()

    return hass


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.title = "Test Tibber"
    entry.version = "2025.06.1"
    entry.domain = "tibber_unofficial"
    entry.state = Mock()
    entry.state.value = "loaded"
    entry.data = {
        "email": "test@example.com",
        "password": "test_password",
        "home_id": "12345678-1234-1234-1234-123456789abc",
    }
    entry.options = {"rewards_scan_interval": 15, "gizmo_scan_interval": 12}
    return entry


class TestDiagnostics:
    """Test diagnostics functionality."""

    async def test_config_entry_diagnostics_basic(self, mock_hass, mock_config_entry):
        """Test basic config entry diagnostics."""
        # Setup mock coordinators and API client
        mock_rewards_coordinator = Mock()
        mock_rewards_coordinator.last_update_success = True
        mock_rewards_coordinator.last_exception = None
        mock_rewards_coordinator.update_interval = Mock()
        mock_rewards_coordinator.update_interval.__str__ = Mock(return_value="0:15:00")
        mock_rewards_coordinator.last_update_success_time = datetime.now(UTC)
        mock_rewards_coordinator.data = {"test_key": "test_value"}
        mock_rewards_coordinator.home_id = "12345678-1234-1234-1234-123456789abc"

        mock_api_client = Mock()
        mock_api_client._initialized = True
        mock_api_client._token = "test_token"
        mock_api_client._token_expiry_time = datetime.now(UTC)
        mock_api_client.get_cache_stats = Mock(
            return_value={"entries": 5, "hits": 10, "misses": 2, "hit_rate": 83.3}
        )
        mock_api_client._rate_limiter = Mock()
        mock_api_client._rate_limiter.hourly = Mock()
        mock_api_client._rate_limiter.hourly.tokens = 75.5
        mock_api_client._rate_limiter.burst = Mock()
        mock_api_client._rate_limiter.burst.tokens = 18.2

        mock_hass.data["tibber_unofficial"]["test_entry_id"] = {
            "coordinator_rewards": mock_rewards_coordinator,
            "api_client": mock_api_client,
        }

        # Mock entity and device registries
        mock_entity_registry = Mock()
        mock_entity_registry.async_entries_for_config_entry = Mock(return_value=[])
        mock_hass.helpers.entity_registry.async_get = Mock(
            return_value=mock_entity_registry
        )

        mock_device_registry = Mock()
        mock_device_registry.async_entries_for_config_entry = Mock(return_value=[])
        mock_hass.helpers.device_registry.async_get = Mock(
            return_value=mock_device_registry
        )

        # Get diagnostics
        diagnostics = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        # Verify structure
        assert "entry" in diagnostics
        assert "coordinators" in diagnostics
        assert "api_client" in diagnostics
        assert "system_info" in diagnostics
        assert "entities" in diagnostics
        assert "devices" in diagnostics

        # Verify entry data is redacted
        assert diagnostics["entry"]["data"]["email"] == "**REDACTED**"
        assert diagnostics["entry"]["data"]["password"] == "**REDACTED**"

        # Verify coordinator data
        assert diagnostics["coordinators"]["rewards"]["last_update_success"] is True
        assert "test_key" in diagnostics["coordinators"]["rewards"]["data_keys"]

        # Verify API client data
        assert diagnostics["api_client"]["initialized"] is True
        assert diagnostics["api_client"]["has_token"] is True
        assert diagnostics["api_client"]["cache_stats"]["entries"] == 5

    async def test_device_diagnostics(self, mock_hass, mock_config_entry):
        """Test device-specific diagnostics."""
        mock_device = Mock()
        mock_device.id = "device_id"
        mock_device.identifiers = {("tibber_unofficial", "test_entry_id")}

        # Setup mock data
        mock_hass.data["tibber_unofficial"]["test_entry_id"] = {
            "coordinator_rewards": Mock(),
            "api_client": Mock(),
        }

        # Mock registries
        mock_entity_registry = Mock()
        mock_entity_registry.async_entries_for_device = Mock(return_value=[])
        mock_hass.helpers.entity_registry.async_get = Mock(
            return_value=mock_entity_registry
        )

        mock_device_registry = Mock()
        mock_device_registry.async_entries_for_config_entry = Mock(
            return_value=[
                {
                    "name": "Test Device",
                    "identifiers": [("tibber_unofficial", "test_entry_id")],
                }
            ]
        )
        mock_hass.helpers.device_registry.async_get = Mock(
            return_value=mock_device_registry
        )

        # Mock config entry diagnostics
        with patch(
            "custom_components.tibber_unofficial.diagnostics.async_get_config_entry_diagnostics"
        ) as mock_get_config:
            mock_get_config.return_value = {
                "devices": [
                    {
                        "name": "Test Device",
                        "identifiers": [("tibber_unofficial", "test_entry_id")],
                    }
                ],
                "entities": [],
                "system_info": {"timestamp": "2024-01-01T00:00:00Z"},
            }

            diagnostics = await async_get_device_diagnostics(
                mock_hass, mock_config_entry, mock_device
            )

            assert "device" in diagnostics
            assert "entities" in diagnostics
            assert "system_info" in diagnostics


class TestRepairs:
    """Test repair flow functionality."""

    async def test_auth_failed_repair_flow(self, mock_hass):
        """Test authentication failed repair flow."""
        issue_data = {"entry_id": "test_entry_id", "entry_title": "Test Integration"}

        repair_flow = AuthFailedRepairFlow(mock_hass, "auth_failed", issue_data)

        # Test initial step
        result = await repair_flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "init"
        assert "email" in result["data_schema"].schema
        assert "password" in result["data_schema"].schema

    async def test_rate_limit_repair_flow(self, mock_hass):
        """Test rate limit exceeded repair flow."""
        issue_data = {"entry_id": "test_entry_id", "current_interval_minutes": 15}

        repair_flow = RateLimitRepairFlow(mock_hass, "rate_limit_exceeded", issue_data)

        # Test initial step
        result = await repair_flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "init"
        assert "update_interval_minutes" in result["data_schema"].schema

    async def test_deprecated_config_repair_flow(self, mock_hass):
        """Test deprecated configuration repair flow."""
        issue_data = {
            "entry_id": "test_entry_id",
            "deprecated_option": "old_setting",
            "new_option": "new_setting",
        }

        repair_flow = DeprecatedConfigRepairFlow(
            mock_hass, "deprecated_config", issue_data
        )

        # Test initial step
        result = await repair_flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    async def test_create_and_delete_issue(self, mock_hass):
        """Test issue creation and deletion."""
        with (
            patch(
                "homeassistant.helpers.issue_registry.async_create_issue"
            ) as mock_create,
            patch(
                "homeassistant.helpers.issue_registry.async_delete_issue"
            ) as mock_delete,
        ):
            # Create issue
            await async_create_issue(
                mock_hass,
                "test_issue",
                "test_domain",
                translation_key="test_key",
                data={"test": "data"},
            )
            mock_create.assert_called_once()

            # Delete issue
            await async_delete_issue(mock_hass, "test_issue", "test_domain")
            mock_delete.assert_called_once()


class TestServices:
    """Test service functionality."""

    async def test_setup_services(self, mock_hass):
        """Test service setup."""
        await async_setup_services(mock_hass)

        # Verify services were registered
        assert mock_hass.services.async_register.call_count == 2

        # Check service names
        calls = mock_hass.services.async_register.call_args_list
        service_names = [call[0][1] for call in calls]
        assert "refresh_rewards" in service_names
        assert "clear_cache" in service_names

    async def test_unload_services(self, mock_hass):
        """Test service unload."""
        await async_unload_services(mock_hass)

        # Verify services were removed
        assert mock_hass.services.async_remove.call_count == 2

    async def test_refresh_rewards_service(self, mock_hass):
        """Test refresh rewards service call."""
        # Setup mock coordinator
        mock_coordinator = AsyncMock()
        mock_coordinator.async_request_refresh = AsyncMock()

        mock_hass.data["tibber_unofficial"]["test_entry"] = {
            "coordinator_rewards": mock_coordinator
        }

        # Setup services
        await async_setup_services(mock_hass)

        # Get the service handler
        refresh_service = None
        for call in mock_hass.services.async_register.call_args_list:
            if call[0][1] == "refresh_rewards":
                refresh_service = call[0][2]
                break

        assert refresh_service is not None

        # Mock service call
        mock_call = Mock()
        mock_call.data = {}

        # Call service
        await refresh_service(mock_call)

        # Verify coordinator was called
        mock_coordinator.async_request_refresh.assert_called_once()

    async def test_clear_cache_service(self, mock_hass):
        """Test clear cache service call."""
        # Setup mock API client
        mock_api_client = Mock()
        mock_cache = Mock()
        mock_cache.invalidate = Mock()
        mock_api_client._cache = mock_cache

        mock_hass.data["tibber_unofficial"]["test_entry"] = {
            "api_client": mock_api_client
        }

        # Setup services
        await async_setup_services(mock_hass)

        # Get the service handler
        clear_cache_service = None
        for call in mock_hass.services.async_register.call_args_list:
            if call[0][1] == "clear_cache":
                clear_cache_service = call[0][2]
                break

        assert clear_cache_service is not None

        # Mock service call
        mock_call = Mock()
        mock_call.data = {}

        # Call service
        await clear_cache_service(mock_call)

        # Verify cache was cleared
        mock_cache.invalidate.assert_called_once()


@pytest.mark.gold_standard
class TestGoldStandardIntegration:
    """Test Gold standard integration features."""

    async def test_service_lifecycle_in_setup_unload(
        self, mock_hass, mock_config_entry
    ):
        """Test services are properly managed during setup and unload."""
        # Mock the API client initialization
        with (
            patch(
                "custom_components.tibber_unofficial.TibberApiClient"
            ) as mock_api_class,
            patch(
                "custom_components.tibber_unofficial.RateLimiterStorage"
            ) as mock_storage_class,
            patch("aiohttp.ClientSession"),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.initialize = AsyncMock()
            mock_api_class.return_value = mock_api_instance

            mock_storage_instance = AsyncMock()
            mock_storage_class.return_value = mock_storage_instance

            # Setup entry
            result = await async_setup_entry(mock_hass, mock_config_entry)
            assert result is True

            # Verify services were set up
            mock_hass.services.async_register.assert_called()

            # Mock unload
            mock_hass.config_entries = Mock()
            mock_hass.config_entries.async_unload_platforms = AsyncMock(
                return_value=True
            )

            # Unload entry
            result = await async_unload_entry(mock_hass, mock_config_entry)
            assert result is True

    async def test_repair_issue_creation_on_auth_error(
        self, mock_hass, mock_config_entry
    ):
        """Test repair issues are created on authentication errors."""
        with patch(
            "custom_components.tibber_unofficial.repairs.async_create_issue"
        ) as mock_create_issue:
            from custom_components.tibber_unofficial import GridRewardsCoordinator
            from custom_components.tibber_unofficial.api import ApiAuthError

            # Create coordinator
            mock_api_client = AsyncMock()
            coordinator = GridRewardsCoordinator(
                mock_hass, mock_api_client, "test_home_id"
            )
            coordinator.config_entry = mock_config_entry

            # Mock API client to raise auth error
            mock_api_client.get_grid_rewards_history.side_effect = ApiAuthError(
                "Auth failed"
            )

            # Trigger update that should fail
            with pytest.raises(Exception):  # ConfigEntryAuthFailed
                await coordinator._async_update_data()

            # Verify repair issue was created
            mock_create_issue.assert_called_once()
            call_args = mock_create_issue.call_args
            assert call_args[0][1] == "auth_failed"  # issue_id

    async def test_translation_strings_structure(self):
        """Test translation strings have proper structure."""

        # Read strings.json
        strings_path = "/Users/steyn/projects/tibber-unofficial/custom_components/tibber_unofficial/strings.json"

        with open(strings_path) as f:
            strings = json.load(f)

        # Verify required sections exist
        required_sections = ["config", "options", "entity", "issues", "services"]
        for section in required_sections:
            assert section in strings, f"Missing section: {section}"

        # Verify config flow strings
        assert "step" in strings["config"]
        assert "user" in strings["config"]["step"]
        assert "homes" in strings["config"]["step"]
        assert "error" in strings["config"]

        # Verify entity strings
        assert "sensor" in strings["entity"]
        sensor_keys = list(strings["entity"]["sensor"].keys())
        assert len(sensor_keys) >= 12  # Should have all sensor translations

        # Verify issues section for repairs
        assert "auth_failed" in strings["issues"]
        assert "rate_limit_exceeded" in strings["issues"]
        assert "fix_flow" in strings["issues"]["auth_failed"]

        # Verify services section
        assert "refresh_rewards" in strings["services"]
        assert "clear_cache" in strings["services"]

    async def test_manifest_gold_compliance(self):
        """Test manifest.json declares Gold standard compliance."""

        manifest_path = "/Users/steyn/projects/tibber-unofficial/custom_components/tibber_unofficial/manifest.json"

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Verify Gold standard declaration
        assert "quality_scale" in manifest
        assert manifest["quality_scale"] == "gold"

        # Verify integration type
        assert "integration_type" in manifest
        assert manifest["integration_type"] == "service"

        # Verify required fields are present
        required_fields = [
            "domain",
            "name",
            "codeowners",
            "config_flow",
            "dependencies",
            "documentation",
            "iot_class",
            "issue_tracker",
            "requirements",
            "version",
        ]

        for field in required_fields:
            assert field in manifest, f"Missing required field: {field}"

    async def test_sensor_gold_standard_attributes(self):
        """Test sensors have Gold standard attributes."""
        from custom_components.tibber_unofficial.sensor import GridRewardComponentSensor

        # Create mock coordinator
        mock_coordinator = Mock()
        mock_coordinator.data = {"test_key": 25.50, "currency": "EUR"}

        # Create sensor
        sensor = GridRewardComponentSensor(
            coordinator=mock_coordinator,
            config_entry_id="test_entry",
            data_key="test_key",
            name_suffix="Test Sensor",
            icon="mdi:test",
            period_from_key="from_key",
            period_to_key="to_key",
        )

        # Verify Gold standard attributes
        assert hasattr(sensor, "_attr_suggested_display_precision")
        assert sensor._attr_suggested_display_precision == 2
        assert hasattr(sensor, "_attr_has_entity_name")
        assert sensor._attr_has_entity_name is True

        # Verify device info has Gold standard fields
        device_info = sensor.device_info
        assert "configuration_url" in device_info
        assert "entry_type" in device_info
        assert device_info["entry_type"] == "service"
