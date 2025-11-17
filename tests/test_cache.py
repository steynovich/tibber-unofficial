"""Tests for caching functionality."""

from datetime import UTC, datetime
import time
from unittest.mock import patch

from custom_components.tibber_unofficial.cache import ApiCache, SmartCache


def test_cache_basic_operations():
    """Test basic cache get/set operations."""
    cache = ApiCache(default_ttl=5)

    # Test cache miss
    result = cache.get("test_method", arg1="value1")
    assert result is None

    # Test cache set and hit
    test_data = {"result": "success"}
    cache.set("test_method", test_data, arg1="value1")

    result = cache.get("test_method", arg1="value1")
    assert result == test_data

    # Test different arguments create different keys
    result = cache.get("test_method", arg1="value2")
    assert result is None


def test_cache_expiration():
    """Test cache entry expiration."""
    cache = ApiCache(default_ttl=1)  # 1 second TTL

    test_data = {"result": "success"}
    cache.set("test_method", test_data)

    # Should hit while fresh
    result = cache.get("test_method")
    assert result == test_data

    # Wait for expiration
    time.sleep(1.1)

    # Should miss after expiration
    result = cache.get("test_method")
    assert result is None


def test_cache_custom_ttl():
    """Test custom TTL for specific entries."""
    cache = ApiCache(default_ttl=10)

    # Set with custom TTL
    cache.set("test_method", {"data": 1}, ttl=2)

    # Should be cached
    assert cache.get("test_method") is not None

    # Wait for custom TTL
    time.sleep(2.1)

    # Should be expired
    assert cache.get("test_method") is None


def test_cache_invalidation():
    """Test cache invalidation methods."""
    cache = ApiCache()

    # Add multiple entries
    cache.set("method1", {"data": 1}, key="a")
    cache.set("method1", {"data": 2}, key="b")
    cache.set("method2", {"data": 3}, key="c")

    # Verify all cached
    assert cache.get("method1", key="a") == {"data": 1}
    assert cache.get("method1", key="b") == {"data": 2}
    assert cache.get("method2", key="c") == {"data": 3}

    # Invalidate specific entry
    cache.invalidate("method1", key="a")
    assert cache.get("method1", key="a") is None
    assert cache.get("method1", key="b") == {"data": 2}

    # Clear all
    cache.invalidate()
    assert cache.get("method1", key="b") is None
    assert cache.get("method2", key="c") is None


def test_cache_stats():
    """Test cache statistics."""
    cache = ApiCache()

    # Initial stats
    stats = cache.get_stats()
    assert stats["entries"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0

    # Generate hits and misses
    cache.get("test")  # Miss
    cache.set("test", "data")
    cache.get("test")  # Hit
    cache.get("test")  # Hit
    cache.get("other")  # Miss

    stats = cache.get_stats()
    assert stats["entries"] == 1
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["hit_rate"] == 50.0


def test_cache_cleanup():
    """Test expired entry cleanup."""
    cache = ApiCache()

    # Add entries with different TTLs
    cache.set("short", "data1", ttl=1)
    cache.set("long", "data2", ttl=100)

    assert len(cache._cache) == 2

    # Wait for short to expire
    time.sleep(1.1)

    # Cleanup should remove expired
    cache.cleanup()
    assert len(cache._cache) == 1
    assert cache.get("long") == "data2"
    assert cache.get("short") is None


def test_smart_cache_ttl_selection():
    """Test SmartCache TTL selection by data type."""
    cache = SmartCache()

    # Test different data types get appropriate TTLs
    cache.set_smart("get_homes", {"homes": []}, "homes", user="test")
    cache.set_smart("get_gizmos", {"gizmos": []}, "gizmos", home="123")
    cache.set_smart("get_rewards", {"rewards": 100}, "rewards_daily", date="2024-01-01")

    # Check entries have different expiry times
    entries = cache._cache
    assert len(entries) == 3

    # Homes should have longest TTL (1 hour)
    homes_key = cache._make_key("get_homes", user="test")
    gizmos_key = cache._make_key("get_gizmos", home="123")
    rewards_key = cache._make_key("get_rewards", date="2024-01-01")

    homes_expiry = entries[homes_key][1]
    gizmos_expiry = entries[gizmos_key][1]
    rewards_expiry = entries[rewards_key][1]

    # Verify TTL ordering (homes > gizmos > daily rewards)
    assert homes_expiry > gizmos_expiry
    assert gizmos_expiry > rewards_expiry


@patch("custom_components.tibber_unofficial.cache.datetime")
def test_smart_cache_adaptive_ttl(mock_datetime):
    """Test SmartCache adaptive TTL based on time."""
    cache = SmartCache()

    # Test near end of day - should get shorter TTL
    mock_now = datetime(2024, 1, 15, 23, 0, 0, tzinfo=UTC)  # 11 PM UTC
    mock_datetime.now.return_value = mock_now

    cache.set_smart("get_rewards", {"rewards": 100}, "rewards_daily")

    # Check TTL is shortened
    key = list(cache._cache.keys())[0]
    _, expiry, cached_at = cache._cache[key]
    ttl = expiry - cached_at

    assert ttl == 60  # Should be 1 minute near midnight


def test_cache_key_consistency():
    """Test that cache keys are consistent regardless of argument order."""
    cache = ApiCache()

    cache.set("method", "data", arg1="a", arg2="b", arg3="c")

    # Should hit regardless of argument order
    assert cache.get("method", arg3="c", arg1="a", arg2="b") == "data"
    assert cache.get("method", arg2="b", arg3="c", arg1="a") == "data"
