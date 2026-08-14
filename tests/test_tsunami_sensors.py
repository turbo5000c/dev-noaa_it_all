"""Tests for the tsunami sensor and binary sensor entities.

Follows the repository's established pattern for entity tests: Home Assistant is
replaced with MagicMocks at import time, coordinators are stubbed with a fixture
payload, and the entity classes are imported inside the test methods once the
patch is active.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
_FIXTURES = os.path.join(_REPO, "tests", "fixtures")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_entity = MagicMock()
_ha_coordinator = MagicMock()

_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_entity.DeviceInfo = dict

_ha_binary_sensor = MagicMock()
_ha_binary_sensor.BinarySensorEntity = type("BinarySensorEntity", (), {})

_ha_image = MagicMock()
_ha_image.ImageEntity = type("ImageEntity", (), {
    "__init__": lambda self, hass: setattr(self, "hass", hass),
})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": _ha_binary_sensor,
    "homeassistant.components.image": _ha_image,
    "homeassistant.const": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.util": MagicMock(),
    "homeassistant.util.dt": MagicMock(),
    "aiohttp": MagicMock(),
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


OFFICE = "ILM"
LAT = 34.2675
LON = -77.9011


def _load_fixture(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return json.load(f)


def _load_text(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return f.read()


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


def _tsunami_payload(alert_fixture="tsunami_alerts.json"):
    """Build a TsunamiCoordinator-shaped payload from the fixtures."""
    from noaa_it_all.parsers import parse_tsunami_atom_feed, parse_tsunami_cap
    levels = ("Warning", "Advisory", "Watch", "Information")
    cap = parse_tsunami_cap(_load_text("tsunami_cap.xml"))
    cap["center"] = "NTWC"
    return {
        "features": _load_fixture(alert_fixture)["features"],
        "products": parse_tsunami_atom_feed(
            _load_text("tsunami_atom_ntwc.xml"), "NTWC", levels
        ),
        "cap": cap,
        "last_success": datetime.now(timezone.utc),
    }


class TestTsunamiThreatLevelSensor(unittest.TestCase):
    """The headline sensor for the domain."""

    def _sensor(self, data):
        from noaa_it_all.sensors.tsunami import TsunamiThreatLevelSensor
        return TsunamiThreatLevelSensor(_make_coordinator(data))

    def test_state_is_highest_level(self):
        self.assertEqual(self._sensor(_tsunami_payload()).state, "Warning")

    def test_state_when_quiet(self):
        sensor = self._sensor(_tsunami_payload("tsunami_quiet.json"))
        self.assertEqual(sensor.state, "None")

    def test_state_before_first_refresh_is_unknown(self):
        """No data must be None, not the string 'None'.

        Home Assistant renders None as 'unknown'. If this ever returned "None"
        an automation could read a dead feed as an all-clear.
        """
        self.assertIsNone(self._sensor(None).state)

    def test_name(self):
        self.assertEqual(self._sensor(None).name, "Threat Level")

    def test_unique_id(self):
        self.assertEqual(
            self._sensor(None).unique_id, "noaa_tsunami_threat_level"
        )

    def test_icon_when_warning(self):
        self.assertEqual(self._sensor(_tsunami_payload()).icon, "mdi:tsunami")

    def test_icon_when_quiet(self):
        sensor = self._sensor(_tsunami_payload("tsunami_quiet.json"))
        self.assertEqual(sensor.icon, "mdi:water-off-outline")

    def test_attributes(self):
        attrs = self._sensor(_tsunami_payload()).extra_state_attributes
        for key in ("alerts", "alert_count", "by_level", "areas",
                    "issuing_centers", "highest_severity", "latest_issued",
                    "last_test_message"):
            self.assertIn(key, attrs)

    def test_attributes_exclude_non_tsunami_alerts(self):
        attrs = self._sensor(_tsunami_payload()).extra_state_attributes
        self.assertEqual(attrs["alert_count"], 2)
        for alert in attrs["alerts"]:
            self.assertIn("tsunami", alert["event"].lower())

    def test_device_info(self):
        info = self._sensor(None).device_info
        self.assertEqual(info["name"], "NOAA Tsunami")


class TestTsunamiActiveAlertsSensor(unittest.TestCase):
    """National tsunami alert count."""

    def _sensor(self, data):
        from noaa_it_all.sensors.tsunami import TsunamiActiveAlertsSensor
        return TsunamiActiveAlertsSensor(_make_coordinator(data))

    def test_state(self):
        self.assertEqual(self._sensor(_tsunami_payload()).state, 2)

    def test_state_when_quiet(self):
        self.assertEqual(
            self._sensor(_tsunami_payload("tsunami_quiet.json")).state, 0
        )

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_name_and_unique_id(self):
        sensor = self._sensor(None)
        self.assertEqual(sensor.name, "Active Alerts")
        self.assertEqual(sensor.unique_id, "noaa_tsunami_active_alerts")

    def test_icon(self):
        self.assertEqual(self._sensor(_tsunami_payload()).icon, "mdi:alert-circle")
        self.assertEqual(
            self._sensor(_tsunami_payload("tsunami_quiet.json")).icon,
            "mdi:check-circle-outline",
        )

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiSourceEarthquakeSensor(unittest.TestCase):
    """The quake behind the alert."""

    def _sensor(self, data):
        from noaa_it_all.sensors.tsunami import TsunamiSourceEarthquakeSensor
        return TsunamiSourceEarthquakeSensor(_make_coordinator(data))

    def test_state_is_magnitude(self):
        self.assertEqual(self._sensor(_tsunami_payload()).state, 7.8)

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_name_and_unique_id(self):
        sensor = self._sensor(None)
        self.assertEqual(sensor.name, "Source Earthquake")
        self.assertEqual(sensor.unique_id, "noaa_tsunami_source_earthquake")

    def test_attributes(self):
        attrs = self._sensor(_tsunami_payload()).extra_state_attributes
        self.assertEqual(attrs["depth_km"], 32.0)
        self.assertEqual(attrs["epicenter_latitude"], 54.7)
        self.assertEqual(attrs["epicenter_longitude"], -161.3)
        self.assertEqual(attrs["center"], "NTWC")

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiLastMessageSensor(unittest.TestCase):
    """Most recent warning-center product."""

    def _sensor(self, data):
        from noaa_it_all.sensors.tsunami import TsunamiLastMessageSensor
        return TsunamiLastMessageSensor(_make_coordinator(data))

    def test_state(self):
        self.assertEqual(
            self._sensor(_tsunami_payload()).state, "2026-08-14T11:02:00Z"
        )

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_name_and_unique_id(self):
        sensor = self._sensor(None)
        self.assertEqual(sensor.name, "Last Message")
        self.assertEqual(sensor.unique_id, "noaa_tsunami_last_message")

    def test_attributes(self):
        attrs = self._sensor(_tsunami_payload()).extra_state_attributes
        self.assertEqual(attrs["center"], "NTWC")
        self.assertEqual(attrs["message_type"], "New")
        self.assertEqual(attrs["level"], "Warning")
        self.assertEqual(len(attrs["recent_products"]), 2)

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiLocalThreatSensor(unittest.TestCase):
    """Reads the shared point-query alerts coordinator, not the tsunami one."""

    def _sensor(self, data):
        from noaa_it_all.sensors.tsunami import TsunamiLocalThreatSensor
        return TsunamiLocalThreatSensor(_make_coordinator(data), OFFICE, LAT, LON)

    def test_state(self):
        data = {"features": _load_fixture("tsunami_alerts.json")["features"]}
        self.assertEqual(self._sensor(data).state, "Warning")

    def test_state_when_quiet(self):
        self.assertEqual(self._sensor({"features": []}).state, "None")

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_name_carries_office_code(self):
        self.assertEqual(self._sensor(None).name, "ILM Local Threat")

    def test_unique_id(self):
        self.assertEqual(
            self._sensor(None).unique_id, "noaa_tsunami_ILM_local_threat"
        )

    def test_attributes(self):
        data = {"features": _load_fixture("tsunami_alerts.json")["features"]}
        attrs = self._sensor(data).extra_state_attributes
        self.assertEqual(attrs["office_code"], OFFICE)
        self.assertEqual(attrs["latitude"], LAT)
        self.assertEqual(attrs["alert_count"], 2)

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiWaveArrivalSensor(unittest.TestCase):
    """Estimated arrival at the nearest forecast point."""

    def _sensor(self, data, office=OFFICE, lat=LAT, lon=LON):
        from noaa_it_all.sensors.tsunami import TsunamiWaveArrivalSensor
        return TsunamiWaveArrivalSensor(_make_coordinator(data), office, lat, lon)

    def test_state_picks_nearest_point(self):
        sensor = self._sensor(_tsunami_payload())
        self.assertEqual(sensor.state, "2026-08-14T22:10:00-00:00")

    def test_west_coast_office_gets_west_coast_point(self):
        sensor = self._sensor(_tsunami_payload(), "EKA", 40.9789, -124.1085)
        self.assertEqual(sensor.state, "2026-08-14T15:40:00-00:00")
        self.assertEqual(
            sensor.extra_state_attributes["forecast_point"], "Crescent City, CA"
        )

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_state_when_no_cap_reads_as_quiet_not_unknown(self):
        """A healthy feed with no event says so, rather than looking broken."""
        self.assertEqual(
            self._sensor({"features": [], "cap": None}).state, "No active event"
        )

    def test_name_and_unique_id(self):
        sensor = self._sensor(None)
        self.assertEqual(sensor.name, "ILM Wave Arrival")
        self.assertEqual(sensor.unique_id, "noaa_tsunami_ILM_wave_arrival")

    def test_attributes(self):
        attrs = self._sensor(_tsunami_payload()).extra_state_attributes
        self.assertEqual(attrs["forecast_point"], "Wilmington, NC")
        self.assertEqual(attrs["center"], "NTWC")
        self.assertEqual(attrs["forecast_points_available"], 3)

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiEvacuationStatusSensor(unittest.TestCase):
    """The action label a user or a TTS automation reads."""

    def _sensor(self, data):
        from noaa_it_all.sensors.tsunami import TsunamiEvacuationStatusSensor
        return TsunamiEvacuationStatusSensor(
            _make_coordinator(data), OFFICE, LAT, LON
        )

    def test_warning_says_move_to_high_ground(self):
        data = {"features": _load_fixture("tsunami_alerts.json")["features"]}
        self.assertEqual(self._sensor(data).state, "Move to high ground")

    def test_quiet_says_no_action(self):
        self.assertEqual(self._sensor({"features": []}).state, "No action required")

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_advisory_says_stay_out_of_water(self):
        features = [f for f in _load_fixture("tsunami_alerts.json")["features"]
                    if f["properties"]["event"] == "Tsunami Advisory"]
        self.assertEqual(
            self._sensor({"features": features}).state, "Stay out of the water"
        )

    def test_name_and_unique_id(self):
        sensor = self._sensor(None)
        self.assertEqual(sensor.name, "ILM Evacuation Status")
        self.assertEqual(
            sensor.unique_id, "noaa_tsunami_ILM_evacuation_status"
        )

    def test_icon_when_warning(self):
        data = {"features": _load_fixture("tsunami_alerts.json")["features"]}
        self.assertEqual(self._sensor(data).icon, "mdi:run-fast")

    def test_attributes_carry_instruction(self):
        data = {"features": _load_fixture("tsunami_alerts.json")["features"]}
        attrs = self._sensor(data).extra_state_attributes
        self.assertIn("high ground", attrs["instruction"])
        self.assertEqual(attrs["threat_level"], "Warning")

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiAlertBinarySensor(unittest.TestCase):
    """Only Warnings and Advisories are actionable."""

    def _sensor(self, data):
        from noaa_it_all.binary_sensor import TsunamiAlertBinarySensor
        return TsunamiAlertBinarySensor(_make_coordinator(data))

    def _from_events(self, *events):
        features = [
            {"properties": {"event": e, "status": "Actual", "areaDesc": "X"}}
            for e in events
        ]
        return self._sensor({"features": features})

    def test_warning_is_on(self):
        self.assertTrue(self._from_events("Tsunami Warning").is_on)

    def test_advisory_is_on(self):
        self.assertTrue(self._from_events("Tsunami Advisory").is_on)

    def test_watch_is_off(self):
        """A Watch means a tsunami is merely possible — not an evacuation."""
        self.assertFalse(self._from_events("Tsunami Watch").is_on)

    def test_information_statement_is_off(self):
        self.assertFalse(self._from_events("Tsunami Information Statement").is_on)

    def test_quiet_is_off(self):
        self.assertFalse(self._sensor({"features": []}).is_on)

    def test_no_data_is_off(self):
        self.assertFalse(self._sensor(None).is_on)

    def test_test_message_does_not_trip_the_alert(self):
        """The monthly comms test must never fire an evacuation automation."""
        data = {"features": _load_fixture("tsunami_test_message.json")["features"]}
        sensor = self._sensor(data)
        self.assertFalse(sensor.is_on)
        self.assertIsNotNone(
            sensor.extra_state_attributes["last_test_message"]
        )

    def test_non_tsunami_warning_is_off(self):
        self.assertFalse(self._from_events("Severe Thunderstorm Warning").is_on)

    def test_device_class(self):
        self.assertEqual(self._sensor(None).device_class, "safety")

    def test_icon(self):
        self.assertEqual(self._from_events("Tsunami Warning").icon, "mdi:tsunami")
        self.assertEqual(self._sensor({"features": []}).icon, "mdi:water-off-outline")

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiDataStaleBinarySensor(unittest.TestCase):
    """The safety net: a dead feed must announce itself."""

    def _sensor(self, last_success):
        from noaa_it_all.binary_sensor import TsunamiDataStaleBinarySensor
        coord = _make_coordinator({"features": []})
        coord.last_success = last_success
        return TsunamiDataStaleBinarySensor(coord)

    def test_fresh_data_is_off(self):
        self.assertFalse(self._sensor(datetime.now(timezone.utc)).is_on)

    def test_stale_data_is_on(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        self.assertTrue(self._sensor(old).is_on)

    def test_never_fetched_is_on(self):
        """Never having succeeded is the most stale state there is."""
        self.assertTrue(self._sensor(None).is_on)

    def test_just_inside_threshold_is_off(self):
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.assertFalse(self._sensor(recent).is_on)

    def test_device_class(self):
        self.assertEqual(self._sensor(None).device_class, "problem")

    def test_name_and_unique_id(self):
        sensor = self._sensor(None)
        self.assertEqual(sensor._attr_name, "Data Stale")
        self.assertEqual(sensor._attr_unique_id, "noaa_tsunami_data_stale")

    def test_attributes_report_age(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=30)
        attrs = self._sensor(old).extra_state_attributes
        self.assertGreater(attrs["age_minutes"], 29)
        self.assertEqual(attrs["stale_after_minutes"], 15)

    def test_attributes_when_never_fetched(self):
        attrs = self._sensor(None).extra_state_attributes
        self.assertIsNone(attrs["last_success"])
        self.assertIsNone(attrs["age_minutes"])

    def test_device_info(self):
        self.assertEqual(self._sensor(None).device_info["name"], "NOAA Tsunami")


class TestTsunamiMapImageEntity(unittest.TestCase):
    """The map switches source depending on whether anything is happening."""

    def _entity(self, data):
        from noaa_it_all.image import TsunamiMapImageEntity
        return TsunamiMapImageEntity(MagicMock(), _make_coordinator(data))

    def test_name_and_unique_id(self):
        entity = self._entity(None)
        self.assertEqual(entity.name, "Map")
        self.assertEqual(entity.unique_id, "noaa_tsunami_map")

    def test_has_entity_name(self):
        self.assertTrue(self._entity(None)._attr_has_entity_name)

    def test_device_info(self):
        self.assertEqual(self._entity(None).device_info["name"], "NOAA Tsunami")

    def test_quiet_shows_dart_network(self):
        """No alert means no energy map exists, so only DART candidates remain."""
        entity = self._entity(_tsunami_payload("tsunami_quiet.json"))
        candidates = entity._candidate_sources()
        self.assertTrue(candidates)
        self.assertTrue(all(c[0] == "DART Network" for c in candidates))

    def test_no_data_shows_dart_network(self):
        entity = self._entity(None)
        self.assertEqual(entity._candidate_sources()[0][0], "DART Network")
        self.assertIsNone(entity._active_center())

    def test_active_alert_prefers_energy_map(self):
        entity = self._entity(_tsunami_payload())
        candidates = entity._candidate_sources()
        self.assertEqual(candidates[0][0], "NTWC Energy Forecast")
        self.assertIn("energy", candidates[0][1])
        self.assertGreater(len(candidates), 1, "energy map must have a fallback")

    def test_all_dart_candidates_are_tried(self):
        """Several DART URLs ship unverified; every one must be attempted."""
        from noaa_it_all.const import TSUNAMI_DART_MAP_URLS
        entity = self._entity(None)
        urls = [url for label, url in entity._candidate_sources()
                if label == "DART Network"]
        self.assertEqual(urls, list(TSUNAMI_DART_MAP_URLS))

    def test_candidate_urls_are_unique(self):
        entity = self._entity(_tsunami_payload())
        urls = [url for _, url in entity._candidate_sources()]
        self.assertEqual(len(urls), len(set(urls)))

    def test_dart_always_remains_the_last_candidate(self):
        """However the energy map resolves, there is always a fallback."""
        for payload in (None, _tsunami_payload(), _tsunami_payload("tsunami_quiet.json")):
            entity = self._entity(payload)
            self.assertEqual(entity._candidate_sources()[-1][0], "DART Network")

    def test_active_center_from_products(self):
        entity = self._entity(_tsunami_payload())
        self.assertEqual(entity._active_center(), "NTWC")

    def test_active_center_falls_back_to_sender_name(self):
        """An alert can land before the center's Atom feed has been fetched."""
        data = {
            "features": _load_fixture("tsunami_alerts.json")["features"],
            "products": [],
            "cap": None,
        }
        self.assertEqual(self._entity(data)._active_center(), "NTWC")

    def test_active_center_recognises_ptwc_sender(self):
        """Pacific alerts come from PTWC, spelled out the same way."""
        features = [{
            "properties": {
                "event": "Tsunami Warning",
                "status": "Actual",
                "areaDesc": "Oahu",
                "senderName": "NWS Pacific Tsunami Warning Center",
            }
        }]
        data = {"features": features, "products": [], "cap": None}
        entity = self._entity(data)
        self.assertEqual(entity._active_center(), "PTWC")
        self.assertEqual(
            entity._candidate_sources()[0][0], "PTWC Energy Forecast"
        )

    def test_every_sender_hint_maps_to_a_known_center(self):
        from noaa_it_all.const import (
            TSUNAMI_CENTER_SENDER_HINTS, TSUNAMI_ATOM_URLS,
        )
        self.assertEqual(
            set(TSUNAMI_CENTER_SENDER_HINTS), set(TSUNAMI_ATOM_URLS)
        )

    def test_test_message_does_not_select_an_energy_map(self):
        """A monthly comms test is not an event, so there is no energy map."""
        data = {
            "features": _load_fixture("tsunami_test_message.json")["features"],
            "products": [],
            "cap": None,
        }
        entity = self._entity(data)
        self.assertIsNone(entity._active_center())
        self.assertEqual(entity._candidate_sources()[0][0], "DART Network")

    def test_attributes_report_which_map_is_showing(self):
        entity = self._entity(_tsunami_payload())
        attrs = entity.extra_state_attributes
        self.assertIn("map_type", attrs)
        self.assertIn("source_url", attrs)
        self.assertEqual(attrs["active_center"], "NTWC")

    def test_entity_picture_is_cache_busted(self):
        entity = self._entity(None)
        self.assertIn("?t=", entity.entity_picture)

    def test_every_center_has_an_energy_map_url(self):
        from noaa_it_all.const import TSUNAMI_ATOM_URLS, TSUNAMI_ENERGY_MAP_URLS
        self.assertEqual(set(TSUNAMI_ATOM_URLS), set(TSUNAMI_ENERGY_MAP_URLS))


