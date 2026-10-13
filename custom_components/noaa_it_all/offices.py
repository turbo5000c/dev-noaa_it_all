"""Which office, radar site and magnetic latitude an entry's data comes from.

An entry names its local NWS forecast office. The tables in const.py cover
only the coastal offices that issue Surf Zone Forecasts, so anything they do
not cover for an inland office is stored on the entry at setup or estimated.
"""

import math

from .const import (
    CONF_OFFICE_CODE,
    CONF_RADAR_SITE,
    CONF_SURF_OFFICE_CODE,
    GEOMAGNETIC_POLE_LAT,
    GEOMAGNETIC_POLE_LON,
    OFFICE_COORDINATES,
    OFFICE_MAGNETIC_LATITUDES,
    OFFICE_RADAR_SITES,
)


def surf_office(conf):
    """Return the office whose Surf Zone Forecast to use, or None for none.

    An entry made before the surf office was its own setting has no such key.
    Its office was always one of the coastal offices, so it keeps using it.
    """
    if CONF_SURF_OFFICE_CODE in conf:
        return conf[CONF_SURF_OFFICE_CODE]
    office = conf.get(CONF_OFFICE_CODE)
    return office if office in OFFICE_COORDINATES else None


def radar_site(conf):
    """Return the NEXRAD site for the entry's radar images, or None."""
    return conf.get(CONF_RADAR_SITE) or OFFICE_RADAR_SITES.get(
        conf.get(CONF_OFFICE_CODE)
    )


def geomagnetic_latitude(latitude, longitude):
    """Return the dipole geomagnetic latitude in degrees of a point."""
    phi = math.radians(latitude)
    pole_phi = math.radians(GEOMAGNETIC_POLE_LAT)
    dlon = math.radians(longitude - GEOMAGNETIC_POLE_LON)
    return math.degrees(math.asin(
        math.sin(phi) * math.sin(pole_phi)
        + math.cos(phi) * math.cos(pole_phi) * math.cos(dlon)
    ))


def magnetic_latitude(office_code, latitude=None, longitude=None, default=0.0):
    """Return the magnetic latitude the aurora sensors judge visibility by.

    The table covers the coastal offices. Any other office is estimated from
    the configured location, so an inland office does not read as the equator.
    """
    if office_code in OFFICE_MAGNETIC_LATITUDES:
        return OFFICE_MAGNETIC_LATITUDES[office_code]
    if latitude is None or longitude is None:
        return default
    return round(geomagnetic_latitude(latitude, longitude), 1)
