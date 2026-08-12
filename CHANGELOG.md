# Changelog

All notable changes to NOAA It All for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.5] - 2026-08-12

### Fixed
- README header image now renders. It pointed at a `github.com/.../blob/...` URL, which serves an
  HTML page rather than an image, so the logo appeared broken on GitHub and on the integration's
  HACS page (`hacs.json` sets `render_readme`). Now uses `raw.githubusercontent.com`.
- Corrected the integration domain throughout `.github/copilot-instructions.md`, which referenced a
  non-existent `custom_components/noaa_integration/` path. Every documented command that named a
  path was broken as a result. Also refreshed the file-tree listing, which was missing the
  coordinator, config flow, parsers and the entire `sensors/` package.

### Added
- `TestReadmeImages` regression test that fails on any `github.com` `/blob/` image URL in the
  README, so the above cannot silently return.

### Notes
- No functional changes to the integration; this release is documentation and test coverage only.
- The HACS store-list icon placeholder is unaffected and is not fixable here. It is served from
  `brands.home-assistant.io`, backed by `home-assistant/brands`, which stopped accepting new
  custom-integration submissions on 2026-03-03. It resolves when HACS ships hacs/frontend#937.

## [0.3.13]

### Added
- Dedicated `NOAA Hurricane` device that groups all global hurricane / NHC entities (Hurricane Alerts, Hurricane Activity, Hurricane Outlook Image, GOES Air Mass, GOES GeoColor) into a single device, independent of any configured NWS office.
- Location-specific aurora visibility predictions with timing and duration
- Solar Radiation Storm alerts with S1-S5 classification and location-specific risk assessment
- Forecast Discussion sensor (AFD product) with meteorologist-written technical analysis
- Cloud Cover sensor from NWS gridpoint data
- Radar Timestamp sensor for tracking radar image freshness
- Feels Like (apparent temperature) sensor with wind chill / heat index
- Comprehensive NWS Active Alerts sensor with severity and urgency breakdowns

### Improved
- Weather observations now fetched from nearest station using coordinates (weather.gov API)
- Device grouping organises all entities under NOAA Space, NOAA Weather, NOAA Surf, NOAA Hurricane, and NOAA Weather [OFFICE]

### Breaking Changes
- Hurricane sensors and hurricane image entities are no longer duplicated per configured NWS office. Their `unique_id` values changed from `noaa_{office}_hurricane_*` / `noaa_{office}_goes_*` to global IDs (`noaa_hurricane_alerts`, `noaa_hurricane_activity`, `noaa_hurricane_outlook_image`, `noaa_goes_airmass_image`, `noaa_goes_geocolor_image`). Existing entity registry entries from previous versions will become orphaned and may need to be deleted; the new entities will be created automatically under the `NOAA Hurricane` device.

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
