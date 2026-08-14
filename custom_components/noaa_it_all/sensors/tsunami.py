"""Tsunami sensors for NOAA Integration.

Seven sensors on a single global ``NOAA Tsunami`` device, in two tiers.

The four global sensors answer "is there a tsunami alert anywhere in US waters,
and what caused it" and exist on every install. The three location sensors —
local threat, wave arrival, evacuation status — are only created for offices
listed in ``OFFICE_TSUNAMI_CENTERS``, since the ten Great Lakes offices have no
tsunami exposure and permanently-dead entities help nobody.

Two behaviours here are deliberate and load-bearing, because this is
life-safety data:

* A threat level of ``None`` (Home Assistant ``unknown``) means *no data*,
  while the string ``"None"`` means *fetched successfully, nothing active*.
  Collapsing the two would let a dead feed read as an all-clear.
* Test messages never move the threat level, but the most recent one is exposed
  as an attribute. The NWS runs tsunami communications tests monthly, and on a
  normal install that is the only traffic this domain will ever see — it is how
  a user confirms the pipeline still works between real events.
"""

import logging

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import (
    DOMAIN, TSUNAMI_DEVICE_ID, TSUNAMI_DEVICE_NAME, TSUNAMI_THREAT_LEVELS,
)
from ..parsers import (
    parse_tsunami_alert_features, find_source_earthquake, estimate_wave_arrival,
)

_LOGGER = logging.getLogger(__name__)

#: Icon per threat level, so a dashboard reads at a glance.
_LEVEL_ICONS = {
    "Warning": "mdi:tsunami",
    "Advisory": "mdi:waves-arrow-up",
    "Watch": "mdi:wave",
    "Information": "mdi:information-outline",
}


def tsunami_device_info() -> DeviceInfo:
    """Return the shared device info for all NOAA Tsunami entities.

    Mirrors ``_hurricane_device_info`` in ``sensors/hurricanes.py``. Tsunami
    alerts come from the two national warning centers and cover ocean basins,
    so they must not be attached to an office-specific weather device.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, TSUNAMI_DEVICE_ID)},
        name=TSUNAMI_DEVICE_NAME,
        manufacturer="NOAA",
    )


class _TsunamiBaseSensor(CoordinatorEntity):
    """Shared plumbing for the global tsunami sensors.

    Uses ``_attr_has_entity_name = True`` so Home Assistant combines the device
    name with the local entity name, producing entity IDs like
    ``sensor.noaa_tsunami_threat_level``.
    """

    _attr_has_entity_name = True

    @property
    def _data(self):
        """Return the coordinator payload, or an empty dict before first refresh."""
        return self.coordinator.data or {}

    @property
    def _features(self):
        """Return raw NWS features, or ``None`` when no fetch has succeeded."""
        if not self.coordinator.data:
            return None
        return self._data.get("features")

    @property
    def _summary(self):
        """Return the parsed tsunami alert summary."""
        _, summary = parse_tsunami_alert_features(self._features, TSUNAMI_THREAT_LEVELS)
        return summary

    @property
    def _alerts(self):
        """Return the parsed list of live tsunami alerts."""
        alerts, _ = parse_tsunami_alert_features(self._features, TSUNAMI_THREAT_LEVELS)
        return alerts

    @property
    def _products(self):
        """Return all recent NTWC/PTWC product entries, newest first."""
        return self._data.get("products") or []

    @property
    def _latest_product(self):
        """Return the most recent NTWC/PTWC product entry, or ``None``."""
        products = self._products
        return products[0] if products else None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return tsunami_device_info()


class TsunamiThreatLevelSensor(_TsunamiBaseSensor):
    """Highest tsunami alert level in effect anywhere in US waters."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Threat Level"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return "noaa_tsunami_threat_level"

    @property
    def state(self):
        """Return the highest active level, or ``None`` when there is no data."""
        return self._summary["threat_level"]

    @property
    def icon(self):
        """Return an icon reflecting the current level."""
        return _LEVEL_ICONS.get(self.state, "mdi:water-off-outline")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        summary = self._summary
        return {
            "alerts": self._alerts[:10],
            "alert_count": summary["alert_count"],
            "by_level": summary["by_level"],
            "areas": summary["areas"],
            "issuing_centers": summary["issuing_centers"],
            "highest_severity": summary["highest_severity"],
            "latest_issued": summary["latest_issued"],
            "last_test_message": summary["last_test_message"],
        }


