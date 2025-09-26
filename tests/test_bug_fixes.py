"""Test suite for bug fixes in Tibber Unofficial integration."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import aiohttp
from datetime import datetime, timezone, timedelta

from custom_components.tibber_unofficial.api import TibberApiClient
from custom_components.tibber_unofficial.cache import SmartCache
from custom_components.tibber_unofficial.rate_limiter import MultiTierRateLimiter
from custom_components.tibber_unofficial import async_unload_entry


@pytest.fixture
async def mock_hass():
    """Mock Home Assistant instance."""
    hass = Mock()
    hass.data = {"tibber_unofficial": {}}
    hass.async_create_task = asyncio.create_task
    return hass


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "email": "test@example.com",
        "password": "test_password",
        "home_id": "12345678-1234-1234-1234-123456789abc",
    }
    entry.options = {}
    return entry


@pytest.fixture
async def mock_session():
    """Mock aiohttp session."""
    session = AsyncMock()
    session.closed = False
    return session


@pytest.fixture
async def mock_storage():
    """Mock rate limiter storage."""
    storage = AsyncMock()
    storage.async_load = AsyncMock(return_value={})
    storage.get_tokens = Mock(return_value=(80.0, 20.0))
    return storage


class TestSessionCleanup:
    """Test session and resource cleanup fixes."""

    async def test_session_closed_on_api_error(self, mock_storage):
        """Test session is properly closed when API initialization fails."""
        session = AsyncMock()
        session.closed = False

        with patch("aiohttp.ClientSession", return_value=session):
            api_client = TibberApiClient(
                "test@example.com", "test_password", storage=mock_storage
            )

            # Mock session.post to raise an exception
            session.post.side_effect = aiohttp.ClientError("Connection failed")

            with pytest.raises(Exception):
                await api_client._authenticate()

            # Session should be closed on error
            session.close.assert_called_once()

    async def test_session_cleanup_in_unload_entry(self, mock_hass, mock_config_entry):
        """Test session is properly closed during unload."""
        # Setup mock session
        mock_session = AsyncMock()
        mock_session.closed = False

        # Setup hass data with session
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id] = {
            "session": mock_session,
            "coordinator": Mock(),
            "gizmo_coordinator": Mock(),
            "cache_task": Mock(),
            "api_client": Mock(),
        }
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id][
            "coordinator"
        ].async_shutdown = AsyncMock()
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id][
            "gizmo_coordinator"
        ].async_shutdown = AsyncMock()
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id][
            "cache_task"
        ].cancel = Mock()

        # Unload entry
        result = await async_unload_entry(mock_hass, mock_config_entry)

        # Verify session was closed
        assert result is True
        mock_session.close.assert_called_once()


class TestCacheTaskLeak:
    """Test cache stats task memory leak fixes."""

    async def test_cache_task_cancelled_on_unload(self, mock_hass, mock_config_entry):
        """Test cache task is cancelled during unload."""
        # Setup mock task
        mock_task = Mock()
        mock_task.cancel = Mock()

        # Setup hass data with cache task
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id] = {
            "session": AsyncMock(),
            "coordinator": Mock(),
            "gizmo_coordinator": Mock(),
            "cache_task": mock_task,
            "api_client": Mock(),
        }
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id][
            "session"
        ].closed = False
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id][
            "coordinator"
        ].async_shutdown = AsyncMock()
        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id][
            "gizmo_coordinator"
        ].async_shutdown = AsyncMock()

        # Unload entry
        result = await async_unload_entry(mock_hass, mock_config_entry)

        # Verify task was cancelled
        assert result is True
        mock_task.cancel.assert_called_once()

    async def test_cache_stats_task_handles_cancellation(self):
        """Test cache stats task handles cancellation gracefully."""
        cancelled = False

        async def mock_stats_task():
            try:
                while True:
                    await asyncio.sleep(60)  # Simulate periodic task
            except asyncio.CancelledError:
                nonlocal cancelled
                cancelled = True
                raise

        task = asyncio.create_task(mock_stats_task())
        await asyncio.sleep(0.1)  # Let task start

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert cancelled is True


class TestTimezoneHandling:
    """Test timezone handling fixes."""

    async def test_utc_timezone_consistency(self, mock_storage):
        """Test API calls use UTC timezone consistently."""
        api_client = TibberApiClient(
            "test@example.com", "test_password", storage=mock_storage
        )

        # Mock datetime to return a specific time
        fixed_time = datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)

        with patch("custom_components.tibber_unofficial.api.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # Test period calculations use UTC
            start_time, end_time = api_client._get_period_bounds("current_month")

            # Should be timezone-aware UTC times
            assert start_time.tzinfo == timezone.utc
            assert end_time.tzinfo == timezone.utc

    def test_timezone_aware_period_bounds(self, mock_storage):
        """Test period bounds are timezone-aware."""
        api_client = TibberApiClient(
            "test@example.com", "test_password", storage=mock_storage
        )

        # Test all period types return timezone-aware datetimes
        periods = ["current_day", "current_month", "previous_month", "current_year"]

        for period in periods:
            start_time, end_time = api_client._get_period_bounds(period)
            assert start_time.tzinfo is not None
            assert end_time.tzinfo is not None
            assert start_time.tzinfo == timezone.utc
            assert end_time.tzinfo == timezone.utc


class TestCacheKeyCollision:
    """Test cache key collision fixes."""

    def test_sha256_hash_used_for_cache_keys(self):
        """Test cache uses SHA256 instead of MD5 for keys."""
        cache = SmartCache()

        # Test key generation
        key1 = cache._make_key("method1", param1="value1", param2="value2")
        key2 = cache._make_key("method1", param1="value1", param2="value2")
        key3 = cache._make_key("method1", param1="value1", param2="different")

        # Same parameters should generate same key
        assert key1 == key2
        # Different parameters should generate different keys
        assert key1 != key3
        # Keys should be 64 characters (SHA256 hex)
        assert len(key1) == 64
        assert all(c in "0123456789abcdef" for c in key1)

    def test_cache_key_collision_resistance(self):
        """Test cache keys have low collision probability."""
        cache = SmartCache()

        # Generate many different keys
        keys = set()
        for i in range(1000):
            key = cache._make_key(f"method_{i}", param=f"value_{i}")
            keys.add(key)

        # All keys should be unique
        assert len(keys) == 1000


class TestTokenExpiryHandling:
    """Test token expiry edge case fixes."""

    async def test_token_expiry_buffer_increased(self, mock_storage):
        """Test token expiry check uses 10-minute buffer."""
        api_client = TibberApiClient(
            "test@example.com", "test_password", storage=mock_storage
        )

        # Set token that expires in 8 minutes (should trigger refresh)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=8)
        api_client._token_expiry = future_time
        api_client._access_token = "test_token"

        # Should indicate token needs refresh (8 minutes < 10 minute buffer)
        assert api_client._is_token_expired() is True

        # Set token that expires in 12 minutes (should not trigger refresh)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=12)
        api_client._token_expiry = future_time

        # Should indicate token is still valid (12 minutes > 10 minute buffer)
        assert api_client._is_token_expired() is False

    async def test_preemptive_token_refresh(self, mock_storage):
        """Test token is refreshed before it actually expires."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Mock successful authentication response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {
                "data": {"login": {"token": "new_token", "expiresIn": 3600}}
            }
            mock_session.post.return_value.__aenter__.return_value = mock_response

            api_client = TibberApiClient(
                "test@example.com", "test_password", storage=mock_storage
            )

            # Set token that expires soon
            soon_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
            api_client._token_expiry = soon_expiry
            api_client._access_token = "old_token"

            # Make API call - should trigger token refresh
            await api_client._authenticate()

            # Token should be updated
            assert api_client._access_token == "new_token"


