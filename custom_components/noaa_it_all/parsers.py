"""Shared parsing and conversion utilities for NOAA Integration.

This module contains pure functions with no Home Assistant dependency,
making them independently unit-testable.
"""

import math
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def celsius_to_fahrenheit(celsius: Optional[float]) -> Optional[float]:
    """Convert Celsius to Fahrenheit."""
    if celsius is None:
        return None
    return round((celsius * 9 / 5) + 32, 1)


def kmh_to_mph(kmh: Optional[float]) -> Optional[float]:
    """Convert km/h to mph."""
    if kmh is None:
        return None
    return round(kmh * 0.621371, 1)


def pascals_to_inhg(pascals: Optional[float]) -> Optional[float]:
    """Convert Pascals to inches of mercury."""
    if pascals is None:
        return None
    return round(pascals * 0.00029530, 2)


def meters_to_miles(meters: Optional[float]) -> Optional[float]:
    """Convert meters to miles."""
    if meters is None:
        return None
    return round(meters * 0.000621371, 1)


def degrees_to_cardinal(degrees: Union[int, float]) -> str:
    """Convert degrees to cardinal direction."""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = round(degrees / 22.5) % 16
    return directions[idx]


# ---------------------------------------------------------------------------
# Space-weather interpretation helpers
# ---------------------------------------------------------------------------

def interpret_dst_value(dst_value: Any) -> str:
    """Return a human-readable interpretation of a Dst index value."""
    if isinstance(dst_value, (int, float)):
        if dst_value > -20:
            return 'No Storm (Quiet conditions)'
        elif dst_value > -50:
            return 'Minor Storm'
        elif dst_value > -100:
            return 'Moderate Storm'
        elif dst_value > -200:
            return 'Strong Storm'
        else:
            return 'Severe Storm'
    return 'Error: Invalid Dst value'


def rate_kp_index(kp_value: Any) -> str:
    """Return 'low', 'moderate', or 'high' rating for a Kp index value."""
    if kp_value == 'unknown' or kp_value is None:
        return 'unknown'

    try:
        value = float(kp_value)
    except (TypeError, ValueError):
        return 'unknown'

    if value < 2:
        return 'low'
    elif 2 <= value < 5:
        return 'moderate'
    return 'high'


# ---------------------------------------------------------------------------
# Aurora helpers
# ---------------------------------------------------------------------------

def calculate_aurora_visibility(
    kp_index: float,
    magnetic_latitude: float,
    thresholds: Dict[str, Dict[str, float]],
) -> bool:
    """Return whether aurora is visible at *magnetic_latitude* given *kp_index*."""
    for _name, data in thresholds.items():
        if magnetic_latitude >= data["min_lat"]:
            return kp_index >= data["kp_threshold"]
    return False


def calculate_aurora_duration(kp_index: float, magnetic_latitude: float) -> float:
    """Estimate aurora duration in hours based on Kp and latitude."""
    if kp_index >= 7:
        duration = 4 + (kp_index - 7) * 2
    elif kp_index >= 5:
        duration = 2 + (kp_index - 5) * 1
    elif kp_index >= 3:
        duration = 1 + (kp_index - 3) * 0.5
    else:
        duration = 0

    if magnetic_latitude >= 50:
        duration *= 1.3
    elif magnetic_latitude >= 40:
        duration *= 1.1

    return round(duration, 1)


def calculate_aurora_probability(kp_index: float, magnetic_latitude: float) -> int:
    """Calculate aurora visibility probability (0-100) based on Kp and latitude."""
    if magnetic_latitude >= 55:
        if kp_index >= 3:
            probability = min(90, 30 + (kp_index - 3) * 15)
        else:
            probability = kp_index * 10
    elif magnetic_latitude >= 50:
        if kp_index >= 4:
            probability = min(80, 20 + (kp_index - 4) * 15)
        else:
            probability = max(0, (kp_index - 2) * 10)
    elif magnetic_latitude >= 40:
        if kp_index >= 5:
            probability = min(70, 15 + (kp_index - 5) * 15)
        else:
            probability = max(0, (kp_index - 4) * 8)
    elif magnetic_latitude >= 30:
        if kp_index >= 7:
            probability = min(50, 10 + (kp_index - 7) * 15)
        else:
            probability = max(0, (kp_index - 6) * 5)
    else:
        if kp_index >= 8:
            probability = min(30, (kp_index - 8) * 10)
        else:
            probability = 0

    return round(probability)


def get_visibility_class(probability: int) -> str:
    """Return visibility class label for a given probability percentage."""
    if probability >= 70:
        return "Excellent"
    elif probability >= 50:
        return "Good"
    elif probability >= 30:
        return "Fair"
    elif probability >= 10:
        return "Poor"
    return "None"


def get_required_kp(
    magnetic_latitude: float,
    thresholds: Dict[str, Dict[str, float]],
) -> int:
    """Return the minimum Kp index required for aurora visibility at a latitude."""
    for _name, data in thresholds.items():
        if magnetic_latitude >= data["min_lat"]:
            return data["kp_threshold"]
    return 9


# ---------------------------------------------------------------------------
# Solar radiation storm helpers
# ---------------------------------------------------------------------------

