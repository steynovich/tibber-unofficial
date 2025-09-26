
# Tibber Unofficial - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/senaxx/Tibber_unofficial.svg)](https://github.com/senaxx/Tibber_unofficial/releases)
[![Home Assistant Quality Scale: Gold](https://img.shields.io/badge/HA%20Quality%20Scale-Gold-orange.svg)](https://www.home-assistant.io/docs/quality_scale/#gold)

A **Gold standard** Home Assistant custom integration that provides access to Tibber Homevolt and EV Grid Rewards data through undocumented API endpoints. Track your monetary rewards from grid services across different time periods (daily, monthly, yearly).

## 🌟 Features

### 📊 Comprehensive Reward Tracking
- **12 dedicated sensors** for detailed reward monitoring
- **Real-time data** updated every 15 minutes (configurable)
- **Multi-currency support** using your Tibber account currency
- **Historical data** including current day, month, previous month, and yearly totals

### 🔧 Professional Features
- **Gold standard** Home Assistant integration quality
- **Intelligent caching** to minimize API calls
- **Rate limiting** to respect API limits
- **Automatic retry** with exponential backoff
- **Comprehensive diagnostics** for troubleshooting
- **Repair flows** for common issues
- **Services** for manual refresh and cache management
- **Full translation support** (English included)

### 🏠 Smart Device Management
- **Automatic device discovery** for Homevolt batteries and EVs
- **Entity registry integration** with proper naming
- **Statistics support** for long-term data tracking
- **Configurable update intervals** via UI
- **Proper device grouping** in Home Assistant

## 📋 Requirements

- Home Assistant 2025.5.3 or later
- Active Tibber account with Homevolt battery or EV
- Internet connection for API access

## 🚀 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations" → "Custom repositories"
3. Add `https://github.com/senaxx/Tibber_unofficial` as Integration
4. Install "Tibber Unofficial"
5. Restart Home Assistant

### Manual Installation

1. Download the integration files
2. Copy `custom_components/tibber_unofficial/` to your Home Assistant's `custom_components/` directory
3. Restart Home Assistant

## ⚙️ Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services**
2. Click **"+ ADD INTEGRATION"**
3. Search for and select **"Tibber Unofficial"**
4. Enter your Tibber account credentials:
   - **Email**: Your Tibber account email
   - **Password**: Your Tibber account password
5. Select your home if you have multiple homes
6. Complete the setup

### Configuration Options

Access configuration options via **Settings** → **Devices & Services** → **Tibber Unofficial** → **Configure**

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| **Rewards Update Interval** | 15 minutes | 5-1440 min | How often to fetch reward data |
| **Device Discovery Interval** | 12 hours | 1-168 hours | How often to discover new devices |

## 📊 Available Sensors

The integration creates 12 sensors organized by device type and time period:

### Electric Vehicle (EV) Rewards
- `sensor.tibber_unofficial_ev_current_day` - EV rewards for today
- `sensor.tibber_unofficial_ev_current_month` - EV rewards for current month
- `sensor.tibber_unofficial_ev_previous_month` - EV rewards for previous month
- `sensor.tibber_unofficial_ev_year` - EV rewards for current year

### Homevolt Battery Rewards
- `sensor.tibber_unofficial_homevolt_current_day` - Battery rewards for today
- `sensor.tibber_unofficial_homevolt_current_month` - Battery rewards for current month
- `sensor.tibber_unofficial_homevolt_previous_month` - Battery rewards for previous month
- `sensor.tibber_unofficial_homevolt_year` - Battery rewards for current year

### Total Rewards (Combined)
- `sensor.tibber_unofficial_total_current_day` - Total rewards for today
- `sensor.tibber_unofficial_total_current_month` - Total rewards for current month
- `sensor.tibber_unofficial_total_previous_month` - Total rewards for previous month
- `sensor.tibber_unofficial_total_year` - Total rewards for current year

### Sensor Attributes

Each sensor includes these attributes:
- `data_period_from`: Start date of the reward period
- `data_period_to`: End date of the reward period
- `last_updated`: When the data was last fetched
- `unit_of_measurement`: Currency (e.g., EUR, SEK, NOK)

## 🛠️ Services

### `tibber_unofficial.refresh_rewards`
Manually refresh reward data for all sensors or a specific entry.

**Parameters:**
- `entry_id` (optional): Specific config entry to refresh

**Example:**
```yaml
service: tibber_unofficial.refresh_rewards
```

### `tibber_unofficial.clear_cache`
Clear the API response cache to force fresh data retrieval.

**Parameters:**
- `entry_id` (optional): Specific config entry to clear cache for

**Example:**
```yaml
service: tibber_unofficial.clear_cache
```

## 🔧 Troubleshooting

### Built-in Diagnostics

The integration includes comprehensive diagnostics accessible via:
**Settings** → **Devices & Services** → **Tibber Unofficial** → **Download Diagnostics**

Diagnostics include:
- Configuration details (sensitive data redacted)
- API client status and cache statistics
- Coordinator update history and errors
- Entity states and device information
- Rate limiter status

### Common Issues & Automatic Repairs

The integration can automatically detect and help fix common issues:

#### Authentication Failed
**Symptoms:** Entities show as unavailable, log shows authentication errors
**Solution:** Integration will create a repair notification. Click "Fix" and enter updated credentials.

#### Rate Limit Exceeded
**Symptoms:** Frequent API errors, data not updating
**Solution:** Integration will suggest increasing update intervals. Accept the repair to automatically adjust.

#### Configuration Issues
**Symptoms:** Deprecated options or invalid settings
**Solution:** Integration will guide you through updating to recommended settings.

### Manual Troubleshooting

#### Check Logs
Enable debug logging in `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.tibber_unofficial: debug
```

#### Verify Credentials
- Ensure your Tibber account credentials are correct
- Check if your account has Homevolt or EV devices
- Verify internet connectivity

#### Reset Integration
1. Remove the integration from **Devices & Services**
2. Restart Home Assistant
3. Re-add the integration with fresh credentials

## 🏆 Example Automations

### Daily Reward Notification
```yaml
automation:
  - alias: "Daily Tibber Rewards Summary"
    trigger:
      - platform: time
        at: "20:00:00"
    condition:
      - condition: template
        value_template: "{{ states('sensor.tibber_unofficial_total_current_day') | float > 0 }}"
    action:
      - service: notify.notify
        data:
          title: "Daily Grid Rewards"
          message: >
            Today you earned {{ states('sensor.tibber_unofficial_total_current_day') }}
            {{ state_attr('sensor.tibber_unofficial_total_current_day', 'unit_of_measurement') }}
            from grid services!
```

### Monthly Rewards Dashboard Card
```yaml
type: entities
title: Monthly Grid Rewards
entities:
  - entity: sensor.tibber_unofficial_ev_current_month
    name: EV Rewards
  - entity: sensor.tibber_unofficial_homevolt_current_month
    name: Battery Rewards
  - entity: sensor.tibber_unofficial_total_current_month
    name: Total Rewards
    icon: mdi:cash-multiple
```

### Low Rewards Alert
```yaml
automation:
  - alias: "Low Monthly Rewards Alert"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: template
        value_template: "{{ now().day == 28 }}" # Near month end
      - condition: numeric_state
        entity_id: sensor.tibber_unofficial_total_current_month
        below: 50  # Adjust threshold as needed
    action:
      - service: notify.notify
        data:
          title: "Low Grid Rewards"
          message: >
            Your monthly grid rewards are only
            {{ states('sensor.tibber_unofficial_total_current_month') }}
            {{ state_attr('sensor.tibber_unofficial_total_current_month', 'unit_of_measurement') }}
            so far. Consider optimizing your energy usage!
```

## 🎨 Dashboard Examples

### Grid Rewards Overview Card
```yaml
type: custom:mini-graph-card
name: Grid Rewards Trend
entities:
  - sensor.tibber_unofficial_total_current_day
line_width: 3
font_size: 75
hours_to_show: 168 # 1 week
points_per_hour: 1
show:
  extrema: true
  fill: fade
color_thresholds:
  - value: 0
    color: "#ff5722"
  - value: 10
    color: "#ff9800"
  - value: 25
    color: "#4caf50"
```

### Rewards Statistics Card
```yaml
type: statistics-graph
title: Monthly Rewards History
entities:
  - sensor.tibber_unofficial_total_current_month
period: month
stat_types:
  - sum
  - mean
  - max
```

## 🔗 External Resources

- **Tibber Official App**: [app.tibber.com](https://app.tibber.com)
- **Tibber Developer Documentation**: [developer.tibber.com](https://developer.tibber.com)
- **Home Assistant Community**: [community.home-assistant.io](https://community.home-assistant.io)
- **Issue Tracker**: [GitHub Issues](https://github.com/senaxx/Tibber_unofficial/issues)

## ⚖️ Legal & Privacy

This integration uses undocumented Tibber API endpoints and is not officially supported by Tibber. Use at your own risk.

- **Privacy**: Your credentials are stored locally and only used to authenticate with Tibber
- **Data**: The integration only accesses grid reward data, not consumption or billing information
- **Rate Limiting**: Built-in protections respect Tibber's API limits
- **Terms**: Ensure you comply with Tibber's Terms of Service

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request with detailed description

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Tibber** for providing the underlying API
- **Home Assistant Community** for guidance and support
- **Contributors** who helped improve this integration

---

## 🏆 Gold Quality Integration

This integration meets Home Assistant's **Gold** quality standard, featuring:

- ✅ **Professional User Experience** - Intuitive setup and configuration
- ✅ **Automatic Issue Resolution** - Built-in repair flows for common problems
- ✅ **Comprehensive Diagnostics** - Download detailed diagnostic information
- ✅ **Full Test Coverage** - Extensive automated testing suite
- ✅ **Professional Documentation** - Complete user guides and examples
- ✅ **Translation Framework** - Ready for multiple languages
- ✅ **Statistics Integration** - Long-term data tracking support
- ✅ **Device Registry** - Proper device and entity management

## 🔄 Recent Updates

**v2025.06.1** - Gold Standard Release
- 🏆 **Gold Quality Scale Achievement** - Full compliance with HA Gold standards
- 🛠️ **Professional Repair System** - Automatic issue detection and guided fixes
- 📊 **Comprehensive Diagnostics** - Download diagnostic data for troubleshooting
- 🔧 **Service Integration** - Manual refresh and cache management services
- 🌍 **Translation Framework** - Full internationalization support
- 📈 **Enhanced Statistics** - Better long-term data tracking
- 🔒 **Enhanced Security** - UUID validation and improved error handling
- 🚀 **Performance Improvements** - Smart caching with adaptive TTL
- 🐛 **Bug Fixes** - 10+ critical bugs fixed including memory leaks and race conditions

## 📈 Performance & Reliability

The integration includes professional-grade features for reliability:

- **Smart Rate Limiting** - Respects API limits with persistent state
- **Exponential Backoff** - Automatic retry with intelligent delays
- **Connection Pooling** - Efficient HTTP connection management
- **Smart Caching** - Adaptive TTL based on data types
- **Resource Management** - Proper cleanup to prevent memory leaks
- **Error Recovery** - Graceful handling of partial failures

## 🛡️ Security & Privacy

- **Local Credential Storage** - Credentials never leave your Home Assistant instance
- **UUID Validation** - Strict validation of home IDs for security
- **Token Management** - Automatic refresh with secure expiry handling
- **Data Redaction** - Sensitive data removed from diagnostics
- **Minimal Permissions** - Only accesses grid reward data, no consumption data

---

**Quality Scale**: This integration meets Home Assistant's **Gold** quality standard, ensuring excellent user experience, comprehensive testing, and professional documentation.

## 📜 Authentication & Legal
This integration requires you to authenticate using your personal Tibber credentials.

## ⚖️ Disclaimer
A spokesperson from Tibber has approved the publication of this integration. However, please be aware of the following:

- This integration relies on an undocumented API, which means its functionality may change or break without warning.
- This is my first HACS integration, and I am still actively developing my skills in Python and Home Assistant development. 

While I will do my best to maintain it, bugs and issues may be present.
Contributions and feedback are welcome!

## Planning
This first release only supports the Grid Rewards for now in 9 sensors. I'm planning to add support for Homevolt, EV, EV Charger, Contract information, Solar Inverter. 

## Releases

## v0.1.1
Adds sensors that track the result of the current day.

## v0.1
This is my first release and only supports the Tibber Grid Rewards earnings for now

### Sensors
 - Grid Rewards EV - Current Day
 - Grid Rewards EV - Current Month
 - Grid Rewards EV - Previous Month
 - Grid Rewards EV - Current Year
 - Grid Rewards Homevolt - Current Day
 - Grid Rewards Homevolt - Current Month
 - Grid Rewards Homevolt - Previous Month
 - Grid Rewards Homevolt - Current Year
 - Grid Rewards Total - Current Day
 - Grid Rewards Total - Current Month
 - Grid Rewards Total - Previous Month
 - Grid Rewards Total - Current Year




