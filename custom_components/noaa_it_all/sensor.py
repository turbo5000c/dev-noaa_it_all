"""Sensor platform for NOAA Integration.

This module provides the platform setup entry points for Home Assistant.
All sensor entity classes live in dedicated domain modules under the
``sensors`` package — see ``sensors/__init__.py`` for the full list.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, DOMAIN,
    HURRICANE_SENSORS_ADDED_KEY, TSUNAMI_SENSORS_ADDED_KEY,
    OFFICE_TSUNAMI_CENTERS,
)

# Re-export every sensor class so that existing code that imports
# directly from ``sensor`` continues to work.
from .sensors import (  # noqa: F401
    GeomagneticSensor,
    GeomagneticSensorInterpretation,
    PlanetaryKIndexSensor,
    PlanetaryKIndexSensorRating,
    HurricaneAlertsSensor,
    HurricaneActivitySensor,
    RipCurrentRiskSensor,
    SurfHeightSensor,
    WaterTemperatureSensor,
    AuroraNextTimeSensor,
    AuroraDurationSensor,
    AuroraVisibilityProbabilitySensor,
    SolarRadiationStormAlertsSensor,
    WeatherObservationSensor,
    TemperatureSensor,
    HumiditySensor,
    WindSpeedSensor,
    WindDirectionSensor,
    BarometricPressureSensor,
    DewpointSensor,
    VisibilitySensor,
    SkyConditionsSensor,
    FeelsLikeSensor,
    ForecastBaseSensor,
    ExtendedForecastSensor,
    HourlyForecastSensor,
    NWSAlertsSensor,
    CloudCoverSensor,
    RadarTimestampSensor,
    ForecastDiscussionSensor,
    MeteorShowerActivitySensor,
    NextMeteorShowerSensor,
    MeteorViewingScoreSensor,
    TsunamiThreatLevelSensor,
    TsunamiActiveAlertsSensor,
    TsunamiSourceEarthquakeSensor,
    TsunamiLastMessageSensor,
    TsunamiLocalThreatSensor,
    TsunamiWaveArrivalSensor,
    TsunamiEvacuationStatusSensor,
)

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform (legacy YAML support)."""
    _LOGGER.error(
        "Legacy YAML configuration for NOAA sensors is no longer supported and "
        "will not create any entities. Please remove the YAML configuration "
        "from configuration.yaml and re-add the integration via the Home "
        "Assistant UI config flow."
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA sensors from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

    data = hass.data[DOMAIN][config_entry.entry_id]
    space_coord = data["space_weather_coordinator"]
    hurricane_coord = data["hurricane_coordinator"]
    surf_coord = data["surf_coordinator"]
    observations_coord = data["observations_coordinator"]
    forecast_coord = data["forecast_coordinator"]
    alerts_coord = data["alerts_coordinator"]
    cloud_cover_coord = data["cloud_cover_coordinator"]
    radar_coord = data["radar_timestamp_coordinator"]
    discussion_coord = data["forecast_discussion_coordinator"]
    meteor_coord = data["meteor_coordinator"]
    tsunami_coord = data["tsunami_coordinator"]

    entities = [
        # Space weather (global, use SpaceWeatherCoordinator)
        GeomagneticSensor(space_coord, office_code),
        GeomagneticSensorInterpretation(space_coord, office_code),
        PlanetaryKIndexSensor(space_coord, office_code),
        PlanetaryKIndexSensorRating(space_coord, office_code),
        AuroraNextTimeSensor(space_coord, office_code),
        AuroraDurationSensor(space_coord, office_code),
        AuroraVisibilityProbabilitySensor(space_coord, office_code),
        SolarRadiationStormAlertsSensor(space_coord, office_code),

        # Surf (office-specific, use SurfCoordinator)
        RipCurrentRiskSensor(surf_coord, office_code),
        SurfHeightSensor(surf_coord, office_code),
        WaterTemperatureSensor(surf_coord, office_code),
    ]

    # Hurricane sensors are global (NHC) and grouped under a single
    # dedicated NOAA Hurricane device. Only add them once across all
    # configured NWS offices to prevent duplicates. Track the owning
    # config entry's entry_id so that if the owner is unloaded while
    # other entries remain we can release ownership and trigger a
    # remaining entry to re-create the entities.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(HURRICANE_SENSORS_ADDED_KEY):
        entities.extend([
            HurricaneAlertsSensor(hurricane_coord),
            HurricaneActivitySensor(hurricane_coord),
        ])
        domain_data[HURRICANE_SENSORS_ADDED_KEY] = config_entry.entry_id

        def _release_hurricane_sensor_ownership() -> None:
            """Release hurricane-sensor ownership and re-create on a remaining entry.

            Fires when the owning config entry is unloaded. If other entries
            remain, clear the flag and reload one of them so its
            ``async_setup_entry`` re-adds the global hurricane sensors;
            otherwise the entities would disappear until Home Assistant
            restarts.
            """
            if domain_data.get(HURRICANE_SENSORS_ADDED_KEY) != config_entry.entry_id:
                return
            domain_data.pop(HURRICANE_SENSORS_ADDED_KEY, None)
            remaining = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != config_entry.entry_id
            ]
            if remaining:
                target_entry_id = remaining[0].entry_id

                async def _reload_for_hurricane_sensors() -> None:
                    try:
                        await hass.config_entries.async_reload(target_entry_id)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed to reload entry %s to re-create global "
                            "hurricane sensors", target_entry_id,
                        )

                hass.async_create_task(_reload_for_hurricane_sensors())

        config_entry.async_on_unload(_release_hurricane_sensor_ownership)

    # Observation sensors (location-specific)
    if observations_coord:
        entities.extend([
            TemperatureSensor(observations_coord, office_code, latitude, longitude),
            HumiditySensor(observations_coord, office_code, latitude, longitude),
            WindSpeedSensor(observations_coord, office_code, latitude, longitude),
            WindDirectionSensor(observations_coord, office_code, latitude, longitude),
            BarometricPressureSensor(observations_coord, office_code, latitude, longitude),
            DewpointSensor(observations_coord, office_code, latitude, longitude),
            VisibilitySensor(observations_coord, office_code, latitude, longitude),
            SkyConditionsSensor(observations_coord, office_code, latitude, longitude),
            FeelsLikeSensor(observations_coord, office_code, latitude, longitude),
        ])

    # Forecast sensors (location-specific)
    if forecast_coord:
        entities.extend([
            ExtendedForecastSensor(forecast_coord, office_code, latitude, longitude),
            HourlyForecastSensor(forecast_coord, office_code, latitude, longitude),
        ])

    # NWS alerts sensor (location-specific)
    if alerts_coord:
        entities.append(NWSAlertsSensor(alerts_coord, office_code, latitude, longitude))

    # Cloud cover sensor (location-specific)
    if cloud_cover_coord:
        entities.append(CloudCoverSensor(cloud_cover_coord, office_code, latitude, longitude))

    # Meteor shower sensors (location-specific, grouped under the Space device)
    if meteor_coord:
        entities.extend([
            MeteorShowerActivitySensor(meteor_coord, office_code),
            NextMeteorShowerSensor(meteor_coord, office_code),
            MeteorViewingScoreSensor(meteor_coord, office_code),
        ])

    # Tsunami sensors are global (NTWC/PTWC) and grouped under a single
    # dedicated NOAA Tsunami device, so the four national ones are added
    # only once across all configured offices — same ownership-transfer
    # dance as the hurricane sensors above.
    if tsunami_coord and not domain_data.get(TSUNAMI_SENSORS_ADDED_KEY):
        entities.extend([
            TsunamiThreatLevelSensor(tsunami_coord),
            TsunamiActiveAlertsSensor(tsunami_coord),
            TsunamiSourceEarthquakeSensor(tsunami_coord),
            TsunamiLastMessageSensor(tsunami_coord),
        ])
        domain_data[TSUNAMI_SENSORS_ADDED_KEY] = config_entry.entry_id

        def _release_tsunami_sensor_ownership() -> None:
            """Release tsunami-sensor ownership and re-create on a remaining entry."""
            if domain_data.get(TSUNAMI_SENSORS_ADDED_KEY) != config_entry.entry_id:
                return
            domain_data.pop(TSUNAMI_SENSORS_ADDED_KEY, None)
            remaining = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != config_entry.entry_id
            ]
            if remaining:
                target_entry_id = remaining[0].entry_id

                async def _reload_for_tsunami_sensors() -> None:
                    try:
                        await hass.config_entries.async_reload(target_entry_id)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed to reload entry %s to re-create global "
                            "tsunami sensors", target_entry_id,
                        )

                hass.async_create_task(_reload_for_tsunami_sensors())

        config_entry.async_on_unload(_release_tsunami_sensor_ownership)

    # Location-specific tsunami sensors, for coastal offices only. These are
    # per-office rather than global, so they are created on every entry whose
    # office has coastline — the ten Great Lakes offices get none.
    if tsunami_coord and office_code in OFFICE_TSUNAMI_CENTERS:
        entities.append(
            TsunamiWaveArrivalSensor(tsunami_coord, office_code, latitude, longitude)
        )
        if alerts_coord:
            entities.extend([
                TsunamiLocalThreatSensor(alerts_coord, office_code, latitude, longitude),
                TsunamiEvacuationStatusSensor(
                    alerts_coord, office_code, latitude, longitude
                ),
            ])

    # Radar timestamp sensor (office-specific, may be None if no radar site)
    if radar_coord:
        entities.append(RadarTimestampSensor(radar_coord, office_code))

    # Forecast discussion sensor (office-specific)
    entities.append(ForecastDiscussionSensor(discussion_coord, office_code))

    async_add_entities(entities)
