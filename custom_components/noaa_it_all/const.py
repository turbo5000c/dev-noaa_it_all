"""Constants for NOAA Integration."""

DOMAIN = "noaa_it_all"

# Configuration keys
CONF_OFFICE_CODE = "office_code"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"

# Default values
DEFAULT_SCAN_INTERVAL = 5  # minutes
REQUEST_TIMEOUT = 30  # seconds
USER_AGENT = "HomeAssistant/NOAA-Integration"

# API endpoints
NWS_SRF_URL = "https://forecast.weather.gov/product.php?site={office}&issuedby={office}&product=SRF&format=TXT"
NWS_API_BASE = "https://api.weather.gov"
NWS_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
NWS_OBSERVATIONS_URL = "https://api.weather.gov/stations/{station}/observations/latest"
NWS_RADAR_BASE_URL = "https://radar.weather.gov/ridge/standard/{radar}_0.gif"
NWS_RADAR_LOOP_URL = "https://radar.weather.gov/ridge/standard/{radar}_loop.gif"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?point={lat},{lon}"
NWS_ALERTS_ZONE_URL = "https://api.weather.gov/alerts/active?zone={zone}"
NWS_GRIDPOINT_URL = "https://api.weather.gov/gridpoints/{office}/{gridX},{gridY}"
NWS_AFD_URL = "https://forecast.weather.gov/product.php?site={office}&issuedby={office}&product=AFD&format=TXT"

# NWS office to observation station mapping
# Each office uses the primary weather observation station in their area
OFFICE_STATION_IDS = {
    "AKQ": "KORF",  # Norfolk International Airport
    "APX": "KGLS",  # Gaylord
    "BOX": "KBOS",  # Boston Logan Airport
    "BRO": "KBRO",  # Brownsville South Padre Island
    "CAR": "KCAR",  # Caribou Municipal Airport
    "CHS": "KCHS",  # Charleston International Airport
    "CLE": "KCLE",  # Cleveland Hopkins International Airport
    "CRP": "KCRP",  # Corpus Christi International Airport
    "DLH": "KDLH",  # Duluth International Airport
    "DTX": "KDTW",  # Detroit Metro Airport
    "EKA": "KACV",  # Arcata-Eureka Airport
    "GRB": "KGRB",  # Green Bay Austin Straubel Airport
    "GRR": "KGRR",  # Gerald R. Ford Airport
    "GUM": "PGUM",  # Guam International Airport
    "GYX": "KPWM",  # Portland International Jetport
    "HFO": "PHNL",  # Honolulu International Airport
    "ILM": "KILM",  # Wilmington International Airport
    "IWX": "KSBN",  # South Bend International Airport
    "JAX": "KJAX",  # Jacksonville International Airport
    "LOT": "KORD",  # Chicago O'Hare International Airport
    "LOX": "KLAX",  # Los Angeles International Airport
    "MFL": "KMIA",  # Miami International Airport
    "MFR": "KMFR",  # Rogue Valley International-Medford Airport
    "MHX": "KMRH",  # Michael J. Smith Field
    "MKX": "KMKE",  # Milwaukee Mitchell International Airport
    "MLB": "KMLB",  # Melbourne Orlando International Airport
    "MOB": "KMOB",  # Mobile Regional Airport
    "MQT": "KSAW",  # Sawyer International Airport
    "MTR": "KSFO",  # San Francisco International Airport
    "OKX": "KJFK",  # John F. Kennedy International Airport
    "PHI": "KPHL",  # Philadelphia International Airport
    "PQR": "KPDX",  # Portland International Airport
    "SGX": "KSAN",  # San Diego International Airport
    "SJU": "TJSJ",  # Luis Muñoz Marín International Airport
    "TAE": "KTLH",  # Tallahassee International Airport
    "TBW": "KTPA",  # Tampa International Airport
}

# NWS office to radar site mapping
# Each office maps to the primary NEXRAD radar station covering their area
OFFICE_RADAR_SITES = {
    "AKQ": "KAKQ",  # Norfolk/Richmond - Wakefield, VA
    "APX": "KAPX",  # Gaylord, MI
    "BOX": "KBOX",  # Boston, MA - Taunton
    "BRO": "KBRO",  # Brownsville, TX
    "CAR": "KCBW",  # Caribou, ME - Houlton
    "CHS": "KCLX",  # Charleston, SC - Grays
    "CLE": "KCLE",  # Cleveland, OH
    "CRP": "KCRP",  # Corpus Christi, TX
    "DLH": "KDLH",  # Duluth, MN
    "DTX": "KDTX",  # Detroit, MI - White Lake
    "EKA": "KBHX",  # Eureka, CA - Blue Canyon
    "GRB": "KGRB",  # Green Bay, WI
    "GRR": "KGRR",  # Grand Rapids, MI
    "GUM": "PGUA",  # Guam - Barrigada
    "GYX": "KGYX",  # Portland, ME - Gray
    "HFO": "PHKI",  # Honolulu, HI - South Shore
    "ILM": "KLTX",  # Wilmington, NC - Shallotte
    "IWX": "KIWX",  # Northern Indiana - North Webster
    "JAX": "KJAX",  # Jacksonville, FL
    "LOT": "KLOT",  # Chicago, IL - Romeoville
    "LOX": "KSOX",  # Los Angeles, CA - Santa Ana Mountains
    "MFL": "KAMX",  # Miami, FL
    "MFR": "KMAX",  # Medford, OR
    "MHX": "KMHX",  # Newport/Morehead City, NC
    "MKX": "KMKX",  # Milwaukee, WI - Dousman
    "MLB": "KMLB",  # Melbourne, FL
    "MOB": "KMOB",  # Mobile, AL
    "MQT": "KMQT",  # Marquette, MI
    "MTR": "KMUX",  # San Francisco, CA - Mt. Umunhum
    "OKX": "KOKX",  # New York, NY - Upton
    "PHI": "KDIX",  # Philadelphia, PA - Mt. Holly, NJ
    "PQR": "KRTX",  # Portland, OR
    "SGX": "KNKX",  # San Diego, CA
    "SJU": "TJUA",  # San Juan, PR - Cayey
    "TAE": "KTLH",  # Tallahassee, FL
    "TBW": "KTBW",  # Tampa, FL - Ruskin
}

