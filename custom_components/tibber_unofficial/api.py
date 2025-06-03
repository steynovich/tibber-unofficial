"""API Client for Tibber Unofficial."""
import asyncio
import logging
import aiohttp
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from .const import (
    API_AUTH_URL,
    API_GRAPHQL_URL,
    HOMES_QUERY,
    GIZMOS_QUERY_TEMPLATE,
    GRID_REWARDS_QUERY_TEMPLATE,
)

_LOGGER = logging.getLogger(__name__) # Kept for error/warning logging

class ApiError(Exception):
    """Generic API error."""
    pass

class ApiAuthError(ApiError):
    """API Authentication error."""
    pass

class TibberApiClient:
    """Client to interact with the Tibber API."""

    def __init__(self, session: aiohttp.ClientSession, email: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None):
        """Initialize the API client."""
        self._session = session
        self._email = email
        self._password = password
        self._token = token
        self._token_expiry_time: Optional[datetime] = None
        # _LOGGER.debug("TibberApiClient initialized for email: %s", email) # Removed

    async def _ensure_token(self) -> str:
        """Ensure a valid token is available, refreshing if necessary."""
        if self._token and self._token_expiry_time and datetime.now(timezone.utc) < self._token_expiry_time - timedelta(minutes=5):
            # _LOGGER.debug("Using existing valid token.") # Removed
            return self._token

        _LOGGER.info("Token is missing or expired for %s. Attempting to authenticate.", self._email) # Kept info for this key event
        if not self._email or not self._password:
            _LOGGER.error("Email or password not provided for authentication.")
            raise ApiAuthError("Email and password are required to fetch a new token.")

        auth_payload = {"email": self._email, "password": self._password}
        headers = {"Content-Type": "application/json"}

        try:
            async with self._session.post(API_AUTH_URL, headers=headers, json=auth_payload, timeout=10) as response:
                if response.status == 400 or response.status == 401:
                    responseText = await response.text()
                    _LOGGER.error("Authentication failed with status %s: %s", response.status, responseText)
                    raise ApiAuthError(f"Invalid credentials. API response: {responseText}")
                response.raise_for_status()
                auth_data = await response.json()
                # _LOGGER.debug("Authentication response data: %s", auth_data) # Removed

                self._token = auth_data.get("token")
                if not self._token:
                    _LOGGER.error("Token not found in authentication response: %s", auth_data)
                    raise ApiAuthError("Token not received from API.")

                self._token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)
                _LOGGER.info("Successfully authenticated and obtained new token for %s.", self._email) # Kept info
                return self._token
        except (asyncio.TimeoutError, aiohttp.ClientError) as e: # Combined some exception groups
            _LOGGER.error("Error during authentication: %s", e)
            raise ApiError(f"Error during authentication: {e}") from e
        except Exception as e: # Catch any other unexpected error during auth
            _LOGGER.exception("Unexpected error during authentication.")
            raise ApiError(f"Unexpected error during authentication: {e}") from e

    async def authenticate(self):
        """Explicitly authenticate and get a token (used by config flow)."""
        await self._ensure_token()

    async def _graphql_request(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GraphQL request to the Tibber API, supporting variables."""
        token = await self._ensure_token()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        
        # _LOGGER.debug("Sending GraphQL request (variables: %s)", variables) # Removed
        
        try:
            async with self._session.post(API_GRAPHQL_URL, headers=headers, json=payload, timeout=20) as response:
                # _LOGGER.debug("GraphQL raw response status: %s", response.status) # Removed
                if response.status >= 400:
                    raw_response_text_error = await response.text()
                    _LOGGER.warning("GraphQL request failed with status %s. Body: %s", response.status, raw_response_text_error)

                if response.status == 401: # Unauthorized
                    _LOGGER.warning("GraphQL request failed with 401. Re-authenticating.")
                    self._token = None
                    self._token_expiry_time = None
                    token = await self._ensure_token()
                    headers["Authorization"] = f"Bearer {token}"
                    # _LOGGER.debug("Retrying GraphQL request with new token.") # Removed
                    async with self._session.post(API_GRAPHQL_URL, headers=headers, json=payload, timeout=20) as retry_response:
                        # _LOGGER.debug("GraphQL retry raw response status: %s", retry_response.status) # Removed
                        if retry_response.status >= 400:
                            raw_retry_response_text_error = await retry_response.text()
                            _LOGGER.warning("GraphQL retry request failed with status %s. Body: %s", retry_response.status, raw_retry_response_text_error)
                        retry_response.raise_for_status()
                        data = await retry_response.json()
                else:
                    response.raise_for_status()
                    data = await response.json()

                if "errors" in data and data["errors"]:
                    _LOGGER.error("GraphQL API returned errors: %s", data["errors"])
                    raise ApiError(f"GraphQL errors: {data['errors']}")
                
                return data.get("data", {})
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            _LOGGER.error("Error during GraphQL request: %s", e)
            raise ApiError(f"Error during GraphQL request: {e}") from e
        except Exception as e:
            _LOGGER.exception("Unexpected error during GraphQL request execution or parsing.")
            raise ApiError(f"An unexpected error occurred during GraphQL request: {e}") from e

    async def async_get_homes(self) -> List[Dict[str, Any]]:
        """Fetch user's homes using GraphQL."""
        # _LOGGER.debug("Requesting user homes from API.") # Removed
        try:
            response_data_field = await self._graphql_request(query=HOMES_QUERY)
            homes_list = response_data_field.get("me", {}).get("homes", [])
            if not isinstance(homes_list, list):
                _LOGGER.error("API response for homes is not a list.")
                return []
            # _LOGGER.debug("Received %d homes from API.", len(homes_list)) # Removed
            return homes_list
        except ApiError:
            raise # Already logged by _graphql_request or _ensure_token
        except Exception as e:
            _LOGGER.exception("Unexpected error structure or issue fetching homes.")
            raise ApiError(f"Unexpected error fetching homes: {e}") from e

    async def async_get_gizmos(self, home_id: str) -> List[Dict[str, Any]]:
        """Fetch gizmos for a specific home ID."""
        # _LOGGER.debug("Requesting gizmos for home ID %s", home_id) # Removed
        variables = {"homeId": home_id}
        try:
            response_data_field = await self._graphql_request(query=GIZMOS_QUERY_TEMPLATE, variables=variables)
            gizmos_list = response_data_field.get("me", {}).get("home", {}).get("gizmos", [])
            if not isinstance(gizmos_list, list):
                _LOGGER.error("API response for gizmos is not a list for home %s.", home_id)
                return []
            # _LOGGER.debug("Received %d gizmos for home %s.", len(gizmos_list), home_id) # Removed
            return gizmos_list
        except ApiError:
            raise
        except Exception as e:
            _LOGGER.exception("Unexpected error structure or issue fetching gizmos for home %s.", home_id)
            raise ApiError(f"Unexpected error fetching gizmos for home {home_id}: {e}") from e

    async def async_get_grid_rewards_history(self, home_id: str, from_date_str: str, to_date_str: str) -> Dict[str, Any]:
        """Fetch grid rewards history using GraphQL."""
        variables = {"homeId": home_id, "fromDate": from_date_str, "toDate": to_date_str}
        # _LOGGER.debug("Requesting grid_rewards_history for home %s.", home_id) # Removed
        
        response_data_field = await self._graphql_request(query=GRID_REWARDS_QUERY_TEMPLATE, variables=variables)
        default_return = {"ev": None, "homevolt": None, "total": None, "currency": None, "from_date_api": None, "to_date_api": None}
        
        try:
            rewards_data_period = response_data_field.get("me", {}).get("home", {}).get("gridRewardsHistoryPeriod")
            if rewards_data_period is None:
                _LOGGER.warning(
                    "gridRewardsHistoryPeriod not found or is null for home %s (from: %s, to: %s).",
                    home_id, from_date_str, to_date_str
                )
                return default_return

            return {
                "ev": rewards_data_period.get("vehicleRewards"),
                "homevolt": rewards_data_period.get("batteryRewards"),
                "total": rewards_data_period.get("totalReward"),
                "currency": rewards_data_period.get("currency"),
                "from_date_api": rewards_data_period.get("from"),
                "to_date_api": rewards_data_period.get("to")
            }
        except Exception: 
            _LOGGER.exception("Error parsing rewards data for home %s.", home_id)
            return default_return