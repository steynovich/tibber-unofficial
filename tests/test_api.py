"""Tests for the Tibber API client."""

import pytest
from unittest.mock import AsyncMock, patch
from aiohttp import ClientError
from datetime import datetime, timezone, timedelta

from custom_components.tibber_unofficial.api import (
    TibberApiClient,
    ApiError,
    ApiAuthError,
)


@pytest.mark.asyncio
async def test_authenticate_success():
    """Test successful authentication."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "data": {"login": {"token": "test_bearer_token", "expiresIn": 3600}}
        }
    )

    mock_session.post.return_value.__aenter__.return_value = mock_response

    await client.authenticate()
    assert client._token == "test_bearer_token"


@pytest.mark.asyncio
async def test_authenticate_failure():
    """Test authentication failure."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="wrong_password"
    )

    mock_response = AsyncMock()
    mock_response.status = 401
    mock_response.text = AsyncMock(return_value="Invalid credentials")

    mock_session.post.return_value.__aenter__.return_value = mock_response

    with pytest.raises(ApiAuthError, match="Authentication failed"):
        await client.authenticate()


@pytest.mark.asyncio
async def test_get_homes_success():
    """Test getting homes successfully."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="password"
    )
    client._token = "test_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "data": {
                "me": {
                    "homes": [
                        {
                            "id": "home1",
                            "appNickname": "My Home",
                            "address": {"address1": "123 Test St"},
                        }
                    ]
                }
            }
        }
    )

    mock_session.post.return_value.__aenter__.return_value = mock_response

    homes = await client.async_get_homes()
    assert len(homes) == 1
    assert homes[0]["id"] == "home1"
    assert homes[0]["appNickname"] == "My Home"


@pytest.mark.asyncio
async def test_get_gizmos_success():
    """Test getting gizmos successfully."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="password"
    )
    client._token = "test_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "data": {
                "me": {
                    "home": {
                        "gizmos": [
                            {"type": "HOMEVOLT", "name": "Battery"},
                            {"type": "ELECTRIC_VEHICLE", "name": "Car"},
                        ]
                    }
                }
            }
        }
    )

    mock_session.post.return_value.__aenter__.return_value = mock_response

    gizmos = await client.async_get_gizmos("home1")
    assert len(gizmos) == 2
    assert gizmos[0]["type"] == "HOMEVOLT"
    assert gizmos[1]["type"] == "ELECTRIC_VEHICLE"


@pytest.mark.asyncio
async def test_get_grid_rewards_history_success():
    """Test getting grid rewards history successfully."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="password"
    )
    client._token = "test_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "data": {
                "me": {
                    "home": {
                        "gridRewardsHistoryPeriod": {
                            "vehicleRewards": 5.50,
                            "batteryRewards": 10.0,
                            "totalReward": 15.50,
                            "currency": "EUR",
                            "from": "2024-01-01T00:00:00Z",
                            "to": "2024-01-31T23:59:59Z",
                        }
                    }
                }
            }
        }
    )

    mock_session.post.return_value.__aenter__.return_value = mock_response

    rewards = await client.async_get_grid_rewards_history(
        "home1",
        "2024-01-01T00:00:00Z",
        "2024-01-31T23:59:59Z",
        use_daily_resolution=False,
    )
    assert rewards["total"] == 15.50
    assert rewards["currency"] == "EUR"
    assert rewards["ev"] == 5.50
    assert rewards["homevolt"] == 10.0


@pytest.mark.asyncio
async def test_cache_integration():
    """Test that caching reduces API calls."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="password"
    )
    client._token = "test_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "data": {"me": {"homes": [{"id": "home1", "appNickname": "My Home"}]}}
        }
    )

    mock_session.post.return_value.__aenter__.return_value = mock_response

    # First call should hit API
    homes1 = await client.async_get_homes()
    assert mock_session.post.call_count == 1

    # Second call should use cache
    homes2 = await client.async_get_homes()
    assert mock_session.post.call_count == 1  # No additional API call
    assert homes1 == homes2


@pytest.mark.asyncio
async def test_token_refresh_on_401():
    """Test automatic token refresh on 401 response."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="password"
    )
    client._token = "expired_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    # First call returns 401, triggers re-auth, then succeeds
    mock_response_401 = AsyncMock()
    mock_response_401.status = 401

    mock_response_auth = AsyncMock()
    mock_response_auth.status = 200
    mock_response_auth.json = AsyncMock(return_value={"token": "new_token"})

    mock_response_success = AsyncMock()
    mock_response_success.status = 200
    mock_response_success.json = AsyncMock(
        return_value={
            "data": {
                "me": {
                    "home": {
                        "gridRewardsHistoryPeriod": {
                            "totalReward": 10.0,
                            "currency": "EUR",
                        }
                    }
                }
            }
        }
    )

    # Setup response sequence
    responses = [mock_response_401, mock_response_auth, mock_response_success]
    mock_session.post.return_value.__aenter__.side_effect = responses

    result = await client.async_get_grid_rewards_history(
        "home1", "2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z"
    )
    assert client._token == "new_token"
    assert result["total"] == 10.0


@pytest.mark.asyncio
async def test_api_error_handling():
    """Test handling of API errors."""
    mock_session = AsyncMock()
    client = TibberApiClient(
        session=mock_session, email="test@example.com", password="password"
    )
    client._token = "test_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_session.post.side_effect = ClientError()

    with pytest.raises(ApiError):
        await client.async_get_grid_rewards_history(
            "home1", "2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z"
        )


@pytest.mark.asyncio
async def test_uuid_validation():
    """Test UUID validation for home IDs."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    # Test valid UUID
    valid_uuid = "12345678-1234-1234-1234-123456789abc"
    assert client._validate_home_id(valid_uuid) is True

    # Test invalid UUIDs
    invalid_uuids = [
        "not-a-uuid",
        "12345678-1234-1234-1234",  # Too short
        "12345678-1234-1234-1234-123456789abcde",  # Too long
        "",  # Empty
        None,  # None
    ]

    for invalid_uuid in invalid_uuids:
        assert client._validate_home_id(invalid_uuid) is False


