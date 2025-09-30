"""Constants for the Tibber Unofficial integration."""

from datetime import timedelta

# Domain of your integration
DOMAIN = "tibber_unofficial"

# Platforms to be set up
PLATFORMS = ["sensor"]

# Default polling intervals
DEFAULT_REWARDS_SCAN_INTERVAL = timedelta(minutes=15)
DEFAULT_GIZMO_SCAN_INTERVAL = timedelta(hours=12)

# Configuration keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_HOME_ID = "home_id"
CONF_GIZMO_IDS = "gizmo_ids"

# API Endpoints
API_AUTH_URL = "https://app.tibber.com/login.credentials"
API_GRAPHQL_URL = "https://app.tibber.com/v4/gql"

# Sensor Data Keys for coordinator data (for grid rewards) - RENAMED
GRID_REWARDS_EV_CURRENT_MONTH = "grid_rewards_ev_current_month"
GRID_REWARDS_HOMEVOLT_CURRENT_MONTH = "grid_rewards_homevolt_current_month"
GRID_REWARDS_TOTAL_CURRENT_MONTH = "grid_rewards_total_current_month"

GRID_REWARDS_EV_PREVIOUS_MONTH = "grid_rewards_ev_previous_month"
GRID_REWARDS_HOMEVOLT_PREVIOUS_MONTH = "grid_rewards_homevolt_previous_month"
GRID_REWARDS_TOTAL_PREVIOUS_MONTH = "grid_rewards_total_previous_month"

GRID_REWARDS_EV_YEAR = "grid_rewards_ev_year"
GRID_REWARDS_HOMEVOLT_YEAR = "grid_rewards_homevolt_year"
GRID_REWARDS_TOTAL_YEAR = "grid_rewards_total_year"

# Current day grid rewards
GRID_REWARDS_EV_CURRENT_DAY = "grid_rewards_ev_current_day"
GRID_REWARDS_HOMEVOLT_CURRENT_DAY = "grid_rewards_homevolt_current_day"
GRID_REWARDS_TOTAL_CURRENT_DAY = "grid_rewards_total_current_day"

KEY_CURRENCY = "currency"  # Unchanged

# Attributes
ATTR_LAST_UPDATED = "last_updated"
ATTR_DATA_PERIOD_FROM = "data_period_from"
ATTR_DATA_PERIOD_TO = "data_period_to"

# GraphQL Query to fetch user's homes
HOMES_QUERY = """
{
  me {
    homes {
      id
      timeZone
      hasSmartMeterCapabilities
      hasSignedEnergyDeal
      hasConsumption
    }
  }
}
"""

# GraphQL Query to fetch gizmos for a specific home
GIZMOS_QUERY_TEMPLATE = """
query GetGizmos($homeId: String!) {
  me {
    home(id: $homeId) {
      gizmos {
        __typename
        ... on Gizmo {
          id
          title
          type
          isHidden
        }
      }
    }
  }
}
"""

# GraphQL Query for Grid Rewards (monthly resolution)
# Note: The API doesn't properly support daily resolution, so we use monthly for both
GRID_REWARDS_QUERY_TEMPLATE = """
query GetGridRewards($homeId: String!, $fromDate: String!, $toDate: String!) {
  me {
    home(id: $homeId) {
      gridRewardsHistoryPeriod(
        from: $fromDate,
        to: $toDate,
        resolution: monthly
      ) {
        from
        to
        batteryRewards
        vehicleRewards
        totalReward
        currency
      }
    }
  }
}
"""

# Alias for compatibility - both queries use monthly resolution
GRID_REWARDS_DAILY_QUERY_TEMPLATE = GRID_REWARDS_QUERY_TEMPLATE

# Desired Gizmo types to extract IDs for
DESIRED_GIZMO_TYPES = [
    "REAL_TIME_METER",
    "INVERTER",
    "BATTERY",
    "ELECTRIC_VEHICLE",
    "EV_CHARGER",
]

# Keys for storing coordinators in hass.data
COORDINATOR_REWARDS = "rewards_coordinator"
COORDINATOR_GIZMOS = "gizmos_coordinator"
