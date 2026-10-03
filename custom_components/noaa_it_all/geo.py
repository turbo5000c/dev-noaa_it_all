"""Distance on the Earth's surface.

Kept free of Home Assistant imports so both the config flow and the
runtime location tracker can use it without pulling in each other.
"""

import math

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