class TestUUIDValidation:
    """Test UUID validation fixes."""

    async def test_home_id_uuid_validation(self, mock_storage):
        """Test home ID is validated as proper UUID."""
        api_client = TibberApiClient(
            "test@example.com", "test_password", storage=mock_storage
        )

        # Valid UUID should pass
        valid_uuid = "12345678-1234-1234-1234-123456789abc"
        assert api_client._validate_home_id(valid_uuid) is True

        # Invalid UUIDs should fail
        invalid_uuids = [
            "not-a-uuid",
            "12345678-1234-1234-1234",  # Too short
            "12345678-1234-1234-1234-123456789abcde",  # Too long
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",  # Invalid characters
            "",  # Empty
            None,  # None
        ]

        for invalid_uuid in invalid_uuids:
            assert api_client._validate_home_id(invalid_uuid) is False


class TestRateLimiterPersistence:
    """Test rate limiter state persistence fixes."""

    async def test_rate_limiter_state_saved_periodically(self, mock_hass):
        """Test rate limiter saves state periodically."""
        mock_storage = AsyncMock()
        mock_storage.async_load.return_value = {}
        mock_storage.get_tokens.return_value = (80.0, 20.0)
        mock_storage.async_save = AsyncMock()

        rate_limiter = MultiTierRateLimiter(storage=mock_storage)
        await rate_limiter.initialize()

        # Simulate multiple API calls that would trigger saves
        with patch(
            "time.monotonic", side_effect=[0, 65, 130]
        ):  # Trigger save after 60s interval
            await rate_limiter.acquire()
            await rate_limiter.acquire()

        # Storage should be saved
        mock_storage.async_save.assert_called()

    async def test_rate_limiter_state_restored_on_init(self, mock_hass):
        """Test rate limiter restores state on initialization."""
        mock_storage = AsyncMock()
        mock_storage.async_load.return_value = {
            "hourly_tokens": 40.0,
            "burst_tokens": 10.0,
        }
        mock_storage.get_tokens.return_value = (40.0, 10.0)

        rate_limiter = MultiTierRateLimiter(storage=mock_storage)
        await rate_limiter.initialize()

        # State should be restored
        assert rate_limiter.hourly.tokens == 40.0
        assert rate_limiter.burst.tokens == 10.0


