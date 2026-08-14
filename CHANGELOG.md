# Changelog

All notable changes to NOAA It All for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - Current

### Added
- **Tsunami alerts**, in a new global `NOAA Tsunami` device group (`noaa_tsunami`), created once
  and shared across every configured office. Global entities, present on every install:
  - `sensor.noaa_tsunami_threat_level` — highest tsunami alert in effect anywhere in US waters:
    `Warning`, `Advisory`, `Watch`, `Information` or `None`. Reads `unknown` rather than `None`
    before the first successful fetch, so automations can tell "no threat" from "no data"
  - `sensor.noaa_tsunami_active_alerts` — count of tsunami alerts in effect nationally
  - `sensor.noaa_tsunami_source_earthquake` — preliminary magnitude of the causative quake, with
    depth, epicenter and region as attributes
  - `sensor.noaa_tsunami_last_message` — when the warning centers last issued a product, with
    message type (New/Update/Cancellation/Final) and the five most recent products
  - `binary_sensor.noaa_tsunami_alert_active` — on for an active Warning or Advisory. Watches and
    Information Statements deliberately leave it off
  - `binary_sensor.noaa_tsunami_data_stale` — on when the feed has stopped answering
  - `image.noaa_tsunami_map` — the wave energy propagation forecast from the issuing warning
    center during an event, falling back to the NDBC DART buoy network map the rest of the time,
    so the tile is never dead. `map_type`, `source_url` and `active_center` attributes report
    which source is on screen
- Location-specific tsunami entities on the same device, created only for the 26 coastal offices
  listed in `OFFICE_TSUNAMI_CENTERS`:
  - `sensor.noaa_tsunami_{office}_local_threat` — alert level for your own coordinates
  - `sensor.noaa_tsunami_{office}_wave_arrival` — estimated arrival at the nearest forecast point
  - `sensor.noaa_tsunami_{office}_evacuation_status` — the action to take, with the full official
    instruction text as an attribute
- `TsunamiCoordinator` in `coordinator.py`, polling `api.weather.gov/alerts/active` every 2
  minutes and the NTWC/PTWC Atom and CAP feeds at tsunami.gov when an alert is active or roughly
  every half hour.
- Seven pure tsunami parsing functions in `parsers.py`, including CAP 1.2 and Atom parsing using
  only the Python standard library.

### Notes
- **This is not a primary warning source.** These entities are for automation and awareness only.
  Home Assistant, your network, and NOAA's servers can all fail silently. Never rely on this
  integration for evacuation decisions — use NOAA Weather Radio, Wireless Emergency Alerts, and
  local sirens.
- The 2-minute poll is the fastest in the integration and is deliberate: a near-field tsunami can
  reach the coast in under fifteen minutes, so a ten-minute poll could burn most of the available
  warning time before the sensor changed state.
- Tsunami alerts are queried by the VTEC-derived codes `TSW`/`TSA`/`TSY` rather than by event-name
  strings, so the query survives NWS wording changes.
- Monthly NWS tsunami communications tests never move the threat level or trip the alert binary
  sensor, but do populate the `last_test_message` attribute. On a normal install that is the only
  traffic this domain will ever see, and it is how you confirm the pipeline still works.
- XML is size-capped at 512 KB and refused outright if it carries a `DOCTYPE`, since
  `xml.etree.ElementTree` is not hardened against entity-expansion attacks and `defusedxml` is not
  a dependency here.
- The map entity tries each image source in turn and treats a non-200 response or a non-image
  content type as "fall through to the next" rather than an error, so an energy map that does not
  exist for a given event quietly yields the DART map instead of a broken tile.
- The ten Great Lakes offices (APX, CLE, DLH, DTX, GRB, GRR, IWX, LOT, MKX, MQT) get the six
  global entities and none of the location-specific ones.

### Fixed
- `sensor.noaa_tsunami_source_earthquake` read `Unknown` on a working feed. Two causes, both
  found against a live install:
  - The magnitude pattern was anchored on a bare `M`, so it matched the leading letter of
    "magnitude" and then failed on the letters after it. Products written as "preliminary
    magnitude 6.2" — which is how the centers usually write it — never matched. Several wordings
    are now tried in order (`magnitude 6.2`, `magnitude of 6.2`, `M 7.8`, `M7.8`, `M=5.9`,
    `Mw 8.1`), with an implausible-value guard so a message number cannot become an earthquake.
  - Only the newest product was inspected. That is frequently a routine statement carrying no
    quake parameters, which blanked the sensor while the answer sat one entry further down.
    `find_source_earthquake` now scans back through recent products.
