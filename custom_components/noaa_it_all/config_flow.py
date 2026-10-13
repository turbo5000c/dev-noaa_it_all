"""Config flow for NOAA Integration."""
import logging
import math

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_OFFICE_CODE,
    CONF_RADAR_LOOP_HOURS,
    CONF_RADAR_SITE,
    CONF_SURF_OFFICE_CODE,
    DEFAULT_RADAR_LOOP_HOURS,
    NWS_OFFICE_URL,
    NWS_POINTS_URL,
    OFFICE_BUOY_STATIONS,
    OFFICE_COORDINATES,
    OFFICE_RADAR_SITES,
    OFFICE_TIDE_STATIONS,
    RADAR_LOOP_MAX_HOURS,
    USER_AGENT,
)
from .entry_config import resolve_entry_config

_LOGGER = logging.getLogger(__name__)

# NWS Forecast Offices that issue Surf Zone Forecasts (SRF)
NWS_OFFICES = {
    "AKQ": "Norfolk, VA",
    "APX": "Gaylord, MI",
    "BOX": "Boston, MA",
    "BRO": "Brownsville, TX",
    "CAR": "Caribou, ME",
    "CHS": "Charleston, SC",
    "CLE": "Cleveland, OH",
    "CRP": "Corpus Christi, TX",
    "DLH": "Duluth, MN",
    "DTX": "Detroit, MI",
    "EKA": "Eureka, CA",
    "GRB": "Green Bay, WI",
    "GRR": "Grand Rapids, MI",
    "GUM": "Guam",
    "GYX": "Portland, ME",
    "HFO": "Honolulu, HI",
    "ILM": "Wilmington, NC",
    "IWX": "Northern Indiana",
    "JAX": "Jacksonville, FL",
    "LOT": "Chicago, IL",
    "LOX": "Los Angeles, CA",
    "MFL": "Miami, FL",
    "MFR": "Medford, OR",
    "MHX": "Newport, NC",
    "MKX": "Milwaukee, WI",
    "MLB": "Melbourne, FL",
    "MOB": "Mobile, AL",
    "MQT": "Marquette, MI",
    "MTR": "San Francisco, CA",
    "OKX": "New York, NY",
    "PHI": "Philadelphia, PA",
    "PQR": "Portland, OR",
    "SGX": "San Diego, CA",
    "SJU": "San Juan, PR",
    "TAE": "Tallahassee, FL",
    "TBW": "Tampa, FL",
}

# Maximum distance (miles) used to filter "nearby" offices.
NEARBY_OFFICE_RADIUS_MILES = 50.0

# Choice on the surf step for an inland user who wants no surf entities.
NO_SURF_OFFICE = "none"

# Seconds to wait on NWS while the setup form is open.
_LOOKUP_TIMEOUT = 10