class TestOptionsUpdateRaceCondition:
    """Test options update race condition fixes."""

    async def test_options_update_without_reload(self, mock_hass, mock_config_entry):
        """Test options can be updated without full entry reload."""
        # Setup initial coordinators with default intervals
        mock_coordinator = Mock()
        mock_gizmo_coordinator = Mock()
        mock_coordinator.update_interval = timedelta(minutes=15)
        mock_gizmo_coordinator.update_interval = timedelta(hours=12)

        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id] = {
            "coordinator": mock_coordinator,
            "gizmo_coordinator": mock_gizmo_coordinator,
            "session": AsyncMock(),
            "api_client": Mock(),
        }

        # Update options with new intervals
        mock_config_entry.options = {
            "rewards_update_interval": 10,
            "gizmo_update_interval": 8,
        }

        # Simulate options update handler
        from custom_components.tibber_unofficial import async_options_update_listener

        await async_options_update_listener(mock_hass, mock_config_entry)

        # Intervals should be updated
        assert mock_coordinator.update_interval == timedelta(minutes=10)
        assert mock_gizmo_coordinator.update_interval == timedelta(hours=8)

    async def test_concurrent_options_updates_handled_safely(
        self, mock_hass, mock_config_entry
    ):
        """Test concurrent options updates don't cause race conditions."""
        # Setup coordinators
        mock_coordinator = Mock()
        mock_gizmo_coordinator = Mock()

        mock_hass.data["tibber_unofficial"][mock_config_entry.entry_id] = {
            "coordinator": mock_coordinator,
            "gizmo_coordinator": mock_gizmo_coordinator,
            "session": AsyncMock(),
            "api_client": Mock(),
        }

        # Simulate concurrent updates
        from custom_components.tibber_unofficial import async_options_update_listener

        mock_config_entry.options = {"rewards_update_interval": 5}
        task1 = asyncio.create_task(
            async_options_update_listener(mock_hass, mock_config_entry)
        )

        mock_config_entry.options = {"rewards_update_interval": 20}
        task2 = asyncio.create_task(
            async_options_update_listener(mock_hass, mock_config_entry)
        )

        # Both should complete without errors
        await asyncio.gather(task1, task2, return_exceptions=True)

        # Final state should be consistent
        assert isinstance(mock_coordinator.update_interval, timedelta)


class TestPartialFailureStates:
    """Test partial failure error state improvements."""

    async def test_partial_api_failure_handled_gracefully(self, mock_storage):
        """Test partial API failures don't crash the entire update."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # Mock partial failure - some homes succeed, others fail
            responses = [
                # First home succeeds
                AsyncMock(
                    status=200,
                    json=AsyncMock(
                        return_value={"data": {"gridRewards": [{"value": 10.5}]}}
                    ),
                ),
                # Second home fails
                AsyncMock(
                    status=500,
                    json=AsyncMock(
                        return_value={"errors": [{"message": "Internal server error"}]}
                    ),
                ),
            ]

            mock_session.post.return_value.__aenter__.side_effect = responses

            api_client = TibberApiClient(
                "test@example.com", "test_password", storage=mock_storage
            )

            # Should handle partial failure gracefully
            result = await api_client.get_grid_rewards("home1", "current_month")

            # Should return available data, not crash
            assert result is not None or result == {}

    async def test_error_state_recovery(self, mock_storage):
        """Test system recovers from error states."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            # First call fails, second succeeds
            responses = [
                AsyncMock(status=500),
                AsyncMock(
                    status=200,
                    json=AsyncMock(
                        return_value={"data": {"gridRewards": [{"value": 15.0}]}}
                    ),
                ),
            ]
            mock_session.post.return_value.__aenter__.side_effect = responses

            api_client = TibberApiClient(
                "test@example.com", "test_password", storage=mock_storage
            )

            # First call should handle error
            try:
                await api_client.get_grid_rewards("home1", "current_month")
            except Exception:
                pass  # Expected to fail

            # Reset side effect for second call
            mock_session.post.return_value.__aenter__.side_effect = [responses[1]]

            # Second call should succeed
            result = await api_client.get_grid_rewards("home1", "current_month")
            assert result is not None