- `sensor.noaa_tsunami_{office}_wave_arrival` sat on `unknown` whenever no event was in progress,
  which reads like a fault. It now says `No active event` when the feed is healthy and reserves
  `unknown` for "nothing fetched".

### Changed
- The quiet-day map is now a list of candidate URLs tried in turn rather than a single guess, and
  the URL that succeeds is logged at info level so the working one can be identified from a real
  install and the list trimmed.
- `manifest.json` version bumped to 0.6.0. No new requirements — the tsunami feature adds no
  dependency beyond the standard library.

### Unchanged (deliberately)
- `SevereWeatherAlertBinarySensor._SEVERE_EVENTS` still lists `tsunami warning`, `tsunami watch`
  and `tsunami advisory`. Existing automations bound to
  `binary_sensor.noaa_{office}_weather_severe_weather_alert` keep firing for tsunamis. Removing
  them would have silently broken life-safety automations, so a tsunami now trips both that sensor
  and the dedicated tsunami entities. A regression test enforces this.

## [0.5.0]

### Added
- **Meteor shower alerts and viewing forecast**, in the `NOAA Space` device group:
  - `binary_sensor.noaa_{office}_space_meteor_shower_active` — turns on only when a shower is
    genuinely worth going outside for, gated on both a real predicted rate (>=5/hour) and usable
    sky conditions (score >=25) so it stays off most nights rather than sitting permanently on
    (about 50 nights a year measured from Wilmington NC, clustered around the major showers)
  - `sensor.noaa_{office}_space_meteor_shower_activity` — the shower most worth watching now
  - `sensor.noaa_{office}_space_next_meteor_shower` — next shower to peak, with an `upcoming`
    attribute listing the next five for dashboard cards
  - `sensor.noaa_{office}_space_meteor_viewing_score` — 0-100 sky-conditions score with the best
    viewing window, expected meteors/hour, moon state and the limiting factor
- Bundled catalog of 29 meteor showers (`meteor_catalog.py`) keyed by **solar longitude** rather
  than by date, sourced from the IMO Meteor Shower Calendar and the IAU Meteor Data Center.
- `astro.py` and `meteor.py`: standard-library positional astronomy and the meteor rate model,
  with no Home Assistant dependency, verified against Meeus worked examples 7.a, 12.a, 13.b,
  25.a, 47.a and 48.a.

### Notes
- **This feature makes no network requests.** NOAA publishes no meteor shower data — the NWS
  alert taxonomy covers terrestrial hazards and the Space Weather Prediction Center covers
  geomagnetic activity, not meteors — and no live feed is needed, because Earth crosses the same
  debris streams at the same point in its orbit every year. Peak times are computed locally from
  each shower's stored solar longitude, so the catalog never needs a date update.
- Computed peak times are accurate to about **±11 minutes**, far finer than the hours-wide spread
  of real shower maxima and than the precision to which published maxima are themselves quoted.
- The viewing score measures **sky conditions, not shower strength** — the shower's ZHR cancels
  out of the relation, so a minor shower riding high under a new moon scores well while the
  Perseids behind a full moon score badly. Shower strength is reported as `expected_per_hour`.
- The score accounts for radiant altitude, moonlight and astronomical darkness. It does **not**
  account for cloud cover; pair it with the existing Cloud Cover sensor if you want that.
- No new dependencies: `requirements` remains `aiohttp` and `voluptuous`.

### Fixed
- **Binary sensors no longer repeat the device name.** All five existing binary sensors set a
  full `_attr_name` containing `NOAA {office}` while also carrying a device, so Home Assistant
  prefixed the device name a second time — producing
  `binary_sensor.noaa_ilm_surf_noaa_ilm_unsafe_to_swim` and the friendly name
  "NOAA ILM Surf NOAA ILM Unsafe to Swim". They now use `_attr_has_entity_name = True` with a
  local-only name, matching every sensor in the integration. Found by running the integration on
  a live Home Assistant instance.
  - **Existing installations are unaffected in any way that breaks automations.** The `unique_id`
    values are unchanged, so the entity registry keeps the entity IDs it already assigned. Only
    the displayed friendly name changes. Fresh installations get the shorter IDs
    (`binary_sensor.noaa_{office}_surf_unsafe_to_swim`); see the migration table in the README.
- Corrected the binary sensor entity IDs throughout README.md and CONFIGURATION.md. They
  previously documented IDs such as `binary_sensor.noaa_ilm_unsafe_to_swim`, which Home Assistant
  never actually produced.

### Changed
- Meteor shower entities refresh every 30 minutes rather than the integration default of 10,
  since nothing is fetched and the best-of-night result is stable for hours.

## [0.3.13] - Previous

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