def extract_storm_scale(message: str, product_id: str) -> str:
    """Extract S1-S5 storm scale from message or product ID."""
    for scale in ['S5', 'S4', 'S3', 'S2', 'S1']:
        if product_id.startswith(scale):
            return scale

    message_upper = message.upper()
    for scale in ['S5', 'S4', 'S3', 'S2', 'S1']:
        if f'SCALE {scale}' in message_upper or f'{scale} (' in message_upper:
            return scale

    lower = message.lower()
    if any(kw in lower for kw in ['extreme', 'severe']):
        return 'S4'
    if any(kw in lower for kw in ['strong', 'major']):
        return 'S3'
    if 'moderate' in lower:
        return 'S2'
    if 'minor' in lower:
        return 'S1'

    return 'Unknown'


def extract_time_from_message(message: str, time_type: str) -> Optional[str]:
    """Extract time information from an alert message."""
    try:
        pattern = rf'{time_type}:\s*(\d{{4}}\s+\w{{3}}\s+\d{{1,2}}\s+\d{{4}}\s+UTC)'
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def calculate_alert_duration(begin_time: Optional[str], end_time: Optional[str]) -> Optional[str]:
    """Calculate duration between begin and end times."""
    if not begin_time or not end_time:
        return None
    try:
        return "TBD"
    except Exception:
        return None


def extract_impacts(message: str) -> List[str]:
    """Extract potential impacts from an alert message."""
    impacts: List[str] = []
    lower = message.lower()

    if 'satellite' in lower:
        impacts.append('Satellite operations')
    if 'radio' in lower or 'communication' in lower:
        impacts.append('Radio communications')
    if 'navigation' in lower or 'gps' in lower:
        impacts.append('Navigation systems')
    if 'radiation' in lower and ('hazard' in lower or 'risk' in lower):
        impacts.append('Radiation exposure risk')
    if 'polar' in lower:
        impacts.append('Polar region effects')

    return impacts


def get_severity_level(scale: str) -> str:
    """Return severity level string for a given storm scale."""
    severity_map = {
        'S5': 'Extreme',
        'S4': 'Severe',
        'S3': 'Strong',
        'S2': 'Moderate',
        'S1': 'Minor',
        'Unknown': 'Unknown',
    }
    return severity_map.get(scale, 'Unknown')


def assess_location_risk(
    magnetic_latitude: float,
    alerts: List[Dict[str, Any]],
) -> str:
    """Assess location-specific risk based on magnetic latitude and active alerts."""
    if not alerts:
        return 'Low'

    base_risk = 'Low'
    if magnetic_latitude >= 60.0:
        base_risk = 'High'
    elif magnetic_latitude >= 45.0:
        base_risk = 'Moderate'

    max_scale = 'S1'
    for alert in alerts:
        scale = alert.get('scale', 'S1')
        if scale in ['S4', 'S5']:
            return 'High'
        elif scale == 'S3':
            max_scale = 'S3'
        elif scale == 'S2' and max_scale not in ['S3', 'S4', 'S5']:
            max_scale = 'S2'

    if max_scale in ['S3', 'S4', 'S5'] and base_risk == 'Low':
        return 'Moderate'
    elif max_scale in ['S4', 'S5']:
        return 'High'

    return base_risk


# ---------------------------------------------------------------------------
# Hurricane classification helpers
# ---------------------------------------------------------------------------

