import aiohttp
import logging
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from datetime import timedelta, datetime

from .const import (
    CONF_OFFICE_CODE, DEFAULT_SCAN_INTERVAL, DOMAIN,
    HURRICANE_DEVICE_ID, HURRICANE_DEVICE_NAME,
    HURRICANE_IMAGES_ADDED_KEY,
    NWS_RADAR_BASE_URL, NWS_RADAR_LOOP_URL,
    OFFICE_RADAR_SITES, REQUEST_TIMEOUT,
    TSUNAMI_DEVICE_ID, TSUNAMI_DEVICE_NAME, TSUNAMI_IMAGES_ADDED_KEY,
    TSUNAMI_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

BASE_IMAGE_URL = ('https://services.swpc.noaa.gov/images/animations/geoelectric/'
                  'InterMagEarthScope/EmapGraphics_1m/latest.png')
AURORA_URL = ('https://services.swpc.noaa.gov/images/animations/ovation/'
              'north/latest.jpg')

# NOAA Hurricane Image Sources
HURRICANE_OUTLOOK_URL = 'https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png'

# NOAA GOES Satellite Image Sources
GOES_AIRMASS_URL = 'https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/AirMass/1250x750.jpg'
GOES_GEOCOLOR_URL = 'https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/1250x750.jpg'


def _hurricane_device_info() -> DeviceInfo:
    """Return the shared device info for all NOAA Hurricane image entities.

    Hurricane / NHC tropical-cyclone data is global and is not tied to any
    configured NWS office, so all hurricane image entities share a single
    dedicated device named ``NOAA Hurricane``.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, HURRICANE_DEVICE_ID)},
        name=HURRICANE_DEVICE_NAME,
        manufacturer="NOAA",
    )


def _tsunami_device_info() -> DeviceInfo:
    """Return the shared device info for the NOAA Tsunami image entity.

    Mirrors ``_hurricane_device_info``. Tsunami data comes from the two
    national warning centers and covers ocean basins, so it is not tied to any
    configured NWS office.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, TSUNAMI_DEVICE_ID)},
        name=TSUNAMI_DEVICE_NAME,
        manufacturer="NOAA",
    )


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Geoelectric Field Image entity (legacy YAML support)."""
    _LOGGER.error(
        "Legacy YAML configuration for NOAA images is no longer supported. "
        "Please remove the YAML configuration and re-add the integration "
        "via the Home Assistant UI config flow."
    )
    return


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA image entities from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]

    # Global image entities (grouped under office device)
    geoelectric_image_entity = GeoelectricFieldImageEntity(hass, office_code)
    aurora_image_entity = AuroraForecastImageEntity(hass, office_code)

    entities = [
        geoelectric_image_entity,
        aurora_image_entity,
    ]

    # Hurricane image entities are global (NHC) and must only be added
    # once across all configured NWS offices, so they don't appear under
    # every office-specific device. Track the owning config entry's
    # entry_id so that if the owner is unloaded while other entries
    # remain we can release ownership and trigger a remaining entry to
    # re-create the entities.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(HURRICANE_IMAGES_ADDED_KEY):
        entities.extend([
            HurricaneOutlookImageEntity(hass),
            GOESAirMassImageEntity(hass),
            GOESGeoColorImageEntity(hass),
        ])
        domain_data[HURRICANE_IMAGES_ADDED_KEY] = config_entry.entry_id

        def _release_hurricane_image_ownership() -> None:
            """Release hurricane-image ownership and re-create on a remaining entry.

            Fires when the owning config entry is unloaded. If other entries
            remain, clear the flag and reload one of them so its
            ``async_setup_entry`` re-adds the global hurricane images;
            otherwise the entities would disappear until Home Assistant
            restarts.
            """
            if domain_data.get(HURRICANE_IMAGES_ADDED_KEY) != config_entry.entry_id:
                return
            domain_data.pop(HURRICANE_IMAGES_ADDED_KEY, None)
            remaining = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != config_entry.entry_id
            ]
            if remaining:
                target_entry_id = remaining[0].entry_id

                async def _reload_for_hurricane_images() -> None:
                    try:
                        await hass.config_entries.async_reload(target_entry_id)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed to reload entry %s to re-create global "
                            "hurricane images", target_entry_id,
                        )

                hass.async_create_task(_reload_for_hurricane_images())

        config_entry.async_on_unload(_release_hurricane_image_ownership)

    # The tsunami map is global (NTWC/PTWC) and belongs to the single NOAA
    # Tsunami device, so it is added once across all configured offices with
    # the same ownership-transfer handling as the hurricane images.
    tsunami_coord = hass.data[DOMAIN].get(config_entry.entry_id, {}).get(
        "tsunami_coordinator"
    )
    if tsunami_coord and not domain_data.get(TSUNAMI_IMAGES_ADDED_KEY):
        entities.append(TsunamiMapImageEntity(hass, tsunami_coord))
        domain_data[TSUNAMI_IMAGES_ADDED_KEY] = config_entry.entry_id

        def _release_tsunami_image_ownership() -> None:
            """Release tsunami-image ownership and re-create on a remaining entry."""
            if domain_data.get(TSUNAMI_IMAGES_ADDED_KEY) != config_entry.entry_id:
                return
            domain_data.pop(TSUNAMI_IMAGES_ADDED_KEY, None)
            remaining = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != config_entry.entry_id
            ]
            if remaining:
                target_entry_id = remaining[0].entry_id

                async def _reload_for_tsunami_images() -> None:
                    try:
                        await hass.config_entries.async_reload(target_entry_id)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed to reload entry %s to re-create the global "
                            "tsunami map", target_entry_id,
                        )

                hass.async_create_task(_reload_for_tsunami_images())

        config_entry.async_on_unload(_release_tsunami_image_ownership)

    # Location-specific radar image entities
    radar_site = OFFICE_RADAR_SITES.get(office_code)

    if radar_site:
        # Add radar image entities for this location
        base_reflectivity_image = RadarBaseReflectivityImageEntity(hass, office_code, radar_site)
        radar_loop_image = RadarLoopImageEntity(hass, office_code, radar_site)
        entities.extend([base_reflectivity_image, radar_loop_image])
        _LOGGER.info("Added radar image entities for office %s using radar site %s", office_code, radar_site)
    else:
        _LOGGER.warning("No radar site mapping found for office %s", office_code)

    async_add_entities(entities, True)


class GeoelectricFieldImageEntity(ImageEntity):
    """Representation of the Geoelectric Field Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Geoelectric Field Image'

    @property
    def entity_picture(self):
        """Return the URL of the latest geoelectric field image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_geoelectric_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since NOAA updates aren't more frequent
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{BASE_IMAGE_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated geoelectric field image URL")
        except Exception as e:
            _LOGGER.error("Error during geoelectric field image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched geoelectric field image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch geoelectric field image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching geoelectric field image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching geoelectric field image: %s", e)
        return b""


class AuroraForecastImageEntity(ImageEntity):
    """Representation of the aurora Field Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Aurora Forecast Image'

    @property
    def entity_picture(self):
        """Return the URL of the latest aurora forecast image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_aurora_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since NOAA updates aren't more frequent
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{AURORA_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated aurora forecast image URL")
        except Exception as e:
            _LOGGER.error("Error during aurora forecast image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched aurora forecast image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch aurora forecast image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching aurora forecast image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching aurora forecast image: %s", e)
        return b""


class HurricaneOutlookImageEntity(ImageEntity):
    """Representation of the Hurricane Outlook Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("Outlook Image") to produce the entity ID
    ``image.noaa_hurricane_outlook_image``.
    """

    _attr_has_entity_name = True

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this entity is global (NHC).
        """
        super().__init__(hass)
        self.hass = hass
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the local entity name."""
        return 'Outlook Image'

    @property
    def entity_picture(self):
        """Return the URL of the latest hurricane outlook image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_outlook_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{HURRICANE_OUTLOOK_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()
            _LOGGER.debug("Updated hurricane outlook image URL")
        except Exception as e:
            _LOGGER.error("Error during hurricane outlook image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched hurricane outlook image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch hurricane outlook image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching hurricane outlook image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching hurricane outlook image: %s", e)
        return b""


class RadarBaseReflectivityImageEntity(ImageEntity):
    """Representation of the Radar Base Reflectivity Image for a specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the office weather device name (e.g.
    "NOAA ILM Weather") with the local entity name ("Radar Base
    Reflectivity") to produce the entity ID
    ``image.noaa_ilm_weather_radar_base_reflectivity``.
    """

    _attr_has_entity_name = True

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._radar_site = radar_site
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the local entity name."""
        return 'Radar Base Reflectivity'

    @property
    def entity_picture(self):
        """Return the URL of the latest radar base reflectivity image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code.lower()}_weather_radar_base_reflectivity'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 10-minute intervals for cache busting since radar updates every 5-10 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        base_url = NWS_RADAR_BASE_URL.format(radar=self._radar_site)
        return f"{base_url}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated radar base reflectivity image URL for %s", self._office_code)
        except Exception as e:
            _LOGGER.error("Error during radar base reflectivity image update for %s: %s", self._office_code, e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s for radar %s",
                                        content_type, self._radar_site)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched radar base reflectivity image for %s (%d bytes)",
                                  self._office_code, len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch radar base reflectivity image for %s: HTTP %d",
                                    self._office_code, response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching radar base reflectivity image for %s: %s", self._office_code, e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching radar base reflectivity image for %s: %s",
                          self._office_code, e)
        return b""