# Earth radius in statute miles.
_EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(lat1, lon1, lat2, lon2):
    """Return the great-circle distance in miles between two points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def find_nearby_offices(latitude, longitude, max_miles=NEARBY_OFFICE_RADIUS_MILES):
    """Return [(office_code, distance_miles), ...] sorted by distance ascending.

    When ``max_miles`` is None, all known offices are returned.
    """
    distances = []
    for code, (olat, olon) in OFFICE_COORDINATES.items():
        distances.append((code, haversine_miles(latitude, longitude, olat, olon)))
    distances.sort(key=lambda item: item[1])
    if max_miles is None:
        return distances
    return [item for item in distances if item[1] <= max_miles]


def _format_office_label(code, distance_miles):
    """Build a human-readable label for an office in the dropdown."""
    name = NWS_OFFICES.get(code, "Unknown")
    return f"{code} - {name} ({distance_miles:.1f} mi)"


def _format_surf_label(code, distance_miles):
    """Build a surf dropdown label naming the surf data the office provides.

    Every surf office gives rip current risk. Water temperature needs a tide
    station and surf height a buoy, which not every office has.
    """
    provides = ["rip current"]
    if code in OFFICE_TIDE_STATIONS:
        provides.append("water temp")
    if code in OFFICE_BUOY_STATIONS:
        provides.append("surf height")
    if len(provides) == 1:
        provides[0] = "rip current only"
    return f"{_format_office_label(code, distance_miles)} - {', '.join(provides)}"


async def async_lookup_point(hass, latitude, longitude):
    """Ask NWS which forecast office and radar cover a point.

    Returns {"office", "name", "radar"}, or None when NWS cannot say: it is
    unreachable, or the point is outside its coverage. The office is whichever
    of the 120-odd offices covers the point, not only the coastal ones in
    NWS_OFFICES.
    """
    if hass is None:
        return None
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(total=_LOOKUP_TIMEOUT)
    headers = {"User-Agent": USER_AGENT}
    url = NWS_POINTS_URL.format(lat=round(latitude, 4), lon=round(longitude, 4))
    try:
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            properties = (await resp.json()).get("properties") or {}
    except Exception as err:  # noqa: BLE001 - the flow falls back to the table
        _LOGGER.debug("Could not look up the forecast office from NWS: %s", err)
        return None

    office = properties.get("cwa") or properties.get("gridId")
    if not isinstance(office, str) or len(office) != 3 or not office.isalpha():
        return None
    office = office.upper()
    radar = properties.get("radarStation")

    name = NWS_OFFICES.get(office)
    if name is None:
        try:
            async with session.get(
                NWS_OFFICE_URL.format(office=office), headers=headers, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                name = (await resp.json()).get("name")
        except Exception as err:  # noqa: BLE001 - the code alone still works
            _LOGGER.debug("Could not look up the name of office %s: %s", office, err)
        if not isinstance(name, str) or not name:
            name = office

    return {
        "office": office,
        "name": name,
        "radar": radar if isinstance(radar, str) and radar else None,
    }


def _build_office_options(latitude, longitude, point=None):
    """Return (options_dict, default_code, no_candidates_within_radius).

    ``point`` is the async_lookup_point result. The office NWS names for the
    location is listed first and pre-selected, then the coastal offices nearby.
    """
    candidates = find_nearby_offices(latitude, longitude)
    no_within_radius = not candidates and point is None
    if not candidates:
        # Fall back to the 5 nearest overall so the user still has a choice.
        candidates = find_nearby_offices(latitude, longitude, max_miles=None)[:5]
    options = {}
    if point is not None:
        options[point["office"]] = (
            f"{point['office']} - {point['name']} (forecast office for this location)"
        )
    for code, dist in candidates:
        options.setdefault(code, _format_office_label(code, dist))
    default_code = next(iter(options), None)
    return options, default_code, no_within_radius


def _build_surf_options(latitude, longitude):
    """Return (options_dict, default_code) for choosing a surf office.

    Every office that issues a Surf Zone Forecast, nearest first, so an inland
    user can take the nearest coast or the one they visit.
    """
    candidates = find_nearby_offices(latitude, longitude, max_miles=None)
    options = {code: _format_surf_label(code, dist) for code, dist in candidates}
    options[NO_SURF_OFFICE] = "No surf data"
    return options, candidates[0][0] if candidates else NO_SURF_OFFICE


def _office_name(code, point):
    """Return the display name of an office the user chose."""
    if code in NWS_OFFICES:
        return NWS_OFFICES[code]
    if point is not None and point["office"] == code:
        return point["name"]
    return code


def _radar_site_for(code, point):
    """Return the radar site for an office, from the table or from NWS."""
    if code in OFFICE_RADAR_SITES:
        return OFFICE_RADAR_SITES[code]
    if point is not None and point["office"] == code:
        return point["radar"]
    return None


def _ha_home_coords(hass):
    """Return (lat, lon) from Home Assistant Home zone, or (None, None)."""
    if hass is None:
        return None, None
    config = getattr(hass, "config", None)
    if config is None:
        return None, None
    lat = getattr(config, "latitude", None)
    lon = getattr(config, "longitude", None)
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None, None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, None
    # Treat a literal 0,0 as "not configured" (Null Island default).
    if lat == 0 and lon == 0:
        return None, None
    return float(lat), float(lon)


class NOAAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NOAA Integration."""

    VERSION = 1

    def __init__(self):
        """Initialize transient state for the multi-step flow."""
        self._latitude = None
        self._longitude = None
        self._point = None
        self._office_code = None

    async def async_step_user(self, user_input=None):
        """Step 1: collect latitude and longitude (pre-filled from HA Home)."""
        errors = {}
        ha_lat, ha_lon = _ha_home_coords(getattr(self, "hass", None))

        if user_input is not None:
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if latitude is None or not -90 <= latitude <= 90:
                errors[CONF_LATITUDE] = "invalid_latitude"
            if longitude is None or not -180 <= longitude <= 180:
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                self._latitude = float(latitude)
                self._longitude = float(longitude)
                self._point = await async_lookup_point(
                    getattr(self, "hass", None), self._latitude, self._longitude
                )
                return await self.async_step_office()

        default_lat = ha_lat if ha_lat is not None else 0.0
        default_lon = ha_lon if ha_lon is not None else 0.0

        if ha_lat is not None:
            ha_location_text = f"{ha_lat:.4f}, {ha_lon:.4f}"
        else:
            ha_location_text = "not configured"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
            }),
            errors=errors,
            description_placeholders={"ha_location": ha_location_text},
        )

    async def async_step_office(self, user_input=None):
        """Step 2: choose the NWS forecast office for the location."""
        options, default_code, no_within_radius = _build_office_options(
            self._latitude, self._longitude, self._point
        )

        if user_input is not None:
            office_code = user_input.get(CONF_OFFICE_CODE)
            if office_code not in options:
                # Defensive — should be enforced by the dropdown schema.
                return self.async_show_form(
                    step_id="office",
                    data_schema=vol.Schema({
                        vol.Required(
                            CONF_OFFICE_CODE, default=default_code
                        ): vol.In(options),
                    }),
                    errors={CONF_OFFICE_CODE: "invalid_office"},
                    description_placeholders=self._office_placeholders(no_within_radius),
                )

            self._office_code = office_code
            if office_code in NWS_OFFICES:
                # A coastal office issues its own Surf Zone Forecast.
                return await self._async_create(office_code)
            return await self.async_step_surf()

        return self.async_show_form(
            step_id="office",
            data_schema=vol.Schema({
                vol.Required(CONF_OFFICE_CODE, default=default_code): vol.In(options),
            }),
            description_placeholders=self._office_placeholders(no_within_radius),
        )

    async def async_step_surf(self, user_input=None):
        """Step 3, for an inland office only: choose an office for surf data."""
        options, default_code = _build_surf_options(self._latitude, self._longitude)

        if user_input is not None:
            surf_code = user_input.get(CONF_SURF_OFFICE_CODE)
            if surf_code in options:
                return await self._async_create(
                    None if surf_code == NO_SURF_OFFICE else surf_code
                )
            errors = {CONF_SURF_OFFICE_CODE: "invalid_office"}
        else:
            errors = {}

        return self.async_show_form(
            step_id="surf",
            data_schema=vol.Schema({
                vol.Required(CONF_SURF_OFFICE_CODE, default=default_code): vol.In(options),
            }),
            errors=errors,
            description_placeholders={"office": self._office_code},
        )

    async def _async_create(self, surf_code):
        """Create the entry for the chosen office and surf office."""
        office_code = self._office_code
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        await self.async_set_unique_id(f"noaa_{office_code}_{lat_str}_{lon_str}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"NOAA - {_office_name(office_code, self._point)}",
            data={
                CONF_OFFICE_CODE: office_code,
                CONF_SURF_OFFICE_CODE: surf_code,
                CONF_RADAR_SITE: _radar_site_for(office_code, self._point),
                CONF_LATITUDE: self._latitude,
                CONF_LONGITUDE: self._longitude,
            },
        )

    def _office_placeholders(self, no_within_radius):
        """Build description placeholders for the office step."""
        return {
            "latitude": f"{self._latitude:.4f}",
            "longitude": f"{self._longitude:.4f}",
            "warning": (
                "No NWS forecast office was found within "
                f"{int(NEARBY_OFFICE_RADIUS_MILES)} miles of the selected location. "
                "Showing the nearest offices instead."
            ) if no_within_radius else "",
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return NOAAOptionsFlow()


class NOAAOptionsFlow(config_entries.OptionsFlow):
    """NOAA config flow options handler."""

    def __init__(self):
        """Initialize transient state for the multi-step flow.

        ``self.config_entry`` is deliberately not assigned here: it is a
        read-only property supplied by the OptionsFlow base class, and
        assigning to it raises AttributeError on current Home Assistant.
        """
        self._latitude = None
        self._longitude = None
        self._point = None
        self._office_code = None
        self._surf_office_code = None

    async def async_step_init(self, user_input=None):
        """Step 1 of the options flow: latitude / longitude."""
        errors = {}
        ha_lat, ha_lon = _ha_home_coords(getattr(self, "hass", None))

        if user_input is not None:
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if latitude is None or not -90 <= latitude <= 90:
                errors[CONF_LATITUDE] = "invalid_latitude"
            if longitude is None or not -180 <= longitude <= 180:
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                self._latitude = float(latitude)
                self._longitude = float(longitude)
                self._point = await async_lookup_point(
                    getattr(self, "hass", None), self._latitude, self._longitude
                )
                return await self.async_step_office()

        # Prefer the previously configured value, then HA Home, then 0.0.
        # Options win over setup data so the form shows what is in effect now,
        # not whatever was entered at initial setup.
        existing = resolve_entry_config(self.config_entry)
        existing_lat = existing.get(CONF_LATITUDE)
        existing_lon = existing.get(CONF_LONGITUDE)
        default_lat = (
            existing_lat if existing_lat is not None
            else ha_lat if ha_lat is not None
            else 0.0
        )
        default_lon = (
            existing_lon if existing_lon is not None
            else ha_lon if ha_lon is not None
            else 0.0
        )

        if ha_lat is not None:
            ha_location_text = f"{ha_lat:.4f}, {ha_lon:.4f}"
        else:
            ha_location_text = "not configured"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
            }),
            errors=errors,
            description_placeholders={"ha_location": ha_location_text},
        )

    async def async_step_office(self, user_input=None):
        """Step 2 of the options flow: choose the NWS forecast office."""
        options, default_code, no_within_radius = _build_office_options(
            self._latitude, self._longitude, self._point
        )
        # Prefer the existing office_code if it's still a valid candidate.
        existing_code = resolve_entry_config(self.config_entry).get(CONF_OFFICE_CODE)
        if (
            self._point is None
            and existing_code
            and existing_code not in OFFICE_COORDINATES
        ):
            # An inland office only ever comes from NWS. With NWS unreachable
            # it would drop off the list, and saving would move the entry.
            options = {existing_code: f"{existing_code} (current office)", **options}
            no_within_radius = False
        if existing_code in options:
            default_code = existing_code

        if user_input is not None:
            office_code = user_input.get(CONF_OFFICE_CODE)
            if office_code not in options:
                return self.async_show_form(
                    step_id="office",
                    data_schema=vol.Schema({
                        vol.Required(
                            CONF_OFFICE_CODE, default=default_code
                        ): vol.In(options),
                    }),
                    errors={CONF_OFFICE_CODE: "invalid_office"},
                    description_placeholders=self._office_placeholders(no_within_radius),
                )
            self._office_code = office_code
            if office_code in NWS_OFFICES:
                self._surf_office_code = office_code
                return await self.async_step_radar()
            return await self.async_step_surf()

        return self.async_show_form(
            step_id="office",
            data_schema=vol.Schema({
                vol.Required(CONF_OFFICE_CODE, default=default_code): vol.In(options),
            }),
            description_placeholders=self._office_placeholders(no_within_radius),
        )

    async def async_step_surf(self, user_input=None):
        """Options step for an inland office only: choose an office for surf data."""
        options, default_code = _build_surf_options(self._latitude, self._longitude)
        existing = resolve_entry_config(self.config_entry)
        if CONF_SURF_OFFICE_CODE in existing:
            saved = existing[CONF_SURF_OFFICE_CODE] or NO_SURF_OFFICE
            if saved in options:
                default_code = saved

        if user_input is not None:
            surf_code = user_input.get(CONF_SURF_OFFICE_CODE)
            if surf_code in options:
                self._surf_office_code = (
                    None if surf_code == NO_SURF_OFFICE else surf_code
                )
                return await self.async_step_radar()
            errors = {CONF_SURF_OFFICE_CODE: "invalid_office"}
        else:
            errors = {}

        return self.async_show_form(
            step_id="surf",
            data_schema=vol.Schema({
                vol.Required(CONF_SURF_OFFICE_CODE, default=default_code): vol.In(options),
            }),
            errors=errors,
            description_placeholders={"office": self._office_code},
        )

    async def async_step_radar(self, user_input=None):
        """Last step of the options flow: how much radar history to keep.

        NOAA's own animation covers about fifty minutes and cannot be made
        longer, so anything beyond that is accumulated locally over time.  The
        value is in hours, and 0 means "just serve NOAA's loop".
        """
        errors = {}
        existing = resolve_entry_config(self.config_entry)
        default_hours = existing.get(
            CONF_RADAR_LOOP_HOURS, DEFAULT_RADAR_LOOP_HOURS
        )

        if user_input is not None:
            hours = user_input.get(CONF_RADAR_LOOP_HOURS)
            # Validated here rather than left to the schema alone: the flow
            # tests mock voluptuous wholesale, so a vol.Range would be a
            # MagicMock that accepts anything.
            try:
                hours = int(hours)
            except (TypeError, ValueError):
                hours = None
            if hours is None or not 0 <= hours <= RADAR_LOOP_MAX_HOURS:
                errors[CONF_RADAR_LOOP_HOURS] = "invalid_radar_hours"
            else:
                # Every key is listed explicitly.  Options replace the stored
                # mapping wholesale rather than merging into it, so a key left
                # out here is a key silently dropped on the next options edit.
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_OFFICE_CODE: self._office_code,
                        CONF_SURF_OFFICE_CODE: self._surf_office_code,
                        CONF_RADAR_SITE: self._radar_site(),
                        CONF_LATITUDE: self._latitude,
                        CONF_LONGITUDE: self._longitude,
                        CONF_RADAR_LOOP_HOURS: hours,
                    },
                )
            default_hours = user_input.get(CONF_RADAR_LOOP_HOURS, default_hours)

        return self.async_show_form(
            step_id="radar",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_RADAR_LOOP_HOURS, default=default_hours
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=RADAR_LOOP_MAX_HOURS)),
            }),
            errors=errors,
            description_placeholders={"max_hours": str(RADAR_LOOP_MAX_HOURS)},
        )

    def _radar_site(self):
        """Return the radar site to save, keeping the saved one if NWS is down."""
        site = _radar_site_for(self._office_code, self._point)
        if site is None:
            existing = resolve_entry_config(self.config_entry)
            if existing.get(CONF_OFFICE_CODE) == self._office_code:
                site = existing.get(CONF_RADAR_SITE)
        return site

    def _office_placeholders(self, no_within_radius):
        """Build description placeholders for the office step."""
        return {
            "latitude": f"{self._latitude:.4f}",
            "longitude": f"{self._longitude:.4f}",
            "warning": (
                "No NWS forecast office was found within "
                f"{int(NEARBY_OFFICE_RADIUS_MILES)} miles of the selected location. "
                "Showing the nearest offices instead."
            ) if no_within_radius else "",
        }
