"""Config flow for NOAA Integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_LATITUDE, CONF_LONGITUDE

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


class NOAAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NOAA Integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            office_code = user_input["office_code"]
            latitude = user_input[CONF_LATITUDE]
            longitude = user_input[CONF_LONGITUDE]
            office_name = NWS_OFFICES.get(office_code, "Unknown")

            # Validate latitude and longitude ranges
            if not -90 <= latitude <= 90:
                errors[CONF_LATITUDE] = "invalid_latitude"
            if not -180 <= longitude <= 180:
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                # Format lat/lon for unique ID consistently (must match sensor.py unique_id format)
                lat_str = f"{latitude:.4f}".replace('.', '_').replace('-', 'n')
                lon_str = f"{longitude:.4f}".replace('.', '_').replace('-', 'n')
                await self.async_set_unique_id(f"noaa_{office_code}_{lat_str}_{lon_str}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"NOAA - {office_name}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("office_code"): vol.In(NWS_OFFICES),
                vol.Required(CONF_LATITUDE): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE): vol.Coerce(float),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return NOAAOptionsFlow(config_entry)


class NOAAOptionsFlow(config_entries.OptionsFlow):
    """NOAA config flow options handler."""

    def __init__(self, config_entry):
        """Initialize NOAA options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            # Validate latitude and longitude ranges
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if latitude is not None and not -90 <= latitude <= 90:
                errors[CONF_LATITUDE] = "invalid_latitude"
            if longitude is not None and not -180 <= longitude <= 180:
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    "office_code",
                    default=self.config_entry.data.get("office_code")
                ): vol.In(NWS_OFFICES),
                vol.Required(
                    CONF_LATITUDE,
                    default=self.config_entry.data.get(CONF_LATITUDE, 0.0)
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE,
                    default=self.config_entry.data.get(CONF_LONGITUDE, 0.0)
                ): vol.Coerce(float),
            }),
            errors=errors,
        )