class TsunamiActiveAlertsSensor(_TsunamiBaseSensor):
    """How many tsunami alerts are currently in effect nationally."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Active Alerts"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return "noaa_tsunami_active_alerts"

    @property
    def state(self):
        """Return the alert count, or ``None`` before the first successful fetch."""
        if self._features is None:
            return None
        return self._summary["alert_count"]

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:alert-circle" if self.state else "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        summary = self._summary
        return {
            "alerts": self._alerts[:10],
            "areas": summary["areas"],
            "by_level": summary["by_level"],
        }


class TsunamiSourceEarthquakeSensor(_TsunamiBaseSensor):
    """Magnitude of the last earthquake the warning centers evaluated.

    Not only quakes that caused a tsunami. The centers publish a statement for
    every notable one and most come to nothing, so on a quiet day this reports
    the most recent quake they looked at and dismissed — which is the most
    interesting thing this domain has to say when nothing is wrong.
    """

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Source Earthquake"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return "noaa_tsunami_source_earthquake"

    @property
    def _source(self):
        """Return the newest product that names a quake."""
        return find_source_earthquake(self._products)

    @property
    def state(self):
        """Return the preliminary magnitude, or ``None`` when unknown."""
        return self._source["magnitude"]

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:pulse"

    @property
    def extra_state_attributes(self):
        """Return the state attributes.

        The product title and link are always present, even when no magnitude
        could be recovered, so the entity is never a dead end — there is always
        something to read and somewhere to click through to.
        """
        source = self._source
        product = self._latest_product or {}
        return {
            "depth_km": source["depth_km"],
            "epicenter_latitude": source["epicenter_latitude"],
            "epicenter_longitude": source["epicenter_longitude"],
            "region": source["region"],
            "origin_time": source["origin_time"],
            "center": product.get("center"),
            "product": product.get("title"),
            "summary": product.get("summary"),
            "link": product.get("link"),
            "products_available": len(self._products),
        }


class TsunamiLastMessageSensor(_TsunamiBaseSensor):
    """When the warning centers last issued a tsunami product."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Last Message"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return "noaa_tsunami_last_message"

    @property
    def state(self):
        """Return the issue time of the newest product, or ``None``."""
        product = self._latest_product
        return product.get("updated") if product else None

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:message-alert-outline"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        product = self._latest_product or {}
        products = self._data.get("products") or []
        return {
            "center": product.get("center"),
            "title": product.get("title"),
            "message_type": product.get("message_type"),
            "level": product.get("level"),
            "summary": product.get("summary"),
            "link": product.get("link"),
            "recent_products": products[:5],
        }


class _TsunamiOfficeSensor(_TsunamiBaseSensor):
    """Base for the location-specific tsunami sensors.

    These carry the office code in their name so that they remain distinct on
    the shared global device when more than one coastal office is configured.
    """

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude


