"""Binary sensor platform for NOAA Integration."""
import logging
import re
from datetime import datetime, timedelta, timezone

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, DOMAIN,
    METEOR_ACTIVE_MIN_RATE, METEOR_ACTIVE_MIN_SCORE,
    TSUNAMI_BINARY_SENSORS_ADDED_KEY, TSUNAMI_STALE_AFTER, TSUNAMI_THREAT_LEVELS,
)
from .parsers import parse_tsunami_alert_features
from .sensors.meteor_showers import space_device_info
from .sensors.tsunami import tsunami_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up binary sensor platform (legacy YAML support)."""
    _LOGGER.warning("NOAA binary sensors require location configuration. Please use config flow setup.")
    return


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA binary sensors from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

    data = hass.data[DOMAIN][config_entry.entry_id]
    surf_coord = data["surf_coordinator"]
    alerts_coord = data["alerts_coordinator"]
    meteor_coord = data["meteor_coordinator"]
    tsunami_coord = data["tsunami_coordinator"]

    entities = [UnsafeToSwimBinarySensor(surf_coord, office_code)]

    if alerts_coord and latitude is not None and longitude is not None:
        entities.extend([
            SevereWeatherAlertBinarySensor(alerts_coord, office_code, latitude, longitude),
            FloodWinterAlertBinarySensor(alerts_coord, office_code, latitude, longitude),
            HeatAirQualityAlertBinarySensor(alerts_coord, office_code, latitude, longitude),
            ActiveAlertsGeneralBinarySensor(alerts_coord, office_code, latitude, longitude),
        ])

    if meteor_coord:
        entities.append(MeteorShowerActiveBinarySensor(meteor_coord, office_code))

    # Tsunami binary sensors are global and grouped under the single NOAA
    # Tsunami device. Only add them once across all configured NWS offices,
    # tracking the owning entry so ownership can transfer if it is unloaded.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if tsunami_coord and not domain_data.get(TSUNAMI_BINARY_SENSORS_ADDED_KEY):
        entities.extend([
            TsunamiAlertBinarySensor(tsunami_coord),
            TsunamiDataStaleBinarySensor(tsunami_coord),
        ])
        domain_data[TSUNAMI_BINARY_SENSORS_ADDED_KEY] = config_entry.entry_id

        def _release_tsunami_binary_sensor_ownership() -> None:
            """Release ownership and re-create on a remaining entry."""
            if domain_data.get(TSUNAMI_BINARY_SENSORS_ADDED_KEY) != config_entry.entry_id:
                return
            domain_data.pop(TSUNAMI_BINARY_SENSORS_ADDED_KEY, None)
            remaining = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != config_entry.entry_id
            ]
            if remaining:
                target_entry_id = remaining[0].entry_id

                async def _reload_for_tsunami_binary_sensors() -> None:
                    try:
                        await hass.config_entries.async_reload(target_entry_id)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed to reload entry %s to re-create global "
                            "tsunami binary sensors", target_entry_id,
                        )

                hass.async_create_task(_reload_for_tsunami_binary_sensors())

        config_entry.async_on_unload(_release_tsunami_binary_sensor_ownership)

    async_add_entities(entities)


class UnsafeToSwimBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for unsafe swimming conditions based on rip current forecasts."""

    _attr_has_entity_name = True

    _HIGH_RISK_PATTERNS = [
        r"high\s+rip\s+current\s+risk",
        r"dangerous\s+rip\s+currents",
        r"high\s+surf\s+and\s+dangerous\s+rip\s+currents",
        r"rip\s+current\s+risk\s+is\s+high",
    ]

    _MODERATE_RISK_PATTERNS = [
        r"moderate\s+rip\s+current\s+risk",
        r"rip\s+current\s+risk\s+is\s+moderate",
        r"moderate\s+surf\s+and\s+rip\s+currents",
    ]

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_unsafe_to_swim"
        self._attr_name = "Unsafe to Swim"

    def _check_risk(self):
        """Return (high_risk_found, moderate_risk_found) from coordinator data."""
        if not self.coordinator.data:
            return False, False
        forecast_text = self.coordinator.data.get("forecast_text", "")
        high = any(re.search(p, forecast_text) for p in self._HIGH_RISK_PATTERNS)
        moderate = any(re.search(p, forecast_text) for p in self._MODERATE_RISK_PATTERNS)
        return high, moderate

    @property
    def is_on(self):
        """Return true if unsafe to swim."""
        high, _ = self._check_risk()
        return high

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:swim-off'
        return 'mdi:swim'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        high_risk_found, moderate_risk_found = self._check_risk()
        risk_level = "High" if high_risk_found else ("Moderate" if moderate_risk_found else "Low")
        return {
            'office_code': self._office_code,
            'risk_level': risk_level,
            'forecast_source': self.coordinator.data.get("source_url", ""),
            'last_updated': 'Available in forecast',
            'high_risk_detected': high_risk_found,
            'moderate_risk_detected': moderate_risk_found,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_surf")},
            name=f"NOAA {self._office_code} Surf",
            manufacturer="NOAA"
        )


class SevereWeatherAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for severe/hazardous weather warnings (tornado, thunderstorm, etc.)."""

    _attr_has_entity_name = True

    _SEVERE_EVENTS = [
        'tornado warning', 'tornado watch',
        'severe thunderstorm warning', 'severe thunderstorm watch',
        'severe weather statement',
        'hurricane warning', 'hurricane watch',
        'tropical storm warning', 'tropical storm watch',
        'extreme wind warning', 'high wind warning', 'high wind watch',
        'hazardous weather outlook',
        'special weather statement',
        'hazardous seas warning', 'hazardous seas watch',
        'storm surge warning', 'storm surge watch',
        'tsunami warning', 'tsunami watch', 'tsunami advisory',
        'typhoon warning', 'typhoon watch',
    ]

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_severe_weather_alert"
        self._attr_name = "Severe Weather Alert"

    def _get_filtered_alerts(self):
        """Return list of active severe weather alerts from coordinator data."""
        if not self.coordinator.data:
            return []
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', '').lower()
            status = props.get('status', '').lower()
            if status == 'actual' and any(se in event for se in self._SEVERE_EVENTS):
                active_alerts.append({
                    'event': props.get('event', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
        return active_alerts

    @property
    def is_on(self):
        """Return true if there is an active severe weather alert."""
        return len(self._get_filtered_alerts()) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:weather-lightning'
        return 'mdi:weather-partly-cloudy'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alerts': active_alerts[:5],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class FloodWinterAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for flood and winter weather alerts."""

    _attr_has_entity_name = True

    _FLOOD_WINTER_EVENTS = [
        'flood warning', 'flood watch', 'flash flood warning', 'flash flood watch',
        'coastal flood warning', 'coastal flood watch', 'lakeshore flood warning',
        'flood advisory', 'coastal flood advisory', 'lakeshore flood advisory',
        'flood statement', 'flash flood statement', 'coastal flood statement', 'lakeshore flood statement',
        'winter storm warning', 'winter storm watch', 'winter weather advisory',
        'blizzard warning', 'ice storm warning', 'lake effect snow warning',
        'heavy snow warning', 'snow squall warning',
        'freezing rain advisory', 'freezing fog advisory', 'sleet advisory',
        'wind chill warning', 'wind chill advisory',
        'extreme cold warning', 'extreme cold watch', 'cold weather advisory',
    ]

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_flood_winter_alert"
        self._attr_name = "Flood/Winter Alert"

    def _get_filtered_alerts(self):
        """Return list of active flood/winter alerts from coordinator data."""
        if not self.coordinator.data:
            return []
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', '').lower()
            status = props.get('status', '').lower()
            if status == 'actual' and any(fe in event for fe in self._FLOOD_WINTER_EVENTS):
                active_alerts.append({
                    'event': props.get('event', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
        return active_alerts

    @property
    def is_on(self):
        """Return true if there is an active flood or winter weather alert."""
        return len(self._get_filtered_alerts()) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:snowflake-alert'
        return 'mdi:weather-snowy'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alerts': active_alerts[:5],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class HeatAirQualityAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for heat, air quality, and other environmental advisories."""

    _attr_has_entity_name = True

    _HEAT_AIRQUALITY_EVENTS = [
        'excessive heat warning', 'excessive heat watch', 'heat advisory',
        'extreme heat warning', 'extreme heat watch',
        'air quality alert', 'air stagnation advisory',
        'red flag warning', 'fire weather watch', 'extreme fire danger',
        'dense fog advisory', 'dense smoke advisory',
        'dust storm warning', 'blowing dust advisory', 'blowing dust warning',
        'freeze warning', 'freeze watch', 'frost advisory',
        'ashfall warning', 'ashfall advisory',
        'volcano warning',
    ]

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_heat_air_quality_alert"
        self._attr_name = "Heat/Air Quality Alert"

    def _get_filtered_alerts(self):
        """Return list of active heat/air quality alerts from coordinator data."""
        if not self.coordinator.data:
            return []
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', '').lower()
            status = props.get('status', '').lower()
            if status == 'actual' and any(he in event for he in self._HEAT_AIRQUALITY_EVENTS):
                active_alerts.append({
                    'event': props.get('event', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
        return active_alerts

    @property
    def is_on(self):
        """Return true if there is an active heat or air quality alert."""
        return len(self._get_filtered_alerts()) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:fire-alert'
        return 'mdi:thermometer'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alerts': active_alerts[:5],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class ActiveAlertsGeneralBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for general active NWS alerts for the configured location."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_active_alerts"
        self._attr_name = "Active Alerts"

    def _get_filtered_alerts(self):
        """Return list of all active alerts and type counts from coordinator data."""
        if not self.coordinator.data:
            return [], {}
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        alert_types = {}
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', 'Unknown')
            status = props.get('status', '').lower()
            if status == 'actual':
                active_alerts.append({
                    'event': event,
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
                alert_types[event] = alert_types.get(event, 0) + 1
        return active_alerts, alert_types

    @property
    def is_on(self):
        """Return true if there are any active alerts."""
        active_alerts, _ = self._get_filtered_alerts()
        return len(active_alerts) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:alert'
        return 'mdi:check-circle'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts, alert_types = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alert_types': alert_types,
            'alerts': active_alerts[:10],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class MeteorShowerActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that turns on when a meteor shower is genuinely worth going outside for.

    This is the entity to trigger automations from. It is deliberately *not* a bare "is any
    shower active" flag: with around thirty showers catalogued something is technically active on
    most nights of the year, so such a flag would sit permanently on. Instead it requires a real
    predicted rate and usable sky geometry.

    Measured over 2026 from Wilmington NC that turns on for roughly 50 nights, clustered tightly
    around the major showers — about thirteen for the Perseids, eight for the Orionids, seven for
    the Geminids. That is not an arbitrary number: with a published activity slope of 0.2 the
    Perseids genuinely stay above five meteors an hour for about six days either side of
    maximum. Raise ``METEOR_ACTIVE_MIN_RATE`` if you only want to hear about the peak nights.

    Unlike the other binary sensors in this module it sets ``_attr_has_entity_name``, matching the
    sensor convention, so the entity ID carries the ``space`` device segment
    (``binary_sensor.noaa_ilm_space_meteor_shower_active``) and reads as a sibling of the meteor
    sensors rather than an orphan.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._attr_unique_id = f"noaa_{office_code}_meteor_shower_active"

    @property
    def name(self):
        """Return the local name of the binary sensor."""
        return "Meteor Shower Active"

    @property
    def _best(self):
        """Return tonight's best shower entry, or None when nothing is active."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("best")

    @property
    def is_on(self):
        """Return true when a worthwhile shower is observable tonight."""
        best = self._best
        if not best:
            return False
        return (
            best['expected_per_hour'] >= METEOR_ACTIVE_MIN_RATE
            and best['viewing_score'] >= METEOR_ACTIVE_MIN_SCORE
        )

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:meteor'
        return 'mdi:weather-night'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            'office_code': self._office_code,
            'minimum_rate': METEOR_ACTIVE_MIN_RATE,
            'minimum_score': METEOR_ACTIVE_MIN_SCORE,
        }
        best = self._best
        if not best:
            return attrs

        attrs.update({
            'shower': best['name'],
            'shower_code': best['code'],
            'zhr_now': best['zhr_now'],
            'expected_per_hour': best['expected_per_hour'],
            'viewing_score': best['viewing_score'],
            'rating': best['rating'],
            'peak_local': best['peak_local'],
            'days_until': best['days_until'],
            'is_peak_night': best['is_peak_night'],
            'best_window_start': best['best_window_start'],
            'best_window_end': best['best_window_end'],
            'limiting_factor': best['limiting_factor'],
        })
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return space_device_info(self._office_code)


class TsunamiAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Turns on when a tsunami Warning or Advisory is in effect in US waters.

    Watches and Information Statements deliberately do not trip this sensor. A
    Watch means a distant earthquake happened and a tsunami is merely possible,
    and an Information Statement usually means there is no threat at all —
    firing an evacuation automation on either would train users to ignore it.
    """

    _attr_has_entity_name = True

    #: Levels that represent a real, present danger to people near the water.
    _ACTIONABLE_LEVELS = ('Warning', 'Advisory')

    def __init__(self, coordinator):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = 'noaa_tsunami_alert_active'
        self._attr_name = 'Alert Active'

    def _summary(self):
        """Return the parsed tsunami alert summary."""
        features = self.coordinator.data.get('features') if self.coordinator.data else None
        _, summary = parse_tsunami_alert_features(features, TSUNAMI_THREAT_LEVELS)
        return summary

    @property
    def is_on(self):
        """Return true when a Warning or Advisory is active."""
        return self._summary()['threat_level'] in self._ACTIONABLE_LEVELS

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:tsunami' if self.is_on else 'mdi:water-off-outline'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        summary = self._summary()
        features = self.coordinator.data.get('features') if self.coordinator.data else None
        alerts, _ = parse_tsunami_alert_features(features, TSUNAMI_THREAT_LEVELS)
        return {
            'threat_level': summary['threat_level'],
            'alert_count': summary['alert_count'],
            'areas': summary['areas'],
            'highest_severity': summary['highest_severity'],
            'alerts': alerts[:5],
            'last_test_message': summary['last_test_message'],
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return tsunami_device_info()


class TsunamiDataStaleBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Turns on when the tsunami feed has stopped answering.

    This is the safety net for the whole domain. Every other tsunami entity
    reports "no threat" when the feed returns nothing, and that reading is
    indistinguishable from a feed that died hours ago unless something says so
    out loud. Wire this into a notification: a silent failure on life-safety
    data is the failure mode that actually hurts people.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = 'noaa_tsunami_data_stale'
        self._attr_name = 'Data Stale'

    def _last_success(self):
        """Return the coordinator's last successful fetch time, or ``None``."""
        return getattr(self.coordinator, 'last_success', None)

    def _age_minutes(self):
        """Return minutes since the last successful fetch, or ``None``."""
        last = self._last_success()
        if last is None:
            return None
        return (datetime.now(timezone.utc) - last).total_seconds() / 60

    @property
    def is_on(self):
        """Return true when the data is stale or has never arrived."""
        last = self._last_success()
        if last is None:
            # Never fetched successfully. That is the most stale state there is.
            return True
        return datetime.now(timezone.utc) - last > timedelta(minutes=TSUNAMI_STALE_AFTER)

    @property
    def device_class(self):
        """Return the device class."""
        return 'problem'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:cloud-alert' if self.is_on else 'mdi:cloud-check-outline'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        age = self._age_minutes()
        last = self._last_success()
        return {
            'last_success': last.isoformat() if last else None,
            'age_minutes': round(age, 1) if age is not None else None,
            'stale_after_minutes': TSUNAMI_STALE_AFTER,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return tsunami_device_info()