# Aurora visibility mapping - approximate magnetic latitudes for NWS offices
OFFICE_MAGNETIC_LATITUDES = {
    "AKQ": 40.2,  # Norfolk, VA
    "APX": 51.8,  # Gaylord, MI
    "BOX": 42.1,  # Boston, MA
    "BRO": 25.9,  # Brownsville, TX
    "CAR": 56.7,  # Caribou, ME
    "CHS": 32.8,  # Charleston, SC
    "CLE": 46.4,  # Cleveland, OH
    "CRP": 27.8,  # Corpus Christi, TX
    "DLH": 56.8,  # Duluth, MN
    "DTX": 47.6,  # Detroit, MI
    "EKA": 50.5,  # Eureka, CA
    "GRB": 49.5,  # Green Bay, WI
    "GRR": 47.9,  # Grand Rapids, MI
    "GUM": 3.3,   # Guam
    "GYX": 43.7,  # Portland, ME
    "HFO": 11.4,  # Honolulu, HI
    "ILM": 34.2,  # Wilmington, NC
    "IWX": 46.8,  # Northern Indiana
    "JAX": 30.3,  # Jacksonville, FL
    "LOT": 47.8,  # Chicago, IL
    "LOX": 34.1,  # Los Angeles, CA
    "MFL": 25.8,  # Miami, FL
    "MFR": 49.3,  # Medford, OR
    "MHX": 34.8,  # Newport, NC
    "MKX": 48.2,  # Milwaukee, WI
    "MLB": 28.1,  # Melbourne, FL
    "MOB": 30.7,  # Mobile, AL
    "MQT": 55.2,  # Marquette, MI
    "MTR": 46.2,  # San Francisco, CA
    "OKX": 40.8,  # New York, NY
    "PHI": 39.9,  # Philadelphia, PA
    "PQR": 55.4,  # Portland, OR
    "SGX": 32.7,  # San Diego, CA
    "SJU": 18.4,  # San Juan, PR
    "TAE": 30.4,  # Tallahassee, FL
    "TBW": 27.8,  # Tampa, FL
}

# Aurora visibility thresholds based on Kp index and magnetic latitude
AURORA_KP_THRESHOLDS = {
    # Kp levels needed for aurora visibility at different magnetic latitudes
    "high_latitude": {"min_lat": 50.0, "kp_threshold": 3},    # Northern US/Canada border
    "mid_latitude": {"min_lat": 40.0, "kp_threshold": 5},     # Northern US states
    "low_latitude": {"min_lat": 30.0, "kp_threshold": 7},     # Southern US states
    "very_low_latitude": {"min_lat": 0.0, "kp_threshold": 9},  # Extreme events only
}

# Solar Radiation Storm scale and impact information
SOLAR_RADIATION_STORM_SCALES = {
    "S1": {
        "name": "Minor",
        "description": "Biological: None. Satellite operations: None. "
                       "Other systems: Minor impact on HF radio in polar regions."
    },
    "S2": {
        "name": "Moderate",
        "description": "Biological: Passengers and crew in high-altitude flights at high latitudes may be "
                       "exposed to radiation risk. Satellite operations: Infrequent single-event upsets possible. "
                       "Other systems: Small effects on HF propagation through polar regions and navigation at "
                       "polar cap locations possibly affected."
    },
    "S3": {
        "name": "Strong",
        "description": "Biological: Radiation hazard avoidance recommended for astronauts on EVA; passengers "
                       "and crew in high-altitude flights at high latitudes may be exposed to radiation risk. "
                       "Satellite operations: Single-event upsets, noise in imaging systems, and slight reduction "
                       "of efficiency in solar panel are likely. Other systems: Degraded HF radio propagation "
                       "through polar regions and navigation position errors likely."
    },
    "S4": {
        "name": "Severe",
        "description": "Biological: Unavoidable radiation hazard to astronauts on EVA; passengers and crew "
                       "in high-altitude flights at high latitudes may be exposed to radiation risk. "
                       "Satellite operations: Memory device problems and noise on imaging systems; star-tracker "
                       "problems may cause orientation problems, and solar panel efficiency can be degraded. "
                       "Other systems: Blackout of HF radio communications through polar regions and increased "
                       "navigation errors over several days are likely."
    },
    "S5": {
        "name": "Extreme",
        "description": "Biological: Unavoidable high radiation hazard to astronauts on EVA "
                       "(extra-vehicular activity); passengers and crew in high-altitude flights at high "
                       "latitudes may be exposed to radiation risk. Satellite operations: Memory device problems "
                       "and noise on imaging systems; star-tracker problems may cause orientation problems, and "
                       "solar panel efficiency can be degraded. Other systems: Complete blackout of HF "
                       "(high frequency) communications possible through polar regions, and navigation may be "
                       "degraded for days."
    }
}

# Solar Radiation Storm alert keywords for filtering NOAA alerts
SOLAR_RADIATION_KEYWORDS = [
    "solar radiation",
    "radiation storm",
    "proton event",
    "proton flux",
    "solar proton",
    "Type IV",
    "coronal mass ejection",
    "solar particle"
]
