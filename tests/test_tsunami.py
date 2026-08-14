"""Tests for the pure tsunami parsing functions.

These import ``parsers`` bare — pytest.ini puts ``custom_components/noaa_it_all``
on the path — because the module has no Home Assistant dependency. A guard test
at the bottom enforces that it stays that way.
"""

import json
import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIXTURES = os.path.join(_REPO, "tests", "fixtures")
_PARSERS_PATH = os.path.join(
    _REPO, "custom_components", "noaa_it_all", "parsers.py"
)

if os.path.join(_REPO, "custom_components", "noaa_it_all") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "custom_components", "noaa_it_all"))

from parsers import (  # noqa: E402
    classify_tsunami_threat_level,
    estimate_wave_arrival,
    find_source_earthquake,
    haversine_km,
    is_tsunami_test_message,
    parse_tsunami_alert_features,
    parse_tsunami_atom_feed,
    parse_tsunami_cap,
    summarize_tsunami_source,
)

LEVELS = ("Warning", "Advisory", "Watch", "Information")


def _load_json(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return json.load(f)


def _load_text(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return f.read()


class TestClassifyTsunamiThreatLevel(unittest.TestCase):
    """The four-level escalation ladder."""

    def test_warning_beats_advisory(self):
        self.assertEqual(
            classify_tsunami_threat_level(
                ["Tsunami Advisory", "Tsunami Warning"], LEVELS
            ),
            "Warning",
        )

    def test_advisory_beats_watch(self):
        self.assertEqual(
            classify_tsunami_threat_level(["Tsunami Watch", "Tsunami Advisory"], LEVELS),
            "Advisory",
        )

    def test_watch_beats_information(self):
        self.assertEqual(
            classify_tsunami_threat_level(
                ["Tsunami Information Statement", "Tsunami Watch"], LEVELS
            ),
            "Watch",
        )

    def test_empty_list_is_the_string_none(self):
        """A successful fetch that found nothing reads as 'None'."""
        self.assertEqual(classify_tsunami_threat_level([], LEVELS), "None")

    def test_no_data_is_python_none(self):
        """No fetch at all must stay None so Home Assistant shows 'unknown'.

        This is the single most important behaviour in the domain: collapsing
        this into "None" would let a dead feed read as an all-clear.
        """
        self.assertIsNone(classify_tsunami_threat_level(None, LEVELS))

    def test_non_tsunami_events_are_ignored(self):
        self.assertEqual(
            classify_tsunami_threat_level(
                ["Severe Thunderstorm Warning", "Tornado Warning"], LEVELS
            ),
            "None",
        )


class TestIsTsunamiTestMessage(unittest.TestCase):
    """Test/exercise traffic must be distinguishable from live alerts."""

    def test_test_status(self):
        self.assertTrue(is_tsunami_test_message({"status": "Test"}))

    def test_exercise_status(self):
        self.assertTrue(is_tsunami_test_message({"status": "Exercise"}))

    def test_actual_status(self):
        self.assertFalse(is_tsunami_test_message({"status": "Actual"}))

    def test_missing_status(self):
        self.assertFalse(is_tsunami_test_message({}))


class TestParseTsunamiAlertFeatures(unittest.TestCase):
    """Filtering NWS GeoJSON down to tsunami events."""

    def setUp(self):
        self.features = _load_json("tsunami_alerts.json")["features"]

    def test_only_tsunami_events_are_kept(self):
        alerts, _ = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertEqual(len(alerts), 2)
        for alert in alerts:
            self.assertIn("tsunami", alert["event"].lower())

    def test_threat_level_is_highest(self):
        _, summary = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertEqual(summary["threat_level"], "Warning")

    def test_counts_by_level(self):
        _, summary = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertEqual(summary["by_level"]["Warning"], 1)
        self.assertEqual(summary["by_level"]["Advisory"], 1)
        self.assertEqual(summary["by_level"]["Watch"], 0)

    def test_areas_collected_without_duplicates(self):
        _, summary = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertEqual(len(summary["areas"]), len(set(summary["areas"])))
        self.assertIn("San Mateo County Coast", summary["areas"])

    def test_highest_severity(self):
        _, summary = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertEqual(summary["highest_severity"], "Extreme")

    def test_alert_count(self):
        _, summary = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertEqual(summary["alert_count"], 2)

    def test_instruction_is_preserved(self):
        alerts, _ = parse_tsunami_alert_features(self.features, LEVELS)
        self.assertIn("high ground", alerts[0]["instruction"])

    def test_quiet_feed(self):
        features = _load_json("tsunami_quiet.json")["features"]
        alerts, summary = parse_tsunami_alert_features(features, LEVELS)
        self.assertEqual(alerts, [])
        self.assertEqual(summary["threat_level"], "None")
        self.assertEqual(summary["alert_count"], 0)

    def test_no_data_yields_unknown_not_none_string(self):
        alerts, summary = parse_tsunami_alert_features(None, LEVELS)
        self.assertEqual(alerts, [])
        self.assertIsNone(summary["threat_level"])

    def test_test_message_does_not_raise_threat_level(self):
        """A monthly comms test must never look like a real alert."""
        features = _load_json("tsunami_test_message.json")["features"]
        alerts, summary = parse_tsunami_alert_features(features, LEVELS)
        self.assertEqual(alerts, [])
        self.assertEqual(summary["threat_level"], "None")

    def test_test_message_is_still_reported_as_an_attribute(self):
        """...but it is surfaced, since it is the only proof the feed works."""
        features = _load_json("tsunami_test_message.json")["features"]
        _, summary = parse_tsunami_alert_features(features, LEVELS)
        self.assertIsNotNone(summary["last_test_message"])
        self.assertEqual(
            summary["last_test_message"]["headline"],
            "Monthly tsunami communications test",
        )

    def test_non_actual_status_is_excluded(self):
        features = [{
            "properties": {
                "event": "Tsunami Warning",
                "status": "Draft",
                "areaDesc": "Nowhere",
            }
        }]
        alerts, summary = parse_tsunami_alert_features(features, LEVELS)
        self.assertEqual(alerts, [])
        self.assertEqual(summary["threat_level"], "None")


class TestParseTsunamiAtomFeed(unittest.TestCase):
    """NTWC/PTWC Atom product feeds."""

    def setUp(self):
        self.xml = _load_text("tsunami_atom_ntwc.xml")

    def test_entry_count(self):
        entries = parse_tsunami_atom_feed(self.xml, "NTWC", LEVELS)
        self.assertEqual(len(entries), 2)

    def test_newest_first(self):
        entries = parse_tsunami_atom_feed(self.xml, "NTWC", LEVELS)
        self.assertEqual(entries[0]["updated"], "2026-08-14T11:02:00Z")

    def test_level_derived_from_title(self):
        entries = parse_tsunami_atom_feed(self.xml, "NTWC", LEVELS)
        self.assertEqual(entries[0]["level"], "Warning")
        self.assertEqual(entries[1]["level"], "Information")

    def test_message_type_detects_final(self):
        entries = parse_tsunami_atom_feed(self.xml, "NTWC", LEVELS)
        self.assertEqual(entries[0]["message_type"], "New")
        self.assertEqual(entries[1]["message_type"], "Final")

    def test_center_is_recorded(self):
        entries = parse_tsunami_atom_feed(self.xml, "NTWC", LEVELS)
        self.assertEqual(entries[0]["center"], "NTWC")

    def test_link_extracted(self):
        entries = parse_tsunami_atom_feed(self.xml, "NTWC", LEVELS)
        self.assertTrue(entries[0]["link"].startswith("https://www.tsunami.gov/"))

    def test_cancellation_detected(self):
        xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            '<title>Tsunami Warning Cancellation</title>'
            '<updated>2026-08-14T12:00:00Z</updated>'
            '</entry></feed>'
        )
        entries = parse_tsunami_atom_feed(xml, "PTWC", LEVELS)
        self.assertEqual(entries[0]["message_type"], "Cancellation")

    def test_malformed_xml_returns_empty(self):
        self.assertEqual(parse_tsunami_atom_feed("<feed><entry>", "NTWC", LEVELS), [])

    def test_none_returns_empty(self):
        self.assertEqual(parse_tsunami_atom_feed(None, "NTWC", LEVELS), [])

    def test_doctype_is_refused(self):
        """Entity-expansion vectors are rejected before ElementTree sees them."""
        hostile = '<!DOCTYPE f [<!ENTITY a "boom">]><feed/>'
        self.assertEqual(parse_tsunami_atom_feed(hostile, "NTWC", LEVELS), [])

    def test_oversized_body_is_refused(self):
        oversized = "<feed/>" + ("x" * 600_000)
        self.assertEqual(parse_tsunami_atom_feed(oversized, "NTWC", LEVELS), [])


class TestSummarizeTsunamiSource(unittest.TestCase):
    """Recovering quake parameters from product prose."""

    def setUp(self):
        xml = _load_text("tsunami_atom_ntwc.xml")
        self.entry = parse_tsunami_atom_feed(xml, "NTWC", LEVELS)[0]

    def test_magnitude(self):
        self.assertEqual(summarize_tsunami_source(self.entry)["magnitude"], 7.8)

    def test_depth(self):
        self.assertEqual(summarize_tsunami_source(self.entry)["depth_km"], 32.0)

    def test_epicenter(self):
        source = summarize_tsunami_source(self.entry)
        self.assertEqual(source["epicenter_latitude"], 54.7)
        self.assertEqual(source["epicenter_longitude"], -161.3)

    def test_region(self):
        self.assertEqual(
            summarize_tsunami_source(self.entry)["region"],
            "95 km SSE of Sand Point, Alaska",
        )

    def test_southern_and_eastern_hemispheres(self):
        entry = {"title": "Tsunami Watch M 8.1", "summary": "near 33.5S 178.2E"}
        source = summarize_tsunami_source(entry)
        self.assertEqual(source["epicenter_latitude"], -33.5)
        self.assertEqual(source["epicenter_longitude"], 178.2)

    def test_depth_in_miles_is_converted(self):
        entry = {"title": "M 6.0", "summary": "depth 20 mi"}
        self.assertEqual(summarize_tsunami_source(entry)["depth_km"], 32.2)

    def test_empty_entry_yields_all_none(self):
        source = summarize_tsunami_source(None)
        self.assertTrue(all(v is None for v in source.values()))


class TestMagnitudeWordings(unittest.TestCase):
    """The centers do not write magnitude one way.

    A live install showed Source Earthquake as Unknown while the feed was
    working: the original pattern was anchored on a bare "M", which matched the
    leading letter of "magnitude" and then failed on the letters after it.
    """

    def _magnitude(self, text):
        return summarize_tsunami_source({"title": text, "summary": ""})["magnitude"]

    def test_spelled_out_magnitude(self):
        self.assertEqual(self._magnitude("Preliminary magnitude 6.2"), 6.2)

    def test_magnitude_of(self):
        self.assertEqual(self._magnitude("magnitude of 7.1"), 7.1)

    def test_abbreviated_with_space(self):
        self.assertEqual(self._magnitude("Tsunami Warning M 7.8 near Alaska"), 7.8)

    def test_abbreviated_without_space(self):
        self.assertEqual(self._magnitude("Statement M6.4"), 6.4)

    def test_equals_form(self):
        self.assertEqual(self._magnitude("Event M=5.9"), 5.9)

    def test_moment_magnitude_form(self):
        self.assertEqual(self._magnitude("Mw 8.1 offshore"), 8.1)

    def test_spelled_out_wins_over_stray_m(self):
        self.assertEqual(
            self._magnitude("Statement Number 3 - preliminary magnitude 6.6"), 6.6
        )

    def test_implausible_values_rejected(self):
        """A stray match must not produce a magnitude 47 earthquake."""
        self.assertIsNone(self._magnitude("Message 47 issued at 1200 UTC"))

    def test_no_magnitude_present(self):
        self.assertIsNone(self._magnitude("Tsunami Information Statement"))

    def test_depth_deep_wording(self):
        source = summarize_tsunami_source(
            {"title": "M 6.0", "summary": "The quake was 35 km deep."}
        )
        self.assertEqual(source["depth_km"], 35.0)


class TestFindSourceEarthquake(unittest.TestCase):
    """One uninformative newest product must not blank the sensor."""

    def test_scans_past_a_product_without_a_magnitude(self):
        entries = [
            {"title": "Tsunami Information Statement", "summary": "", "updated": "3"},
            {"title": "Statement", "summary": "magnitude 6.5", "updated": "2"},
        ]
        self.assertEqual(find_source_earthquake(entries)["magnitude"], 6.5)

    def test_prefers_the_newest_product_that_has_one(self):
        entries = [
            {"title": "No quake here", "summary": "", "updated": "3"},
            {"title": "M 7.0", "summary": "", "updated": "2"},
            {"title": "M 5.0", "summary": "", "updated": "1"},
        ]
        self.assertEqual(find_source_earthquake(entries)["magnitude"], 7.0)

    def test_falls_back_to_newest_when_none_have_a_magnitude(self):
        entries = [
            {"title": "Statement - Kodiak Island", "summary": "", "updated": "2"},
            {"title": "Statement - Elsewhere", "summary": "", "updated": "1"},
        ]
        source = find_source_earthquake(entries)
        self.assertIsNone(source["magnitude"])
        self.assertEqual(source["region"], "Kodiak Island")

    def test_empty_and_none(self):
        self.assertIsNone(find_source_earthquake([])["magnitude"])
        self.assertIsNone(find_source_earthquake(None)["magnitude"])

    def test_scan_is_bounded(self):
        entries = [{"title": "nothing", "summary": ""} for _ in range(50)]
        entries.append({"title": "M 9.0", "summary": ""})
        self.assertIsNone(find_source_earthquake(entries, max_scan=5)["magnitude"])


class TestParseTsunamiCap(unittest.TestCase):
    """CAP 1.2 documents."""

    def setUp(self):
        self.cap = parse_tsunami_cap(_load_text("tsunami_cap.xml"))

    def test_event(self):
        self.assertEqual(self.cap["event"], "Tsunami Warning")

    def test_severity_and_urgency(self):
        self.assertEqual(self.cap["severity"], "Extreme")
        self.assertEqual(self.cap["urgency"], "Immediate")

    def test_instruction(self):
        self.assertIn("high ground", self.cap["instruction"])

    def test_areas_parsed(self):
        self.assertEqual(len(self.cap["areas"]), 3)

    def test_area_carries_arrival_and_coordinates(self):
        area = self.cap["areas"][0]
        self.assertEqual(area["area_desc"], "Crescent City, CA")
        self.assertEqual(area["arrival_time"], "2026-08-14T15:40:00-00:00")
        self.assertAlmostEqual(area["latitude"], 41.7558)
        self.assertAlmostEqual(area["longitude"], -124.2026)

    def test_malformed_returns_empty_areas(self):
        self.assertEqual(parse_tsunami_cap("<alert>")["areas"], [])

    def test_none_returns_empty_areas(self):
        self.assertEqual(parse_tsunami_cap(None)["areas"], [])


class TestEstimateWaveArrival(unittest.TestCase):
    """Choosing the forecast point nearest the user."""

    def setUp(self):
        self.areas = parse_tsunami_cap(_load_text("tsunami_cap.xml"))["areas"]

    def test_picks_crescent_city_for_eureka(self):
        arrival = estimate_wave_arrival(self.areas, 40.9789, -124.1085)
        self.assertEqual(arrival["forecast_point"], "Crescent City, CA")

    def test_picks_honolulu_for_honolulu(self):
        arrival = estimate_wave_arrival(self.areas, 21.3245, -158.0250)
        self.assertEqual(arrival["forecast_point"], "Honolulu, HI")

    def test_picks_wilmington_for_wilmington(self):
        arrival = estimate_wave_arrival(self.areas, 34.2675, -77.9011)
        self.assertEqual(arrival["forecast_point"], "Wilmington, NC")

    def test_distance_is_reported(self):
        arrival = estimate_wave_arrival(self.areas, 21.3245, -158.0250)
        self.assertLess(arrival["distance_km"], 50)

    def test_falls_back_without_coordinates(self):
        arrival = estimate_wave_arrival(self.areas, None, None)
        self.assertEqual(arrival["forecast_point"], "Crescent City, CA")
        self.assertIsNone(arrival["distance_km"])

    def test_no_areas_returns_none(self):
        self.assertIsNone(estimate_wave_arrival([], 40.0, -124.0))
        self.assertIsNone(estimate_wave_arrival(None, 40.0, -124.0))

    def test_areas_without_arrival_times_return_none(self):
        areas = [{"area_desc": "Somewhere", "arrival_time": None,
                  "latitude": 1.0, "longitude": 2.0}]
        self.assertIsNone(estimate_wave_arrival(areas, 1.0, 2.0))


class TestHaversine(unittest.TestCase):
    """Sanity check on the distance helper."""

    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_km(40.0, -124.0, 40.0, -124.0), 0.0)

    def test_known_distance(self):
        # Los Angeles to New York is roughly 3,940 km.
        distance = haversine_km(34.0522, -118.2437, 40.7128, -74.0060)
        self.assertTrue(3900 < distance < 4000, distance)


class TestParsersStayPure(unittest.TestCase):
    """parsers.py must remain importable without Home Assistant.

    Mirrors the guard tests in test_meteor.py and test_astro.py.
    """

    def test_no_home_assistant_import(self):
        with open(_PARSERS_PATH) as f:
            source = f.read()
        self.assertNotIn("homeassistant", source)
        self.assertNotIn("import aiohttp", source)

    def test_no_const_import(self):
        """Lookup tables are injected as arguments, never imported."""
        with open(_PARSERS_PATH) as f:
            source = f.read()
        self.assertNotIn("from .const", source)
        self.assertNotIn("from const", source)


if __name__ == "__main__":
    unittest.main()