class RadarLoopImageEntity(ImageEntity):
    """Representation of the Radar Loop Image (animated) for a specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the office weather device name (e.g.
    "NOAA ILM Weather") with the local entity name ("Radar Loop") to
    produce the entity ID ``image.noaa_ilm_weather_radar_loop``.
    """

    _attr_has_entity_name = True

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar loop image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._radar_site = radar_site
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the local entity name."""
        return 'Radar Loop'

    @property
    def entity_picture(self):
        """Return the URL of the latest radar loop image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code.lower()}_weather_radar_loop'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 10-minute intervals for cache busting since radar updates every 5-10 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        base_url = NWS_RADAR_LOOP_URL.format(radar=self._radar_site)
        return f"{base_url}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated radar loop image URL for %s", self._office_code)
        except Exception as e:
            _LOGGER.error("Error during radar loop image update for %s: %s",
                          self._office_code, e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s for radar %s",
                                        content_type, self._radar_site)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched radar loop image for %s (%d bytes)",
                                  self._office_code, len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch radar loop image for %s: HTTP %d",
                                    self._office_code, response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching radar loop image for %s: %s", self._office_code, e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching radar loop image for %s: %s",
                          self._office_code, e)
        return b""


class GOESAirMassImageEntity(ImageEntity):
    """Representation of the GOES-19 Air Mass RGB Satellite Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("GOES Air Mass") to produce the entity ID
    ``image.noaa_hurricane_goes_air_mass``.
    """

    _attr_has_entity_name = True

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this satellite image is global and is grouped under the
        NOAA Hurricane device alongside the other tropical-cyclone
        tracking images.
        """
        super().__init__(hass)
        self.hass = hass
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the local entity name."""
        return 'GOES Air Mass'

    @property
    def entity_picture(self):
        """Return the URL of the latest GOES Air Mass image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_goes_air_mass'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since GOES updates every ~5 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{GOES_AIRMASS_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated GOES Air Mass image URL")
        except Exception as e:
            _LOGGER.error("Error during GOES Air Mass image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched GOES Air Mass image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch GOES Air Mass image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching GOES Air Mass image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching GOES Air Mass image: %s", e)
        return b""


class GOESGeoColorImageEntity(ImageEntity):
    """Representation of the GOES-19 GeoColor Satellite Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("GOES Geocolor") to produce the entity ID
    ``image.noaa_hurricane_goes_geocolor``.
    """

    _attr_has_entity_name = True

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this satellite image is global and is grouped under the
        NOAA Hurricane device alongside the other tropical-cyclone
        tracking images.
        """
        super().__init__(hass)
        self.hass = hass
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the local entity name."""
        return 'GOES Geocolor'

    @property
    def entity_picture(self):
        """Return the URL of the latest GOES GeoColor image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_goes_geocolor'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since GOES updates every ~5 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{GOES_GEOCOLOR_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated GOES GeoColor image URL")
        except Exception as e:
            _LOGGER.error("Error during GOES GeoColor image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched GOES GeoColor image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch GOES GeoColor image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching GOES GeoColor image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching GOES GeoColor image: %s", e)
        return b""


