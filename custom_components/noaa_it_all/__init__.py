# __init__.py
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "image", "binary_sensor", "weather"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the NOAA component from YAML configuration."""
    _LOGGER.info("Setting up NOAA integration from YAML")

    # For backward compatibility with YAML configuration
    if DOMAIN in config:
        # Load platforms for legacy YAML setup without location configuration
        discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)
        discovery.load_platform(hass, 'image', DOMAIN, {}, config)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up NOAA Integration from a config entry."""
    _LOGGER.info("Setting up NOAA integration for %s", entry.data.get("office_code"))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Load all platforms for the configured location
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


# Legacy function for YAML setup
def setup(hass, config):
    """Set up the NOAA component (legacy YAML support)."""
    _LOGGER.info("Setting up NOAA integration (legacy YAML)")

    # Load the platform for sensor
    discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)

    # Load the platform for image
    discovery.load_platform(hass, 'image', DOMAIN, {}, config)

    return True
