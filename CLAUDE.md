# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration that provides access to Tibber Homevolt and EV Grid Rewards data through undocumented API endpoints. The integration tracks monetary rewards from grid services across different time periods (daily, monthly, yearly).

## Key Architecture Components

### Data Flow Pattern
The integration uses Home Assistant's DataUpdateCoordinator pattern with two coordinators:
- **GridRewardsCoordinator** (`__init__.py`): Fetches rewards data every 15 minutes
- **GizmoUpdateCoordinator** (`__init__.py`): Discovers devices every 12 hours

### Core Files
- `api.py`: TibberApiClient handles authentication and GraphQL queries to Tibber's app endpoints
- `sensor.py`: Implements 12 monetary sensors grouped under "Grid Rewards" device
- `const.py`: Contains GraphQL queries for both daily and monthly data resolution
- `config_flow.py`: User authentication and home selection during setup

## Development Commands

### Validation
```bash
# Validate Home Assistant integration standards
python -m script.hassfest

# Validate HACS compatibility (runs in CI)
# No local command - validated via GitHub Actions
```

### Testing
Currently no test suite exists. When adding tests, follow Home Assistant's testing patterns using pytest.

### Installation for Development
1. Copy `custom_components/tibber_unofficial/` to your Home Assistant's `custom_components/` directory
2. Restart Home Assistant
3. Add integration via UI: Settings → Devices & Services → Add Integration → "Tibber Unofficial"

## API Details

### Official Tibber API Documentation
- **Overview**: https://developer.tibber.com/docs/overview
- **API Reference**: https://developer.tibber.com/docs/reference
- Note: This integration uses undocumented app endpoints, not the official API

### Authentication Flow
1. Username/password → Bearer token via `https://app.tibber.com/login.credentials`
2. Token used for GraphQL queries to `https://app.tibber.com/v4/gql`
3. Automatic token refresh on 401 responses

### GraphQL Queries
- `GRID_REWARDS_MONTHLY_QUERY`: Fetches monthly aggregated rewards
- `GRID_REWARDS_DAILY_QUERY`: Fetches daily rewards for current day tracking
- Both queries filter by home ID and gizmo types (BATTERY, ELECTRIC_VEHICLE)

### Sensor Types
Each sensor tracks monetary rewards in home currency:
- Current day (EV, Homevolt, Total)
- Current month (EV, Homevolt, Total)
- Previous month (EV, Homevolt, Total)
- Current year (EV, Homevolt, Total)

## Important Constraints

1. **Unofficial API**: Uses undocumented endpoints - may break without warning
2. **No External Dependencies**: All dependencies provided by Home Assistant
3. **Minimum HA Version**: 2025.5.3 required
4. **Update Intervals**: 15 minutes for rewards, 12 hours for device discovery
5. **Currency**: Uses home's configured currency from Tibber account

## Performance Optimizations (Latest)

### Implemented Optimizations
1. **Parallel API Calls** - GridRewardsCoordinator fetches all periods concurrently (~66% faster)
2. **Authentication Lock** - asyncio.Lock prevents concurrent auth attempts when parallel requests race
   - Double-check pattern: check token → acquire lock → check again → authenticate if needed
   - Only first request authenticates, others reuse the token
   - Eliminates wasteful duplicate authentication calls
3. **Compiled Regex** - UUID pattern compiled once at module level for repeated validation
4. **Session Management** - Fixed memory leak in config flow with proper cleanup
5. **Code Simplification** - Simplified sensor availability logic and cache operations
6. **Workflow Fix** - Python syntax validation now recursively checks all files

### Performance Metrics
- **API Fetch Time**: Reduced from ~3 seconds to ~1 second per coordinator update
- **Authentication**: Only 1 auth call instead of 3 when parallel requests start
- **Memory**: Fixed session leak preventing gradual memory growth
- **Validation**: All Python files now properly validated in CI pipeline