class TsunamiMapImageEntity(ImageEntity):
    """Location map for the most recent tsunami in the warning centers' archive.

    The centers keep every past tsunami under ``previous.events/`` with a
    location map at ``Images/Location.jpg``, so the newest entry in that
    archive is always a real, renderable picture of a real tsunami. That makes
    this the one map source here that is confirmed rather than inferred.

    Earlier revisions tried the RIFT energy-propagation forecast during a live
    event and the DART buoy network map otherwise. Both were guesses at URL
    shapes, both 404'd on a live install, and both were removed — a dead tile
    is worse than a slightly less topical one, and unverifiable fallbacks only
    made the failure harder to diagnose.

    Uses ``_attr_has_entity_name = True`` so Home Assistant combines the device
    name ("NOAA Tsunami") with the local name to produce
    ``image.noaa_tsunami_map``.
    """

    _attr_has_entity_name = True

    def __init__(self, hass, coordinator=None):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._coordinator = coordinator
        self._source_url = None
        self._image_url = None

    @property
    def name(self):
        """Return the local entity name."""
        return 'Map'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_tsunami_map'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _tsunami_device_info()

    def _latest_event(self):
        """Return the newest archived tsunami event, or ``None``."""
        if self._coordinator is None or not self._coordinator.data:
            return None
        events = self._coordinator.data.get('events') or []
        return events[0] if events else None

    @property
    def entity_picture(self):
        """Return the URL of the current map, or ``None`` when unknown."""
        return self._image_url

    @property
    def extra_state_attributes(self):
        """Report which event the map is showing."""
        event = self._latest_event() or {}
        return {
            'event': event.get('name'),
            'event_date': event.get('date'),
            'event_url': event.get('url'),
            'source_url': self._source_url,
        }

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching.

        Archived event images never change once published, so the bucket only
        needs to be coarse enough to pick up a newly added event.
        """
        if not self._source_url:
            return None
        now = datetime.utcnow()
        bucket = (now.minute // TSUNAMI_SCAN_INTERVAL) * TSUNAMI_SCAN_INTERVAL
        timestamp = now.strftime('%Y%m%d%H') + f"{bucket:02d}"
        return f"{self._source_url}?t={timestamp}"

    async def async_update(self):
        """Point at the newest archived event's location map."""
        try:
            event = self._latest_event()
            source = event.get('image_url') if event else None
            if source != self._source_url:
                self._source_url = source
                _LOGGER.debug(
                    "Tsunami map now showing %s",
                    event.get('name') if event else 'nothing',
                )
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Error during tsunami map update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest event's location map."""
        event = self._latest_event()
        source = event.get('image_url') if event else None
        if not source:
            _LOGGER.debug("No archived tsunami event available for the map yet")
            return b""

        self._source_url = source
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        try:
            async with session.get(source, timeout=timeout) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Tsunami map unavailable for %s: HTTP %d (%s)",
                        event.get('name'), response.status, source,
                    )
                    return b""
                content_type = response.headers.get('content-type', '').lower()
                if 'image' not in content_type:
                    _LOGGER.warning(
                        "Tsunami map for %s returned %s, not an image",
                        event.get('name'), content_type,
                    )
                    return b""
                content = await response.read()
                _LOGGER.debug(
                    "Fetched tsunami map for %s (%d bytes)",
                    event.get('name'), len(content),
                )
                return content
        except aiohttp.ClientError as e:
            _LOGGER.warning("Error fetching tsunami map: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching tsunami map: %s", e)
        return b""
