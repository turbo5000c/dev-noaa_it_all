# Changelog

All notable changes to the NOAA Integration for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.7.2] - Current

### Added
- Location-specific aurora visibility predictions with timing and duration
- Solar Radiation Storm alerts with S1-S5 classification and location-specific risk assessment
- Forecast Discussion sensor (AFD product) with meteorologist-written technical analysis
- Cloud Cover sensor from NWS gridpoint data
- Radar Timestamp sensor for tracking radar image freshness
- Feels Like (apparent temperature) sensor with wind chill / heat index
- Comprehensive NWS Active Alerts sensor with severity and urgency breakdowns

### Improved
- Weather observations now fetched from nearest station using coordinates (weather.gov API)
- Device grouping organises all entities under NOAA Space, NOAA Weather, NOAA Surf, and NOAA Weather [OFFICE]

## [1.0.20]

### Breaking Changes
- **Latitude and Longitude are now required fields** in Config Flow setup
- Weather data now fetched from nearest observation station to configured coordinates
- Users must reconfigure the integration to provide coordinates

### Added
- Config Flow UI setup with NWS office selector and coordinate inputs
- Location-specific weather observations from nearest NWS station
- Binary sensors for Severe Weather, Flood/Winter, Heat/Air Quality, and Active Alerts

## [1.0.0]

### Added
- Initial release
- Planetary K-Index sensor
- Geomagnetic Storm measurements
- Hurricane alerts and activity sensors
- Geomagnetic field and aurora forecast image entities
- Legacy YAML configuration support