class TsunamiLocalThreatSensor(_TsunamiOfficeSensor):
    """Tsunami alert level in effect for the user's own coordinates.

    Reads the existing ``NWSAlertsCoordinator`` rather than the tsunami one:
    that coordinator already queries ``alerts/active?point=lat,lon``, so the
    alerts for this exact location are in a payload the integration is fetching
    anyway. No additional request is made for this entity.
    """

    @property
    def name(self):
        """Return the local name of the sensor."""
        return f"{self._office_code} Local Threat"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_tsunami_{self._office_code}_local_threat"

    @property
    def _features(self):
        """Return the point-query features from the shared alerts coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("features")

    @property
    def state(self):
        """Return the local threat level, or ``None`` when there is no data."""
        return self._summary["threat_level"]

    @property
    def icon(self):
        """Return an icon reflecting the local level."""
        return _LEVEL_ICONS.get(self.state, "mdi:water-off-outline")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        summary = self._summary
        return {
            "office_code": self._office_code,
            "latitude": self._latitude,
            "longitude": self._longitude,
            "alerts": self._alerts[:5],
            "alert_count": summary["alert_count"],
            "areas": summary["areas"],
            "highest_severity": summary["highest_severity"],
            "last_test_message": summary["last_test_message"],
        }


class TsunamiWaveArrivalSensor(_TsunamiOfficeSensor):
    """Estimated tsunami wave arrival time at the nearest forecast point."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return f"{self._office_code} Wave Arrival"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_tsunami_{self._office_code}_wave_arrival"

    @property
    def _arrival(self):
        """Return the nearest arrival forecast, or ``None`` when none is published."""
        cap = self._data.get("cap") or {}
        return estimate_wave_arrival(
            cap.get("areas"), self._latitude, self._longitude
        )

    @property
    def state(self):
        """Return the estimated arrival time, or a plain-language quiet state.

        ``None`` (Home Assistant ``unknown``) is reserved for "no data has been
        fetched". Once the feed is answering and simply has no event to report,
        the state says so in words rather than sitting on ``unknown``, which
        reads like a fault.
        """
        arrival = self._arrival
        if arrival:
            return arrival["arrival_time"]
        if not self.coordinator.data:
            return None
        return "No active event"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:clock-alert-outline" if self._arrival else "mdi:clock-outline"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        arrival = self._arrival or {}
        cap = self._data.get("cap") or {}
        return {
            "office_code": self._office_code,
            "forecast_point": arrival.get("forecast_point"),
            "distance_km": arrival.get("distance_km"),
            "center": cap.get("center"),
            "event": cap.get("event"),
            "expires": cap.get("expires"),
            "forecast_points_available": len(cap.get("areas") or []),
        }


class TsunamiEvacuationStatusSensor(_TsunamiOfficeSensor):
    """What the warning center is telling people at this location to do.

    Reads the same shared ``NWSAlertsCoordinator`` payload as the local threat
    sensor. The state is a short action label suitable for a dashboard or a
    spoken notification; the full instruction text is an attribute.
    """

    #: Action label per level. These follow the official meanings: a Warning
    #: means move inland or to high ground, an Advisory means stay out of the
    #: water but not evacuate, a Watch means stay alert for updates.
    _ACTIONS = {
        "Warning": "Move to high ground",
        "Advisory": "Stay out of the water",
        "Watch": "Stay alert for updates",
        "Information": "No action required",
    }

    @property
    def name(self):
        """Return the local name of the sensor."""
        return f"{self._office_code} Evacuation Status"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_tsunami_{self._office_code}_evacuation_status"

    @property
    def _features(self):
        """Return the point-query features from the shared alerts coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("features")

    @property
    def state(self):
        """Return the action label, or ``None`` when there is no data."""
        level = self._summary["threat_level"]
        if level is None:
            return None
        return self._ACTIONS.get(level, "No action required")

    @property
    def icon(self):
        """Return the icon."""
        level = self._summary["threat_level"]
        if level == "Warning":
            return "mdi:run-fast"
        if level == "Advisory":
            return "mdi:swim-off"
        return "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        alerts = self._alerts
        instruction = next(
            (a["instruction"] for a in alerts if a.get("instruction")), None
        )
        return {
            "office_code": self._office_code,
            "threat_level": self._summary["threat_level"],
            "instruction": instruction,
            "headline": alerts[0]["headline"] if alerts else None,
            "area": alerts[0]["area"] if alerts else None,
            "expires": alerts[0]["expires"] if alerts else None,
        }