def classify_hurricane_activity(
    active_storms: List[Dict[str, Any]],
    alert_features: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Classify hurricane activity and return (state_string, attributes_dict).

    Pure logic extracted from HurricaneActivitySensor.async_update.
    """
    hurricane_warnings = 0
    hurricane_watches = 0
    tropical_warnings = 0
    tropical_watches = 0

    for feature in alert_features:
        event = feature.get('properties', {}).get('event', '').lower()
        if 'hurricane warning' in event:
            hurricane_warnings += 1
        elif 'hurricane watch' in event:
            hurricane_watches += 1
        elif 'tropical storm warning' in event:
            tropical_warnings += 1
        elif 'tropical storm watch' in event:
            tropical_watches += 1

    hurricanes = 0
    tropical_storms = 0
    other_storms = 0
    storm_details: List[Dict[str, Any]] = []

    for storm in active_storms:
        classification = storm.get('classification', '').upper()
        storm_info = {
            'name': storm.get('name', 'Unknown'),
            'classification': classification,
            'intensity': storm.get('intensity', 'Unknown'),
            'pressure': storm.get('pressure', 'Unknown'),
            'latitude': storm.get('latitude', 'Unknown'),
            'longitude': storm.get('longitude', 'Unknown'),
            'movement_dir': storm.get('movementDir', 'Unknown'),
            'movement_speed': storm.get('movementSpeed', 'Unknown'),
            'last_update': storm.get('lastUpdate', 'Unknown'),
        }
        storm_details.append(storm_info)

        if classification in ['H1', 'H2', 'H3', 'H4', 'H5', 'HU']:
            hurricanes += 1
        elif classification in ['TS', 'TD']:
            tropical_storms += 1
        else:
            other_storms += 1

    total_storms = len(active_storms)

    if hurricane_warnings > 0 or hurricanes > 0:
        if hurricanes > 0:
            state = f'High - {hurricanes} Active Hurricane(s)'
        else:
            state = 'High - Hurricane Warnings Active'
    elif hurricane_watches > 0:
        state = 'Moderate - Hurricane Watches Active'
    elif tropical_warnings > 0 or tropical_storms > 0:
        if tropical_storms > 0:
            state = f'Moderate - {tropical_storms} Active Tropical Storm(s)'
        else:
            state = 'Moderate - Tropical Storm Warnings Active'
    elif tropical_watches > 0:
        state = 'Low - Tropical Storm Watches Active'
    elif other_storms > 0:
        state = f'Low - {other_storms} Other Storm System(s) Active'
    else:
        state = 'Quiet - No Active Storms or Alerts'

    attributes = {
        'total_active_storms': total_storms,
        'hurricanes': hurricanes,
        'tropical_storms': tropical_storms,
        'other_storms': other_storms,
        'hurricane_warnings': hurricane_warnings,
        'hurricane_watches': hurricane_watches,
        'tropical_warnings': tropical_warnings,
        'tropical_watches': tropical_watches,
        'total_alerts': len(alert_features),
        'storm_details': storm_details,
    }

    return state, attributes


# ---------------------------------------------------------------------------
# Surf-zone parsing helpers
# ---------------------------------------------------------------------------

def parse_rip_current_risk(forecast_text: str) -> str:
    """Parse rip current risk level from forecast text (case-insensitive)."""
    text = forecast_text.lower()
    if re.search(r"high\s+rip\s+current\s+risk|dangerous\s+rip\s+currents|"
                 r"rip\s+current\s+risk\s+is\s+high", text):
        return "High"
    if re.search(r"moderate\s+rip\s+current\s+risk|rip\s+current\s+risk\s+is\s+moderate", text):
        return "Moderate"
    if re.search(r"low\s+rip\s+current\s+risk|rip\s+current\s+risk\s+is\s+low", text):
        return "Low"
    return "Low"


def parse_surf_height(forecast_text: str) -> Optional[str]:
    """Parse surf height from forecast text (case-insensitive).

    Returns a string like ``"2-4"`` (range) or ``"3"`` (single), or *None*.
    """
    text = forecast_text.lower()
    height_patterns = [
        r"surf\s+height\.+(\d+)\s+to\s+(\d+)\s+feet",
        r"surf\s+height\s+(\d+)\s+to\s+(\d+)\s+feet",
        r"surf\s+height\.+(\d+)\s+feet",
        r"surf\s+height\s+(\d+)\s+feet",
        r"surf\s+height\s+(\d+)\s+to\s+(\d+)\s+feet",
        r"surf\s+(\d+)\s+to\s+(\d+)\s+feet",
    ]

    for pattern in height_patterns:
        match = re.search(pattern, text)
        if match:
            if len(match.groups()) == 2:
                return f"{int(match.group(1))}-{int(match.group(2))}"
            return match.group(1)
    return None


def parse_water_temperature(forecast_text: str) -> Optional[str]:
    """Parse water temperature from forecast text (case-insensitive).

    Returns a string like ``"85-89"`` (range) or ``"78"`` (single), or *None*.
    """
    text = forecast_text.lower()
    temp_patterns = [
        r"water\s+temperature\.+in\s+the\s+(upper|mid|lower)\s+(\d+)s",
        r"water\s+temperature\s+in\s+the\s+(upper|mid|lower)\s+(\d+)s",
        r"water\s+temperature\.+around\s+(\d+)",
        r"water\s+temperature\s+around\s+(\d+)",
        r"water\s+temperature\.+(\d+)\s*(?:degrees?|°?f?)",
        r"water\s+temp\.+(\d+)\s*(?:degrees?|°?f?)",
    ]

    for pattern in temp_patterns:
        match = re.search(pattern, text)
        if match:
            if "upper" in match.groups():
                base = int(match.groups()[-1])
                return f"{base + 5}-{base + 9}"
            elif "mid" in match.groups():
                base = int(match.groups()[-1])
                return f"{base + 3}-{base + 7}"
            elif "lower" in match.groups():
                base = int(match.groups()[-1])
                return f"{base}-{base + 4}"
            else:
                return match.groups()[-1]
    return None


# ---------------------------------------------------------------------------
# CO-OPS / NDBC API parsing helpers
# ---------------------------------------------------------------------------

def parse_coops_water_temperature(data: Dict[str, Any]) -> Optional[float]:
    """Extract water temperature in °F from a CO-OPS JSON response.

    Expects the structure returned by the CO-OPS ``datagetter`` API with
    ``units=english``.  Returns *None* when the response is missing or
    the value cannot be converted to a float.
    """
    try:
        records = data.get("data")
        if not records:
            return None
        value = records[-1].get("v")
        if value is None or value == "":
            return None
        return round(float(value), 1)
    except (TypeError, ValueError, IndexError, KeyError):
        return None


# Meters-to-feet conversion factor
_M_TO_FT = 3.28084


def parse_ndbc_wave_height(text: str) -> Optional[float]:
    """Extract significant wave height in feet from NDBC real-time text.

    The text is the standard meteorological data file
    (``/data/realtime2/{station}.txt``).  The first non-comment line
    after the two header rows is the most recent observation.

    Returns *None* when no valid reading is found or the value is ``MM``
    (missing).
    """
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        wvht = parts[8]  # WVHT column (significant wave height in metres)
        if wvht == "MM":
            # Missing value for this observation; try the next line.
            continue
        try:
            return round(float(wvht) * _M_TO_FT, 1)
        except (ValueError, TypeError):
            # Invalid numeric value; try the next line.
            continue
    return None


def normalize_numeric(value) -> Optional[float]:
    """Normalize a parsed value to a numeric float.

    Handles direct numbers, numeric strings, and range strings like
    ``"2-4"`` or ``"85-89"`` (averaged).  Returns *None* when the value
    cannot be converted.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if "-" in text:
            parts = text.split("-", 1)
            try:
                low = float(parts[0].strip())
                high = float(parts[1].strip())
                return round((low + high) / 2.0, 1)
            except (ValueError, TypeError):
                return None
        try:
            return float(text)
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# NWS alert parsing helpers
# ---------------------------------------------------------------------------

def parse_nws_alert_features(features: List[Dict[str, Any]]) -> Tuple[
    List[Dict[str, Any]], Dict[str, Any]
]:
    """Parse NWS alert features and return (active_alerts, summary_dict).

    Only includes alerts with status == 'actual'.
    """
    active_alerts: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        'warnings': 0,
        'watches': 0,
        'advisories': 0,
        'statements': 0,
        'by_severity': {'Extreme': 0, 'Severe': 0, 'Moderate': 0, 'Minor': 0, 'Unknown': 0},
        'by_urgency': {'Immediate': 0, 'Expected': 0, 'Future': 0, 'Past': 0, 'Unknown': 0},
        'event_types': {},
    }

    for feature in features:
        props = feature.get('properties', {})
        status = props.get('status', '').lower()

        if status != 'actual':
            continue

        event = props.get('event', 'Unknown')
        severity = props.get('severity', 'Unknown')
        urgency = props.get('urgency', 'Unknown')

        instruction_raw = props.get('instruction')
        instruction = instruction_raw[:200] if instruction_raw else None

        alert_info = {
            'event': event,
            'headline': props.get('headline', 'No headline'),
            'severity': severity,
            'urgency': urgency,
            'certainty': props.get('certainty', 'Unknown'),
            'area': props.get('areaDesc', 'Unknown area'),
            'effective': props.get('effective', 'Unknown'),
            'onset': props.get('onset', 'Unknown'),
            'expires': props.get('expires', 'Unknown'),
            'ends': props.get('ends', 'Unknown'),
            'status': props.get('status', 'Unknown'),
            'message_type': props.get('messageType', 'Unknown'),
            'category': props.get('category', 'Unknown'),
            'sender': props.get('senderName', 'Unknown'),
            'instruction': instruction,
            'description': props.get('description', '')[:300],
        }
        active_alerts.append(alert_info)

        event_lower = event.lower()
        if 'warning' in event_lower:
            summary['warnings'] += 1
        elif 'watch' in event_lower:
            summary['watches'] += 1
        elif 'advisory' in event_lower:
            summary['advisories'] += 1
        elif 'statement' in event_lower:
            summary['statements'] += 1

        norm_severity = severity if severity in summary['by_severity'] else 'Unknown'
        norm_urgency = urgency if urgency in summary['by_urgency'] else 'Unknown'
        summary['by_severity'][norm_severity] += 1
        summary['by_urgency'][norm_urgency] += 1
        summary['event_types'][event] = summary['event_types'].get(event, 0) + 1

    return active_alerts, summary


