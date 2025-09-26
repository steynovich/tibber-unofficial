# Tibber Unofficial Integration

## Features

This integration provides access to Tibber Homevolt and EV Grid Rewards data through unofficial API endpoints.

### Sensors Provided

The integration creates 12 monetary sensors tracking grid rewards across different time periods:

#### Current Values
- **Current Day Total/EV/Homevolt**: Today's rewards so far
- **Current Month Total/EV/Homevolt**: This month's accumulated rewards
- **Current Year Total/EV/Homevolt**: This year's accumulated rewards

#### Historical Values
- **Previous Month Total/EV/Homevolt**: Last month's total rewards

All monetary values are displayed in your home's configured currency (EUR, SEK, NOK, etc.).

### Key Features
- **Smart Caching**: Reduces API calls while maintaining data freshness
- **Configurable Update Intervals**: Customize how often data is fetched
- **Automatic Retry Logic**: Handles temporary API failures gracefully
- **Rate Limiting**: Prevents overwhelming the API
- **Comprehensive Error Handling**: Clear error messages and logging

## Configuration

1. Add the integration via Home Assistant UI
2. Enter your Tibber credentials (same as mobile app)
3. Select your home if you have multiple
4. Configure update intervals in integration options (optional)

## Important Notes

⚠️ **Unofficial API**: This integration uses undocumented Tibber endpoints that may change without notice. It is not affiliated with or endorsed by Tibber.

## Requirements

- Home Assistant 2025.5.3 or newer
- Active Tibber account with energy deal
- Homevolt battery and/or Electric Vehicle registered in Tibber app

## Support

For issues or questions, please use the [GitHub issue tracker](https://github.com/steynovich/tibber-unofficial/issues).