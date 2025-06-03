
# Tibber unofficial HACS integration
This custom integration provides support for the Homevolt and EV Grid Rewards within Home Assistant. As the official Tibber API does not currently offer this functionality, this component utilizes an undocumented API endpoint.

## Authentication
This integration requires you to authenticate using your personal Tibber credentials.

## Disclaimer
A spokesperson from Tibber has approved the publication of this integration. However, please be aware of the following:

- This integration relies on an undocumented API, which means its functionality may change or break without warning.
- This is my first HACS integration, and I am still actively developing my skills in Python and Home Assistant development. 

While I will do my best to maintain it, bugs and issues may be present.
Contributions and feedback are welcome!

## Planning
This first release only supports the Grid Rewards for now in 9 sensors. I'm planning to add support for Homevolt, EV, EV Charger, Contract information, Solar Inverter. 

## Releases
## v0.1
This is my first release and only supports the Tibber Grid Rewards earnings for now

### Sensors
 - Grid Rewards EV - Current Month
 - Grid Rewards EV - Previous Month
 - Grid Rewards EV - Current Year
 - Grid Rewards Homevolt - Current Month
 - Grid Rewards Homevolt - Previous Month
 - Grid Rewards Homevolt - Current Year
 - Grid Rewards Total - Current Month
 - Grid Rewards Total - Previous Month
 - Grid Rewards Total - Current Year