# ---------------------------------------------------------------------------
# Tsunami parsing helpers
# ---------------------------------------------------------------------------
#
# Two feeds are parsed here. The NWS alerts API supplies the authoritative
# alert *state* as GeoJSON; the NTWC/PTWC Atom and CAP products supply the
# detail a user actually acts on — estimated wave arrival time, the source
# earthquake, and the evacuation instruction.
#
# Everything below is pure: no network, no Home Assistant, and no imports of
# the lookup tables in const.py. Tables arrive as arguments.

#: Largest XML body we will hand to ElementTree, in bytes.
#:
#: ``xml.etree.ElementTree`` is not hardened against entity-expansion attacks
#: and ``defusedxml`` is not a dependency of this integration. These feeds are
#: a few kilobytes even during a basin-wide event, so anything approaching this
#: size is not a feed we should be parsing.
TSUNAMI_XML_MAX_BYTES = 512 * 1024

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_CAP_NS = "{urn:oasis:names:tc:emergency:cap:1.2}"

#: Magnitude, tried in order. The centers do not write it one way: a headline
#: may say "M 7.2" while the body says "preliminary magnitude 7.2". The spelled
#: out form is tried first, because a pattern anchored on a bare "M" would
#: otherwise match the leading letter of "magnitude" and then fail on the
#: letters that follow it — which is exactly what happened on a live feed.
_MAGNITUDE_PATTERNS = (
    re.compile(r"magnitude\s*(?:of\s*)?[:=]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\bM(?:\.?w)?\s*[:=]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
)
#: Sanity bounds. Anything outside this is a false positive, not a quake.
_MAGNITUDE_RANGE = (0.0, 10.0)

#: Depth, e.g. "depth 35 km", "depth of 35 km", "35 km deep".
_DEPTH_PATTERNS = (
    re.compile(r"\bdepth\D{0,12}?(\d+(?:\.\d+)?)\s*(km|mi)\b", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*(km|mi)\s+deep\b", re.IGNORECASE),
)
#: A decimal coordinate pair with hemisphere letters, e.g. "54.2N 161.5W".
_COORD_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*([NS])[\s,]+(\d+(?:\.\d+)?)\s*([EW])", re.IGNORECASE
)


def _tsunami_level_from_event(event: str, levels: Sequence[str]) -> Optional[str]:
    """Return the alert level named inside an NWS event string, if any.

    ``event`` is a value like ``"Tsunami Advisory"``. Only tsunami events are
    considered, so a "Severe Thunderstorm Warning" never resolves to a level.
    """
    if not event:
        return None
    event_lower = event.lower()
    if 'tsunami' not in event_lower:
        return None
    for level in levels:
        if level.lower() in event_lower:
            return level
    return None


def classify_tsunami_threat_level(
    events: Optional[Iterable[str]], levels: Sequence[str]
) -> Optional[str]:
    """Resolve a collection of NWS event names to the single highest level.

    ``levels`` is ordered highest-first (see ``TSUNAMI_THREAT_LEVELS``).

    Returns ``None`` when ``events`` itself is ``None`` — meaning no data has
    been fetched yet — so callers can surface Home Assistant's ``unknown``
    state. Returns the string ``"None"`` only for a fetch that genuinely
    succeeded and found nothing active. The distinction matters: a sensor that
    reports "no threat" because the feed is down is worse than no sensor.
    """
    if events is None:
        return None
    found = [
        level for level in (
            _tsunami_level_from_event(event, levels) for event in events
        ) if level
    ]
    if not found:
        return "None"
    return min(found, key=levels.index)


def is_tsunami_test_message(props: Dict[str, Any]) -> bool:
    """Return True for a test or exercise message rather than a live alert.

    The NWS runs tsunami communications tests monthly. They are the only
    traffic most installations will ever see on this domain, so they are worth
    surfacing as an attribute — but they must never drive a threat level.
    """
    status = (props.get('status') or '').strip().lower()
    return status in ('test', 'exercise', 'draft', 'system')


def parse_tsunami_alert_features(
    features: Optional[List[Dict[str, Any]]], levels: Sequence[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Filter NWS alert features to tsunami events; return (alerts, summary).

    Mirrors ``parse_nws_alert_features``: only ``status == 'actual'`` counts as
    a live alert. Test messages are excluded from the alert list but the most
    recent one is reported in the summary so users can confirm the feed works
    between real events.

    ``features`` of ``None`` (no successful fetch) produces a summary whose
    ``threat_level`` is ``None`` rather than ``"None"``.
    """
    summary: Dict[str, Any] = {
        'threat_level': None,
        'alert_count': 0,
        'by_level': {level: 0 for level in levels},
        'areas': [],
        'issuing_centers': [],
        'highest_severity': None,
        'latest_issued': None,
        'last_test_message': None,
    }
    if features is None:
        return [], summary

    active_alerts: List[Dict[str, Any]] = []
    events: List[str] = []
    severities: List[str] = []

    for feature in features:
        props = feature.get('properties', {})
        event = props.get('event', '')
        if 'tsunami' not in event.lower():
            continue

        if is_tsunami_test_message(props):
            sent = props.get('sent') or props.get('effective')
            existing = summary['last_test_message']
            if existing is None or (sent and sent > existing.get('sent', '')):
                summary['last_test_message'] = {
                    'event': event,
                    'sent': sent,
                    'sender': props.get('senderName', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                }
            continue

        if (props.get('status') or '').lower() != 'actual':
            continue

        instruction_raw = props.get('instruction')
        alert_info = {
            'event': event,
            'level': _tsunami_level_from_event(event, levels),
            'headline': props.get('headline', 'No headline'),
            'severity': props.get('severity', 'Unknown'),
            'urgency': props.get('urgency', 'Unknown'),
            'certainty': props.get('certainty', 'Unknown'),
            'area': props.get('areaDesc', 'Unknown area'),
            'effective': props.get('effective', 'Unknown'),
            'onset': props.get('onset', 'Unknown'),
            'expires': props.get('expires', 'Unknown'),
            'sent': props.get('sent', 'Unknown'),
            'message_type': props.get('messageType', 'Unknown'),
            'sender': props.get('senderName', 'Unknown'),
            'instruction': instruction_raw[:400] if instruction_raw else None,
            'description': (props.get('description') or '')[:400],
        }
        active_alerts.append(alert_info)
        events.append(event)
        severities.append(alert_info['severity'])

        level = alert_info['level']
        if level in summary['by_level']:
            summary['by_level'][level] += 1
        area = alert_info['area']
        if area and area not in summary['areas']:
            summary['areas'].append(area)
        sender = alert_info['sender']
        if sender and sender not in summary['issuing_centers']:
            summary['issuing_centers'].append(sender)
        sent = props.get('sent')
        if sent and (summary['latest_issued'] is None or sent > summary['latest_issued']):
            summary['latest_issued'] = sent

    summary['threat_level'] = classify_tsunami_threat_level(events, levels)
    summary['alert_count'] = len(active_alerts)

    severity_order = ('Extreme', 'Severe', 'Moderate', 'Minor', 'Unknown')
    ranked = [s for s in severities if s in severity_order]
    if ranked:
        summary['highest_severity'] = min(ranked, key=severity_order.index)

    return active_alerts, summary


def _safe_parse_xml(xml_text: Optional[str]) -> Optional[ET.Element]:
    """Parse XML defensively, returning ``None`` on anything suspicious.

    A malformed or oversized feed must degrade this domain to NWS-only rather
    than take down the whole coordinator update.
    """
    if not xml_text:
        return None
    if len(xml_text.encode('utf-8', errors='ignore')) > TSUNAMI_XML_MAX_BYTES:
        return None
    if '<!ENTITY' in xml_text or '<!DOCTYPE' in xml_text:
        return None
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        return None


def _text_of(element: Optional[ET.Element]) -> str:
    """Return an element's stripped text, or an empty string."""
    if element is None or element.text is None:
        return ''
    return element.text.strip()


def _classify_message_type(title: str) -> str:
    """Label a product as an update, a cancellation, a final message, or new."""
    lowered = title.lower()
    if 'cancel' in lowered:
        return 'Cancellation'
    if 'final' in lowered:
        return 'Final'
    if 'supplement' in lowered or 'update' in lowered:
        return 'Update'
    return 'New'


def parse_tsunami_atom_feed(
    xml_text: Optional[str], center: str, levels: Sequence[str]
) -> List[Dict[str, Any]]:
    """Parse an NTWC/PTWC Atom feed into a list of product entries, newest first.

    Each entry carries the product title, when it was issued, a link to the
    full text, the derived alert level and message type, and whatever source
    earthquake parameters could be recovered from the title and summary.

    Returns ``[]`` for a missing, oversized or malformed feed.
    """
    root = _safe_parse_xml(xml_text)
    if root is None:
        return []

    entries: List[Dict[str, Any]] = []
    for entry in root.findall(f'{_ATOM_NS}entry') or root.findall('entry'):
        title = _text_of(entry.find(f'{_ATOM_NS}title')) or _text_of(entry.find('title'))
        summary = _text_of(entry.find(f'{_ATOM_NS}summary')) or _text_of(entry.find('summary'))
        updated = (
            _text_of(entry.find(f'{_ATOM_NS}updated'))
            or _text_of(entry.find(f'{_ATOM_NS}published'))
            or _text_of(entry.find('updated'))
        )
        link_el = entry.find(f'{_ATOM_NS}link')
        if link_el is None:
            link_el = entry.find('link')
        link = link_el.get('href', '') if link_el is not None else ''

        entries.append({
            'center': center,
            'title': title,
            'summary': summary[:400],
            'updated': updated,
            'link': link,
            'level': _tsunami_level_from_event(title, levels),
            'message_type': _classify_message_type(title),
        })

    entries.sort(key=lambda item: item.get('updated') or '', reverse=True)
    return entries


def summarize_tsunami_source(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recover source-earthquake parameters from a product entry.

    NTWC and PTWC write the quake into the product title and summary rather
    than into structured Atom fields, so this reads them back out by pattern:
    ``"M 7.2"``, ``"depth 35 km"``, ``"54.2N 161.5W"``. Every key is ``None``
    when the corresponding pattern is absent.
    """
    result: Dict[str, Any] = {
        'magnitude': None,
        'depth_km': None,
        'epicenter_latitude': None,
        'epicenter_longitude': None,
        'region': None,
        'origin_time': None,
    }
    if not entry:
        return result

    title = entry.get('title') or ''
    summary = entry.get('summary') or ''
    haystack = f"{title} {summary}"

    for pattern in _MAGNITUDE_PATTERNS:
        match = pattern.search(haystack)
        if not match:
            continue
        value = float(match.group(1))
        if _MAGNITUDE_RANGE[0] <= value <= _MAGNITUDE_RANGE[1]:
            result['magnitude'] = value
            break

    for pattern in _DEPTH_PATTERNS:
        match = pattern.search(haystack)
        if not match:
            continue
        depth = float(match.group(1))
        if match.group(2).lower() == 'mi':
            depth = round(depth * 1.60934, 1)
        result['depth_km'] = depth
        break

    coord_match = _COORD_RE.search(haystack)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(3))
        if coord_match.group(2).upper() == 'S':
            lat = -lat
        if coord_match.group(4).upper() == 'W':
            lon = -lon
        result['epicenter_latitude'] = lat
        result['epicenter_longitude'] = lon

    # Product titles commonly read "... - 100 km SSE of Sand Point, Alaska".
    if ' - ' in title:
        result['region'] = title.split(' - ', 1)[1].strip() or None
    result['origin_time'] = entry.get('updated')

    return result


#: Event directory names in the warning centers' archive, e.g.
#: "previous.events/08-29-2018_LoyaltyIslands". The listing page links to
#: these; each directory holds Images/Location.jpg.
_EVENT_SLUG_RE = re.compile(
    r"previous\.events/((\d{2})-(\d{2})-(\d{4})_([A-Za-z0-9._-]+?))/",
    re.IGNORECASE,
)


def _humanize_event_name(raw: str) -> str:
    """Turn an archive directory name into something readable.

    ``LoyaltyIslands`` becomes ``Loyalty Islands``; separators become spaces.
    """
    spaced = re.sub(r"[._-]+", " ", raw)
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", spaced)
    spaced = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", spaced)
    return re.sub(r"\s+", " ", spaced).strip()


def parse_recent_tsunami_events(
    html: Optional[str], image_template: str, page_template: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """Parse the recent-tsunamis listing into event entries, newest first.

    The listing is an HTML page rather than a feed, so this reads the event
    directory names straight out of the links — the same regex-over-HTML
    approach ``ForecastDiscussionCoordinator`` already uses for AFD text.
    Anything that does not look like a dated event directory is ignored, so a
    layout change degrades to an empty list rather than to nonsense.

    ``image_template`` and ``page_template`` are passed in rather than imported
    to keep this module free of ``const``.
    """
    if not html:
        return []

    seen = set()
    events: List[Dict[str, Any]] = []
    for match in _EVENT_SLUG_RE.finditer(html):
        slug, month, day, year, raw_name = match.groups()
        if slug in seen:
            continue
        seen.add(slug)

        try:
            date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            continue
        if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
            continue

        events.append({
            'slug': slug,
            'name': _humanize_event_name(raw_name),
            'date': date,
            'url': page_template.format(slug=slug),
            'image_url': image_template.format(slug=slug),
        })

    events.sort(key=lambda item: item['date'], reverse=True)
    return events[:limit]


def find_source_earthquake(
    entries: Optional[List[Dict[str, Any]]], max_scan: int = 12
) -> Dict[str, Any]:
    """Return the newest product that actually names an earthquake.

    The most recent product is often a routine statement carrying no quake
    parameters at all, so taking ``entries[0]`` and giving up leaves the sensor
    blank while the answer sits one entry further down. This scans back until
    it finds a magnitude, and falls back to the newest entry so callers still
    get its region, title and link even when no magnitude is recoverable.

    On a quiet day this is the most interesting thing the domain has to say:
    the last earthquake the warning centers looked at and decided was harmless.
    """
    if not entries:
        return summarize_tsunami_source(None)

    for entry in entries[:max_scan]:
        source = summarize_tsunami_source(entry)
        if source['magnitude'] is not None:
            return source

    return summarize_tsunami_source(entries[0])


def _cap_parameters(parent: ET.Element) -> Dict[str, str]:
    """Collect CAP ``<parameter>`` and ``<geocode>`` name/value pairs."""
    values: Dict[str, str] = {}
    for tag in ('parameter', 'geocode'):
        for param in list(parent.findall(f'{_CAP_NS}{tag}')) + list(parent.findall(tag)):
            name = (
                _text_of(param.find(f'{_CAP_NS}valueName'))
                or _text_of(param.find('valueName'))
            )
            value = _text_of(param.find(f'{_CAP_NS}value')) or _text_of(param.find('value'))
            if name:
                values[name] = value
    return values


def _first_matching_value(values: Dict[str, str], needle: str) -> Optional[str]:
    """Return the first value whose parameter name contains ``needle``."""
    for name, value in values.items():
        if needle.lower() in name.lower() and value:
            return value
    return None


def _circle_centre(area: ET.Element) -> Optional[Tuple[float, float]]:
    """Return the lat/lon of a CAP ``<circle>``, if the area carries one."""
    circle = area.find(f'{_CAP_NS}circle')
    if circle is None:
        circle = area.find('circle')
    raw = _text_of(circle)
    if not raw:
        return None
    try:
        point = raw.split()[0]
        lat_str, lon_str = point.split(',')
        return float(lat_str), float(lon_str)
    except (ValueError, IndexError):
        return None


def parse_tsunami_cap(xml_text: Optional[str]) -> Dict[str, Any]:
    """Parse a CAP 1.2 tsunami message into a flat dict.

    Wave arrival times are published as CAP parameters, which the warning
    centers attach either to the ``<info>`` block or to each ``<area>``. Both
    placements are read; area-level values win for a given area.

    Returns a dict whose ``areas`` list is empty when the document is missing,
    oversized or malformed.
    """
    result: Dict[str, Any] = {
        'event': None,
        'severity': None,
        'urgency': None,
        'certainty': None,
        'headline': None,
        'instruction': None,
        'effective': None,
        'expires': None,
        'sent': None,
        'status': None,
        'message_type': None,
        'areas': [],
    }
    root = _safe_parse_xml(xml_text)
    if root is None:
        return result

    result['sent'] = _text_of(root.find(f'{_CAP_NS}sent')) or _text_of(root.find('sent')) or None
    result['status'] = (
        _text_of(root.find(f'{_CAP_NS}status')) or _text_of(root.find('status')) or None
    )
    result['message_type'] = (
        _text_of(root.find(f'{_CAP_NS}msgType')) or _text_of(root.find('msgType')) or None
    )

    info = root.find(f'{_CAP_NS}info')
    if info is None:
        info = root.find('info')
    if info is None:
        return result

    def info_text(tag: str) -> Optional[str]:
        return _text_of(info.find(f'{_CAP_NS}{tag}')) or _text_of(info.find(tag)) or None

    result['event'] = info_text('event')
    result['severity'] = info_text('severity')
    result['urgency'] = info_text('urgency')
    result['certainty'] = info_text('certainty')
    result['headline'] = info_text('headline')
    result['instruction'] = info_text('instruction')
    result['effective'] = info_text('effective')
    result['expires'] = info_text('expires')

    info_params = _cap_parameters(info)
    default_arrival = _first_matching_value(info_params, 'arrival')

    areas = list(info.findall(f'{_CAP_NS}area')) + list(info.findall('area'))
    for area in areas:
        area_params = _cap_parameters(area)
        arrival = _first_matching_value(area_params, 'arrival') or default_arrival
        centre = _circle_centre(area)
        result['areas'].append({
            'area_desc': (
                _text_of(area.find(f'{_CAP_NS}areaDesc'))
                or _text_of(area.find('areaDesc'))
            ),
            'arrival_time': arrival,
            'latitude': centre[0] if centre else None,
            'longitude': centre[1] if centre else None,
        })

    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def estimate_wave_arrival(
    cap_areas: Optional[List[Dict[str, Any]]],
    latitude: Optional[float],
    longitude: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Pick the wave-arrival forecast point closest to the given coordinates.

    CAP areas that carry a ``<circle>`` are ranked by great-circle distance.
    When no area has coordinates — or no coordinates were configured — the
    first area that has an arrival time is used instead, so a coastal user
    still gets a usable time rather than nothing.

    Returns ``None`` when no area carries an arrival time at all.
    """
    if not cap_areas:
        return None

    with_time = [area for area in cap_areas if area.get('arrival_time')]
    if not with_time:
        return None

    if latitude is not None and longitude is not None:
        located = [
            area for area in with_time
            if area.get('latitude') is not None and area.get('longitude') is not None
        ]
        if located:
            nearest = min(
                located,
                key=lambda area: haversine_km(
                    latitude, longitude, area['latitude'], area['longitude']
                ),
            )
            return {
                'forecast_point': nearest.get('area_desc'),
                'arrival_time': nearest.get('arrival_time'),
                'distance_km': round(
                    haversine_km(
                        latitude, longitude, nearest['latitude'], nearest['longitude']
                    ), 1
                ),
            }

    fallback = with_time[0]
    return {
        'forecast_point': fallback.get('area_desc'),
        'arrival_time': fallback.get('arrival_time'),
        'distance_km': None,
    }


# ---------------------------------------------------------------------------
# Forecast formatting helpers
# ---------------------------------------------------------------------------

def format_forecast_text(periods: List[Dict[str, Any]], max_periods: int = 14) -> str:
    """Format forecast periods into human-readable text."""
    lines = []
    for period in periods[:max_periods]:
        name = period.get('name', 'Unknown')
        detailed = period.get('detailedForecast', 'No details available')
        lines.append(f"{name}: {detailed}")
    return "\n\n".join(lines)


def format_forecast_periods(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format extended forecast periods for entity attributes."""
    formatted = []
    for period in periods:
        formatted.append({
            'name': period.get('name', 'Unknown'),
            'temperature': period.get('temperature'),
            'temperature_unit': period.get('temperatureUnit', 'F'),
            'wind_speed': period.get('windSpeed', 'Unknown'),
            'wind_direction': period.get('windDirection', 'Unknown'),
            'short_forecast': period.get('shortForecast', 'Unknown'),
            'detailed_forecast': period.get('detailedForecast', 'No details available'),
            'start_time': period.get('startTime', 'Unknown'),
            'is_daytime': period.get('isDaytime', False),
            'icon': period.get('icon', ''),
        })
    return formatted


def format_hourly_periods(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format hourly forecast periods for entity attributes."""
    formatted = []
    for period in periods:
        precip_prob = period.get('probabilityOfPrecipitation')
        precip_value = 0
        if precip_prob and isinstance(precip_prob, dict):
            precip_value = precip_prob.get('value', 0)
        elif isinstance(precip_prob, (int, float)):
            precip_value = precip_prob

        formatted.append({
            'start_time': period.get('startTime', 'Unknown'),
            'temperature': period.get('temperature'),
            'temperature_unit': period.get('temperatureUnit', 'F'),
            'wind_speed': period.get('windSpeed', 'Unknown'),
            'wind_direction': period.get('windDirection', 'Unknown'),
            'short_forecast': period.get('shortForecast', 'Unknown'),
            'precipitation_probability': precip_value,
            'is_daytime': period.get('isDaytime', False),
            'icon': period.get('icon', ''),
        })
    return formatted