@pytest.mark.asyncio
async def test_rate_limiter_integration():
    """Test rate limiter integration with API client."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    mock_storage.async_load = AsyncMock()
    mock_storage.get_tokens = AsyncMock(return_value=(80.0, 20.0))

    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    # Initialize client
    await client.initialize()

    # Verify rate limiter was initialized
    assert client._initialized is True
    mock_storage.async_load.assert_called_once()


@pytest.mark.asyncio
async def test_token_expiry_buffer():
    """Test token expiry uses 10-minute buffer."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    from datetime import timedelta

    # Set token that expires in 8 minutes (should trigger refresh)
    future_time = datetime.now(timezone.utc) + timedelta(minutes=8)
    client._token_expiry_time = future_time
    client._access_token = "test_token"

    # Should indicate token needs refresh (8 minutes < 10 minute buffer)
    assert client._is_token_expired() is True

    # Set token that expires in 12 minutes (should not trigger refresh)
    future_time = datetime.now(timezone.utc) + timedelta(minutes=12)
    client._token_expiry_time = future_time

    # Should indicate token is still valid (12 minutes > 10 minute buffer)
    assert client._is_token_expired() is False


@pytest.mark.asyncio
async def test_cache_stats():
    """Test cache statistics functionality."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    # Get initial cache stats
    stats = client.get_cache_stats()

    assert "entries" in stats
    assert "hits" in stats
    assert "misses" in stats
    assert "hit_rate" in stats
    assert "total_requests" in stats

    # Initially should have no stats
    assert stats["total_requests"] == 0
    assert stats["hit_rate"] == 0


@pytest.mark.asyncio
async def test_home_id_validation_in_methods():
    """Test home ID validation in API methods."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    # Test invalid home ID in get_gizmos
    with pytest.raises(ApiError, match="Invalid home_id"):
        await client.get_gizmos("invalid-uuid")

    # Test invalid home ID in get_grid_rewards
    with pytest.raises(ApiError, match="Invalid home_id"):
        await client.get_grid_rewards("invalid-uuid", "current_month")


@pytest.mark.asyncio
async def test_period_bounds_timezone_aware():
    """Test period bounds return timezone-aware datetimes."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    periods = ["current_day", "current_month", "previous_month", "current_year"]

    for period in periods:
        start_time, end_time = client._get_period_bounds(period)

        # Should be timezone-aware UTC times
        assert start_time.tzinfo is not None
        assert end_time.tzinfo is not None
        assert start_time.tzinfo == timezone.utc
        assert end_time.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_retry_mechanism_with_exponential_backoff():
    """Test retry mechanism with exponential backoff."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    client._token = "test_token"
    client._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

    # Mock responses: fail twice, then succeed
    mock_response_fail = AsyncMock()
    mock_response_fail.status = 500

    mock_response_success = AsyncMock()
    mock_response_success.status = 200
    mock_response_success.json = AsyncMock(return_value={"data": {"me": {"homes": []}}})

    responses = [mock_response_fail, mock_response_fail, mock_response_success]
    mock_session.post.return_value.__aenter__.side_effect = responses

    # Should eventually succeed after retries
    with patch("asyncio.sleep") as mock_sleep:  # Speed up test by mocking sleep
        result = await client._graphql_request("query { me { homes { id } } }")

        # Should have retried and eventually succeeded
        assert mock_session.post.call_count == 3
        assert mock_sleep.call_count == 2  # Two retries with sleep
        assert result["data"]["me"]["homes"] == []


@pytest.mark.asyncio
async def test_smart_cache_integration():
    """Test smart cache with different TTL for data types."""
    mock_session = AsyncMock()
    mock_storage = AsyncMock()
    client = TibberApiClient(
        session=mock_session,
        email="test@example.com",
        password="password",
        storage=mock_storage,
    )

    # Verify smart cache is being used
    assert hasattr(client._cache, "set_smart")
    assert hasattr(client._cache, "ttl_config")

    # Verify TTL configuration for different data types
    ttl_config = client._cache.ttl_config
    assert "homes" in ttl_config
    assert "gizmos" in ttl_config
    assert "rewards_daily" in ttl_config
    assert "rewards_monthly" in ttl_config