class TestTsunamiCoastalOfficeGating(unittest.TestCase):
    """Great Lakes offices must not get location-specific tsunami entities."""

    def test_great_lakes_offices_absent(self):
        from noaa_it_all.const import OFFICE_TSUNAMI_CENTERS
        for office in ("APX", "CLE", "DLH", "DTX", "GRB",
                       "GRR", "IWX", "LOT", "MKX", "MQT"):
            self.assertNotIn(office, OFFICE_TSUNAMI_CENTERS)

    def test_coastal_offices_present(self):
        from noaa_it_all.const import OFFICE_TSUNAMI_CENTERS
        for office in ("EKA", "LOX", "MFR", "MTR", "PQR", "SGX",
                       "HFO", "GUM", "SJU", "ILM", "BOX", "MFL"):
            self.assertIn(office, OFFICE_TSUNAMI_CENTERS)

    def test_every_office_maps_to_a_real_center(self):
        from noaa_it_all.const import OFFICE_TSUNAMI_CENTERS, TSUNAMI_ATOM_URLS
        for office, center in OFFICE_TSUNAMI_CENTERS.items():
            self.assertIn(center, TSUNAMI_ATOM_URLS, office)

    def test_every_tsunami_office_has_coordinates(self):
        from noaa_it_all.const import OFFICE_TSUNAMI_CENTERS, OFFICE_COORDINATES
        for office in OFFICE_TSUNAMI_CENTERS:
            self.assertIn(office, OFFICE_COORDINATES, office)


if __name__ == "__main__":
    unittest.main()
