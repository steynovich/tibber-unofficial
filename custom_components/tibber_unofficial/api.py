"""API Client for Tibber Unofficial."""

from __future__ import annotations

import asyncio
import logging
import aiohttp
import random
import re
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from asyncio import sleep

from .rate_limiter import MultiTierRateLimiter
from .cache import SmartCache
from .const import (
    API_AUTH_URL,
    API_GRAPHQL_URL,
    HOMES_QUERY,
    GIZMOS_QUERY_TEMPLATE,
    GRID_REWARDS_QUERY_TEMPLATE,
    GRID_REWARDS_DAILY_QUERY_TEMPLATE,
)

_LOGGER = logging.getLogger(__name__)

# Compile UUID pattern once for performance
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Debug logging can be enabled in HA via:
# logger:
#   default: info
#   logs:
#     custom_components.tibber_unofficial: debug


class ApiError(Exception):
    """Generic API error."""

    pass


class ApiAuthError(ApiError):
    """API Authentication error."""

    pass


class TibberApiClient:
    """Client to interact with the Tibber API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str | None = None,
        password: str | None = None,
        token: str | None = None,
        storage: Any = None,
    ):
        """Initialize the API client.

        Args:
            session: aiohttp client session
            email: User email
            password: User password
            token: Optional existing token
            storage: Optional storage for rate limiter persistence
        """
        self._session = session
        self._email = email
        self._password = password
        self._token = token
        self._token_expiry_time: datetime | None = None
        self._max_retries = 3
        self._base_delay = 1.0  # Base delay in seconds for exponential backoff
        self._max_delay = 60.0  # Maximum delay between retries
        self._jitter_range = 0.3  # Add ±30% jitter to delays
        self._rate_limiter = MultiTierRateLimiter(storage=storage)
        self._cache = SmartCache()
        self._initialized = False
        self._auth_lock = asyncio.Lock()  # Prevent concurrent authentication
        # _LOGGER.debug("TibberApiClient initialized for email: %s", email) # Removed

    async def initialize(self) -> None:
        """Initialize rate limiter with stored state."""
        if not self._initialized:
            await self._rate_limiter.initialize()
            self._initialized = True

    async def _ensure_token(self) -> str:
        """Ensure a valid token is available, refreshing if necessary."""
        # Check token with 10 minute buffer for long-running requests
        if (
            self._token
            and self._token_expiry_time
            and datetime.now(timezone.utc)
            < self._token_expiry_time - timedelta(minutes=10)
        ):
            _LOGGER.debug(
                "Using cached token for %s (expires: %s)",
                self._email,
                self._token_expiry_time.isoformat(),
            )
            return self._token

        # Use lock to prevent concurrent authentication attempts
        async with self._auth_lock:
            # Check again after acquiring lock - another coroutine may have authenticated
            if (
                self._token
                and self._token_expiry_time
                and datetime.now(timezone.utc)
                < self._token_expiry_time - timedelta(minutes=10)
            ):
                _LOGGER.debug(
                    "Using token obtained by concurrent request for %s",
                    self._email,
                )
                return self._token

            _LOGGER.info(
                "Token is missing or expired for %s. Attempting to authenticate.",
                self._email,
            )  # Kept info for this key event
            if not self._email or not self._password:
                _LOGGER.error("Email or password not provided for authentication.")
                raise ApiAuthError("Email and password are required to fetch a new token.")

            # Validate email format
            if not isinstance(self._email, str) or "@" not in self._email:
                raise ApiAuthError("Invalid email format")
            if not isinstance(self._password, str) or not self._password:
                raise ApiAuthError("Invalid password")

            auth_payload = {"email": self._email, "password": self._password}
            headers = {"Content-Type": "application/json"}

            # Retry authentication with exponential backoff
            for attempt in range(self._max_retries):
                try:
                    _LOGGER.debug(
                        "Attempting authentication for %s (attempt %d/%d)",
                        self._email,
                        attempt + 1,
                        self._max_retries,
                    )
                    async with self._session.post(
                        API_AUTH_URL, headers=headers, json=auth_payload, timeout=10,
                    ) as response:
                        if response.status == 400 or response.status == 401:
                            responseText = await response.text()
                            _LOGGER.error(
                                "Authentication failed for %s - Status: %s, Response: %s",
                                self._email,
                                response.status,
                                responseText[:200],
                            )  # Limit response text
                            raise ApiAuthError(
                                "Authentication failed: Invalid email or password",
                            )
                        response.raise_for_status()
                        auth_data = await response.json()
                        # _LOGGER.debug("Authentication response data: %s", auth_data) # Removed

                        self._token = auth_data.get("token")
                        if not self._token:
                            _LOGGER.error(
                                "Token not found in authentication response: %s", auth_data,
                            )
                            raise ApiAuthError("Token not received from API.")

                        self._token_expiry_time = datetime.now(timezone.utc) + timedelta(
                            hours=1,
                        )
                        _LOGGER.info(
                            "Successfully authenticated %s - Token expires: %s",
                            self._email,
                            self._token_expiry_time.isoformat(),
                        )
                        _LOGGER.debug(
                            "Token obtained: %s...",
                            self._token[:10] if self._token else "None",
                        )
                        return self._token
                except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                    if attempt < self._max_retries - 1:
                        # Exponential backoff with jitter for auth retries
                        base_wait = min(self._base_delay * (2**attempt), self._max_delay)
                        jitter = base_wait * self._jitter_range * (2 * random.random() - 1)
                        wait_time = max(0.1, base_wait + jitter)
                        _LOGGER.warning(
                            "Authentication network error: %s. Retrying in %.2f seconds (attempt %s/%s)",
                            e,
                            wait_time,
                            attempt + 1,
                            self._max_retries,
                        )
                        await sleep(wait_time)
                    else:
                        _LOGGER.error(
                            "Error during authentication after %s retries: %s",
                            self._max_retries,
                            e,
                        )
                        raise ApiError(f"Error during authentication: {e}") from e
                except ApiAuthError:
                    raise  # Don't retry on auth errors (bad credentials)
                except Exception as e:
                    _LOGGER.exception("Unexpected error during authentication.")
                    raise ApiError(f"Unexpected error during authentication: {e}") from e

            # Should not reach here
            raise ApiError("Authentication failed after all retries")

    async def authenticate(self) -> None:
        """Explicitly authenticate and get a token (used by config flow)."""
        await self._ensure_token()

    async def _graphql_request(
        self, query: str, variables: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Make a GraphQL request to the Tibber API with retry logic."""
        # Ensure rate limiter is initialized
        if not self._initialized:
            await self.initialize()

        query_type = query.split("{")[0].strip() if "{" in query else "Unknown"
        _LOGGER.debug("GraphQL request: %s, Variables: %s", query_type, variables)

        # Apply rate limiting before making the request
        await self._rate_limiter.acquire()
        _LOGGER.debug("Rate limit acquired for request")

        last_exception = None

        for attempt in range(self._max_retries):
            try:
                token = await self._ensure_token()
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                }
                payload: Dict[str, Any] = {"query": query}
                if variables:
                    payload["variables"] = variables

                _LOGGER.debug(
                    "Sending request (attempt %d/%d) to %s",
                    attempt + 1,
                    self._max_retries,
                    API_GRAPHQL_URL,
                )

                async with self._session.post(
                    API_GRAPHQL_URL, headers=headers, json=payload, timeout=20,
                ) as response:
                    # _LOGGER.debug("GraphQL raw response status: %s", response.status) # Removed
                    _LOGGER.debug("Response status: %s", response.status)
                    if response.status >= 400:
                        raw_response_text_error = await response.text()
                        _LOGGER.warning(
                            "GraphQL request failed - Status: %s, Response: %s",
                            response.status,
                            raw_response_text_error[:500],
                        )  # Limit log size

                    if response.status == 401:  # Unauthorized
                        _LOGGER.warning(
                            "Token expired or invalid (401) - Re-authenticating %s",
                            self._email,
                        )
                        self._token = None
                        self._token_expiry_time = None
                        token = await self._ensure_token()
                        headers["Authorization"] = f"Bearer {token}"
                        _LOGGER.debug("Retrying request with new token")
                        async with self._session.post(
                            API_GRAPHQL_URL, headers=headers, json=payload, timeout=20,
                        ) as retry_response:
                            # _LOGGER.debug("GraphQL retry raw response status: %s", retry_response.status) # Removed
                            if retry_response.status >= 400:
                                raw_retry_response_text_error = (
                                    await retry_response.text()
                                )
                                _LOGGER.warning(
                                    "GraphQL retry request failed with status %s. Body: %s",
                                    retry_response.status,
                                    raw_retry_response_text_error,
                                )
                            retry_response.raise_for_status()
                            data = await retry_response.json()
                    elif response.status == 429:  # Rate limited
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            wait_time = float(retry_after)
                        else:
                            # Exponential backoff with jitter
                            base_wait = min(
                                self._base_delay * (2**attempt), self._max_delay,
                            )
                            jitter = (
                                base_wait
                                * self._jitter_range
                                * (2 * random.random() - 1)
                            )
                            wait_time = base_wait + jitter
                        _LOGGER.warning(
                            "Rate limited (429). Waiting %.2f seconds before retry %s/%s",
                            wait_time,
                            attempt + 1,
                            self._max_retries,
                        )
                        await sleep(wait_time)
                        continue
                    elif (
                        response.status >= 500
                    ):  # Server errors - retry with exponential backoff
                        if attempt < self._max_retries - 1:
                            # Exponential backoff with jitter and maximum delay
                            base_wait = min(
                                self._base_delay * (2**attempt), self._max_delay,
                            )
                            jitter = (
                                base_wait
                                * self._jitter_range
                                * (2 * random.random() - 1)
                            )
                            wait_time = base_wait + jitter
                            _LOGGER.warning(
                                "Server error (%s). Retrying in %.2f seconds (attempt %s/%s)",
                                response.status,
                                wait_time,
                                attempt + 1,
                                self._max_retries,
                            )
                            await sleep(wait_time)
                            continue
                        else:
                            response.raise_for_status()
                    else:
                        response.raise_for_status()
                        data = await response.json()

                    if "errors" in data and data["errors"]:
                        error_msgs = [
                            err.get("message", str(err)) for err in data["errors"]
                        ]
                        _LOGGER.error(
                            "GraphQL errors returned: %s", ", ".join(error_msgs),
                        )
                        raise ApiError(f"GraphQL query failed: {', '.join(error_msgs)}")

                    _LOGGER.debug("GraphQL request successful")
                    return data.get("data", {})

            except asyncio.TimeoutError as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    base_wait = min(self._base_delay * (2**attempt), self._max_delay)
                    jitter = base_wait * self._jitter_range * (2 * random.random() - 1)
                    wait_time = max(0.1, base_wait + jitter)
                    _LOGGER.warning(
                        "Request timeout after 20s - Retrying in %.2f seconds (attempt %d/%d)",
                        wait_time,
                        attempt + 1,
                        self._max_retries,
                    )
                    await sleep(wait_time)
                else:
                    _LOGGER.error(
                        "Request timeout after %d retries - Network may be slow or API unresponsive",
                        self._max_retries,
                    )
                    raise ApiError(
                        "Request timed out - Please check your network connection",
                    ) from e
            except aiohttp.ClientError as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    base_wait = min(self._base_delay * (2**attempt), self._max_delay)
                    jitter = base_wait * self._jitter_range * (2 * random.random() - 1)
                    wait_time = max(0.1, base_wait + jitter)
                    error_type = type(e).__name__
                    _LOGGER.warning(
                        "Network error (%s: %s) - Retrying in %.2f seconds (attempt %d/%d)",
                        error_type,
                        str(e),
                        wait_time,
                        attempt + 1,
                        self._max_retries,
                    )
                    await sleep(wait_time)
                else:
                    _LOGGER.error(
                        "Network error after %d retries: %s", self._max_retries, str(e),
                    )
                    raise ApiError(f"Network connection failed: {str(e)}") from e
            except ApiError:
                raise  # Don't retry on API errors (like auth errors)
            except Exception as e:
                _LOGGER.exception(
                    "Unexpected error during GraphQL request execution or parsing.",
                )
                raise ApiError(
                    f"An unexpected error occurred during GraphQL request: {e}",
                ) from e

        # If we get here, all retries failed
        if last_exception:
            raise ApiError(
                f"Failed after {self._max_retries} retries: {last_exception}",
            ) from last_exception
        raise ApiError(f"Failed after {self._max_retries} retries")

    async def async_get_homes(self) -> List[Dict[str, Any]]:
        """Fetch user's homes using GraphQL."""
        _LOGGER.debug("Fetching homes for user %s", self._email)

        # Check cache first
        cached_homes = self._cache.get("get_homes", email=self._email)
        if cached_homes is not None:
            _LOGGER.debug("Using cached homes data")
            return cached_homes

        try:
            response_data_field = await self._graphql_request(query=HOMES_QUERY)
            homes_list = response_data_field.get("me", {}).get("homes", [])
            if not isinstance(homes_list, list):
                _LOGGER.error("API response for homes is not a list.")
                return []

            # Validate home data structure
            valid_homes = []
            for home in homes_list:
                if isinstance(home, dict) and home.get("id"):
                    valid_homes.append(home)
                else:
                    _LOGGER.warning("Invalid home data structure: %s", home)

            _LOGGER.info("Found %d valid homes for %s", len(valid_homes), self._email)
            _LOGGER.debug(
                "Homes: %s",
                [
                    {"id": h.get("id"), "name": h.get("appNickname")}
                    for h in valid_homes
                ],
            )

            # Cache the homes data
            self._cache.set_smart("get_homes", valid_homes, "homes", email=self._email)
            return valid_homes
        except ApiError:
            raise  # Already logged by _graphql_request or _ensure_token
        except Exception as e:
            _LOGGER.exception(
                "Unexpected error fetching homes for %s: %s", self._email, str(e),
            )
            raise ApiError(f"Failed to fetch homes: {str(e)}") from e

    async def async_get_gizmos(self, home_id: str) -> List[Dict[str, Any]]:
        """Fetch gizmos for a specific home ID."""
        # Validate home_id
        if not home_id or not isinstance(home_id, str):
            _LOGGER.error("Invalid home_id provided: %s", home_id)
            raise ApiError("Invalid home_id - Must be a non-empty string")

        # Validate UUID format
        if not UUID_PATTERN.match(home_id):
            _LOGGER.error("Invalid home_id format (not UUID): %s", home_id[:8])
            raise ApiError("Invalid home_id - Must be a valid UUID")

        _LOGGER.debug(
            "Fetching gizmos for home %s", home_id[:8],
        )  # Log partial ID for privacy

        # Check cache first
        cached_gizmos = self._cache.get("get_gizmos", home_id=home_id)
        if cached_gizmos is not None:
            _LOGGER.debug("Using cached gizmos data")
            return cached_gizmos

        variables = {"homeId": home_id}
        try:
            response_data_field = await self._graphql_request(
                query=GIZMOS_QUERY_TEMPLATE, variables=variables,
            )
            gizmos_list = (
                response_data_field.get("me", {}).get("home", {}).get("gizmos", [])
            )
            if not isinstance(gizmos_list, list):
                _LOGGER.error(
                    "API response for gizmos is not a list for home %s.", home_id,
                )
                return []

            # Validate gizmo data structure
            valid_gizmos = []
            for gizmo in gizmos_list:
                if isinstance(gizmo, dict) and gizmo.get("type"):
                    valid_gizmos.append(gizmo)
                else:
                    _LOGGER.warning("Invalid gizmo data structure: %s", gizmo)

            _LOGGER.info(
                "Found %d valid gizmos for home %s", len(valid_gizmos), home_id[:8],
            )
            _LOGGER.debug(
                "Gizmos: %s",
                [
                    {
                        "type": g.get("type"),
                        "id": g.get("id")[:8] if g.get("id") else None,  # type: ignore[index]
                    }
                    for g in valid_gizmos
                ],
            )

            # Cache the gizmos data
            self._cache.set_smart("get_gizmos", valid_gizmos, "gizmos", home_id=home_id)
            return valid_gizmos
        except ApiError:
            raise
        except Exception as e:
            _LOGGER.exception(
                "Unexpected error fetching gizmos for home %s: %s", home_id[:8], str(e),
            )
            raise ApiError(f"Failed to fetch gizmos: {str(e)}") from e

    async def async_get_grid_rewards_history(
        self,
        home_id: str,
        from_date_str: str,
        to_date_str: str,
        use_daily_resolution: bool = False,
    ) -> Dict[str, Any]:
        """Fetch grid rewards history using GraphQL.

        Args:
            home_id: The ID of the home to fetch data for
            from_date_str: Start date in ISO format
            to_date_str: End date in ISO format
            use_daily_resolution: If True, use daily resolution instead of monthly
        """
        # Validate inputs
        if not home_id or not isinstance(home_id, str):
            raise ApiError("Invalid home_id provided")

        # Validate UUID format for home_id
        if not UUID_PATTERN.match(home_id):
            _LOGGER.error("Invalid home_id format in rewards history: %s", home_id[:8])
            raise ApiError("Invalid home_id - Must be a valid UUID")

        if not from_date_str or not isinstance(from_date_str, str):
            raise ApiError("Invalid from_date provided")
        if not to_date_str or not isinstance(to_date_str, str):
            raise ApiError("Invalid to_date provided")

        # Basic ISO date format validation
        try:
            datetime.fromisoformat(from_date_str.replace("Z", "+00:00"))
            datetime.fromisoformat(to_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise ApiError(f"Invalid date format: {e}")

        # Determine cache data type based on date range
        cache_type = "rewards_daily" if use_daily_resolution else "rewards_monthly"
        to_dt = datetime.fromisoformat(to_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        # Check if this is historical data (ended more than 1 day ago)
        if to_dt < now - timedelta(days=1):
            cache_type = "rewards_historical"

        # Check cache first
        cached_rewards = self._cache.get(
            "get_grid_rewards",
            home_id=home_id,
            from_date=from_date_str,
            to_date=to_date_str,
            resolution="daily" if use_daily_resolution else "monthly",
        )
        if cached_rewards is not None:
            _LOGGER.debug("Using cached rewards data for %s", cache_type)
            return cached_rewards

        variables = {
            "homeId": home_id,
            "fromDate": from_date_str,
            "toDate": to_date_str,
        }
        query_template = (
            GRID_REWARDS_DAILY_QUERY_TEMPLATE
            if use_daily_resolution
            else GRID_REWARDS_QUERY_TEMPLATE
        )
        response_data_field = await self._graphql_request(
            query=query_template, variables=variables,
        )
        default_return = {
            "ev": None,
            "homevolt": None,
            "total": None,
            "currency": None,
            "from_date_api": None,
            "to_date_api": None,
        }

        try:
            rewards_data_period = (
                response_data_field.get("me", {})
                .get("home", {})
                .get("gridRewardsHistoryPeriod")
            )
            if rewards_data_period is None:
                _LOGGER.warning(
                    "gridRewardsHistoryPeriod not found or is null for home %s (from: %s, to: %s).",
                    home_id,
                    from_date_str,
                    to_date_str,
                )
                return default_return

            result = {
                "ev": rewards_data_period.get("vehicleRewards"),
                "homevolt": rewards_data_period.get("batteryRewards"),
                "total": rewards_data_period.get("totalReward"),
                "currency": rewards_data_period.get("currency"),
                "from_date_api": rewards_data_period.get("from"),
                "to_date_api": rewards_data_period.get("to"),
            }

            # Cache the rewards data with appropriate TTL
            self._cache.set_smart(
                "get_grid_rewards",
                result,
                cache_type,
                home_id=home_id,
                from_date=from_date_str,
                to_date=to_date_str,
                resolution="daily" if use_daily_resolution else "monthly",
            )
            return result
        except Exception:
            _LOGGER.exception("Error parsing rewards data for home %s.", home_id)
            return default_return

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()
