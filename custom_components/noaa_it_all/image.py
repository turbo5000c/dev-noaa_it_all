"""NOAA image entities.

Every entity here follows the same shape, provided by :class:`NoaaImageEntity`:
the image is fetched from NOAA on a background timer and the last frame that
came back successfully is kept in memory.  ``async_image()`` only ever hands
back that cached copy, so a transient upstream failure -- a DNS timeout, an
unreachable network, a 503 from NOAA -- leaves the previous picture on the
dashboard instead of blanking the tile.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_OFFICE_CODE, DEFAULT_SCAN_INTERVAL, DOMAIN,
    HURRICANE_DEVICE_ID, HURRICANE_DEVICE_NAME,
    HURRICANE_IMAGES_ADDED_KEY,
    IMAGE_FAILURE_ERROR_AFTER, IMAGE_FAILURE_WARN_AFTER,
    IMAGE_FETCH_TIMEOUT, IMAGE_MAX_BYTES,
    NWS_RADAR_BASE_URL, NWS_RADAR_LOOP_URL,
    OFFICE_RADAR_SITES, USER_AGENT,
)
from .entry_config import resolve_entry_config

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

# Failures that mean "the network or NOAA is having a moment" rather than
# "this integration is asking for the wrong thing".  ``asyncio.TimeoutError``
# has to be listed explicitly: a ``ClientTimeout`` expiry raises it, and it is
# *not* an ``aiohttp.ClientError``, so it would otherwise be reported as an
# unexpected error.
_TRANSIENT_FETCH_ERRORS = (
    aiohttp.ClientConnectorError,   # DNS failure, refused, network unreachable
    aiohttp.ClientOSError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ServerTimeoutError,
    asyncio.TimeoutError,
)


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
    office_code = resolve_entry_config(config_entry)[CONF_OFFICE_CODE]

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

    # No ``update_before_add``: the first fetch is scheduled by
    # ``async_added_to_hass`` once the entity actually exists, so a slow or
    # unreachable NOAA can never hold up setting up the config entry.
    async_add_entities(entities)


class NoaaImageEntity(ImageEntity):
    """Base class for the NOAA image entities.

    Subclasses supply the upstream URL, the content type and a short label
    used in log messages; everything else -- fetching, caching, failure
    handling and the refresh timer -- lives here.

    The important behaviour is that ``async_image()`` never performs I/O.  It
    hands back whatever was last fetched successfully, and a failed fetch
    changes nothing at all, so a transient upstream failure is invisible to
    the dashboard: the previous frame stays on screen until a later refresh
    replaces it.

    Subclasses must assign anything ``_base_url()`` reads *before* calling
    ``super().__init__(hass)``; the base constructor resolves the first URL.
    """

    # Overridden per subclass; Home Assistant defaults everything to JPEG,
    # which is wrong for the PNG and GIF sources below.
    _attr_content_type = "image/jpeg"

    # Short human-readable subject used in log messages, e.g. "aurora forecast".
    _log_label = "NOAA"

    # Upstream URL without the cache-busting query string.  Subclasses whose
    # URL depends on instance state override ``_base_url()`` instead.
    _url = ""

    def __init__(self, hass) -> None:
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        # Note the name: Home Assistant's own ImageEntity owns ``_cached_image``
        # and stores an ``Image`` dataclass in it, so the raw bytes need a
        # attribute of their own.
        self._last_image_bytes: bytes | None = None
        # What was last fetched from the upstream URL, which for most entities
        # is the same object as ``_last_image_bytes``.  The radar loop breaks
        # that equivalence -- it displays a GIF it assembled from many fetches
        # -- so conditional revalidation and the 304 short-circuit have to key
        # off the fetched frame rather than the displayed picture.
        self._last_fetched_bytes: bytes | None = None
        self._attr_image_last_updated = None
        self._last_etag: str | None = None
        self._last_modified: str | None = None
        self._failure_count = 0
        self._image_url = self.get_cache_busted_url()

    # -- URL handling ----------------------------------------------------

    def _base_url(self) -> str:
        """Return the upstream URL without cache busting."""
        return self._url

    def get_cache_busted_url(self) -> str:
        """Return the upstream URL with a coarse timestamp appended.

        The timestamp is rounded down to a 10-minute bucket: NOAA does not
        publish these images more often than that, and a coarse bucket keeps
        upstream and CDN caching effective while still defeating a stale
        cached copy.
        """
        timestamp = dt_util.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'
        return f"{self._base_url()}?t={timestamp}"

    # -- Home Assistant plumbing -----------------------------------------

    async def async_added_to_hass(self) -> None:
        """Fetch the first frame and start the background refresh timer."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_scheduled_refresh, SCAN_INTERVAL
            )
        )
        # Kick off the first fetch as a scheduled call rather than awaiting it
        # here: entity setup must not block on a NOAA round trip, and during
        # the outages this class guards against that round trip is precisely
        # what hangs.
        self.async_on_remove(
            async_call_later(self.hass, 0, self._async_scheduled_refresh)
        )

    @property
    def entity_picture(self) -> str | None:
        """Return the picture URL, preferring Home Assistant's image proxy.

        Once a frame has been fetched the browser is pointed at
        ``/api/image_proxy/...``, which is what lets the cached copy survive a
        NOAA outage.  Before that first fetch ``image_last_updated`` is None
        and the base class returns None, which would render an empty card --
        so fall back to the upstream URL, on the grounds that the browser may
        well have working connectivity when Home Assistant does not.  That is
        exactly the case when Home Assistant restarts while its own resolver
        is broken.
        """
        return super().entity_picture or self._image_url

    async def async_image(self) -> bytes | None:
        """Return the bytes of the most recently fetched image.

        Deliberately does no I/O: a refresh failure must not be able to blank
        a picture we already have, and a slow NOAA must not be able to blow
        Home Assistant's 10-second image-proxy budget.  ``None`` (rather than
        ``b""``) is returned when nothing has ever been fetched, matching the
        upstream signature.
        """
        return self._last_image_bytes

    def _write_state_if_added(self) -> None:
        """Push new state, but only once Home Assistant has added the entity.

        A refresh that completes before the entity is added -- or after it has
        been removed -- must not raise ``NoEntitySpecifiedError``, which is
        the startup-error regression fixed in c7ed6e6.
        """
        if self.hass is None or self.entity_id is None:
            return
        self.async_write_ha_state()

    # -- Fetching --------------------------------------------------------

    async def _async_scheduled_refresh(self, now=None) -> None:
        """Refresh the cached image and publish the new state if it changed."""
        if await self._async_update_cache():
            self._write_state_if_added()

    async def _async_update_cache(self) -> bool:
        """Fetch the image and cache it.

        Returns True when the cached bytes actually changed, so the caller
        knows whether a state write is warranted.  A failed fetch changes
        nothing at all -- neither the cached bytes nor ``image_last_updated``
        -- which is what keeps the previous frame on the dashboard.
        """
        content = await self._async_fetch_image()
        if content is None:
            return False

        self._note_success()

        if content == self._last_image_bytes:
            _LOGGER.debug(
                "The %s image is unchanged (%d bytes)", self._log_label, len(content)
            )
            return False

        self._last_image_bytes = content
        self._attr_image_last_updated = dt_util.utcnow()
        _LOGGER.debug(
            "Fetched the %s image (%d bytes)", self._log_label, len(content)
        )
        return True

    def _note_success(self) -> None:
        """Reset the failure counter, announcing a recovery if there was one."""
        if self._failure_count >= IMAGE_FAILURE_WARN_AFTER:
            _LOGGER.info(
                "The %s image is available again after %d failed attempts",
                self._log_label, self._failure_count,
            )
        self._failure_count = 0

    def _conditional_headers(self) -> dict[str, str]:
        """Return revalidation headers for the copy already in hand.

        The refresh runs on a timer whether or not anyone is looking at the
        dashboard, so revalidating keeps the steady-state cost close to zero
        for sources that publish infrequently.
        """
        headers = {"User-Agent": USER_AGENT}
        if self._last_fetched_bytes is None:
            return headers
        if self._last_etag:
            headers["If-None-Match"] = self._last_etag
        elif self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
        return headers

    async def _async_fetch_image(self, url: str | None = None) -> bytes | None:
        """Fetch the image from NOAA, returning None on any failure.

        No failure path may touch ``_last_image_bytes``, ``_last_etag``,
        ``_last_modified`` or ``image_last_updated``.  That invariant is what
        keeps a blip from blanking the picture.

        ``url`` overrides the entity's own URL, which the radar loop uses to
        fall back to NOAA's ready-made animation without reimplementing any of
        the error handling below.
        """
        self._image_url = url or self.get_cache_busted_url()
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=IMAGE_FETCH_TIMEOUT)
            async with session.get(
                self._image_url,
                timeout=timeout,
                headers=self._conditional_headers(),
            ) as response:
                if response.status == 304 and self._last_fetched_bytes is not None:
                    _LOGGER.debug(
                        "The %s image is unchanged upstream (HTTP 304)",
                        self._log_label,
                    )
                    return self._last_fetched_bytes
                if response.status != 200:
                    self._log_failure(
                        f"HTTP {response.status}",
                        transient=response.status >= 500,
                    )
                    return None
                content_type = response.headers.get('content-type', '')
                content_type = content_type.split(';')[0].strip().lower()
                if 'image' not in content_type:
                    self._log_failure(
                        f"expected an image but the content type was {content_type!r}",
                        transient=False,
                    )
                    return None
                content = await response.read()
                etag = response.headers.get('etag')
                last_modified = response.headers.get('last-modified')
        except _TRANSIENT_FETCH_ERRORS as err:
            self._log_failure(f"{err}" or type(err).__name__, transient=True)
            return None
        except aiohttp.ClientError as err:
            self._log_failure(f"{err}" or type(err).__name__, transient=False)
            return None
        except Exception as err:  # noqa: BLE001
            self._log_failure(f"unexpected error: {err}", transient=False)
            return None

        if not content:
            self._log_failure("the response body was empty", transient=False)
            return None
        if len(content) > IMAGE_MAX_BYTES:
            self._log_failure(
                f"the response was {len(content)} bytes, over the "
                f"{IMAGE_MAX_BYTES} byte limit",
                transient=False,
            )
            return None

        # Serve what NOAA actually sent rather than the class default.
        self._attr_content_type = content_type
        self._last_etag = etag
        self._last_modified = last_modified
        self._last_fetched_bytes = content
        return content

    def _log_failure(self, reason: str, *, transient: bool) -> None:
        """Record a failed fetch and log it at a level that fits its duration.

        A NOAA image source being briefly unreachable is normal for a
        ``cloud_polling`` integration and is not worth an error per blip, so
        transient failures start at debug while a cached frame is still being
        served, warn once the outage has lasted a while, and only escalate to
        error when it is sustained -- and then only periodically.

        A non-transient failure (a 404, a content type that is not an image)
        means the URL or our expectations are wrong rather than the weather,
        so it always warns.
        """
        self._failure_count += 1
        count = self._failure_count

        if not transient:
            level = logging.WARNING
        elif self._last_image_bytes is None and count < IMAGE_FAILURE_WARN_AFTER:
            # Nothing to fall back on, so the user does see a blank card.
            level = logging.WARNING
        elif count == IMAGE_FAILURE_WARN_AFTER:
            level = logging.WARNING
        elif count >= IMAGE_FAILURE_ERROR_AFTER and count % IMAGE_FAILURE_ERROR_AFTER == 0:
            level = logging.ERROR
        else:
            level = logging.DEBUG

        if self._last_image_bytes is None:
            _LOGGER.log(
                level,
                "Could not fetch the %s image (attempt %d, no image cached yet): %s",
                self._log_label, count, reason,
            )
        else:
            _LOGGER.log(
                level,
                "Could not refresh the %s image (attempt %d); still showing the "
                "copy fetched at %s: %s",
                self._log_label, count, self._attr_image_last_updated, reason,
            )


class GeoelectricFieldImageEntity(NoaaImageEntity):
    """Representation of the Geoelectric Field Image."""

    _attr_content_type = "image/png"
    _log_label = "geoelectric field"
    _url = BASE_IMAGE_URL

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        self._office_code = office_code
        super().__init__(hass)

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Geoelectric Field Image'

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


class AuroraForecastImageEntity(NoaaImageEntity):
    """Representation of the aurora Field Image."""

    _attr_content_type = "image/jpeg"
    _log_label = "aurora forecast"
    _url = AURORA_URL

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        self._office_code = office_code
        super().__init__(hass)

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Aurora Forecast Image'

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


class HurricaneOutlookImageEntity(NoaaImageEntity):
    """Representation of the Hurricane Outlook Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("Outlook Image") to produce the entity ID
    ``image.noaa_hurricane_outlook_image``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/png"
    _log_label = "hurricane outlook"
    _url = HURRICANE_OUTLOOK_URL

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this entity is global (NHC).
        """
        super().__init__(hass)

    @property
    def name(self):
        """Return the local entity name."""
        return 'Outlook Image'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_outlook_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()


class RadarBaseReflectivityImageEntity(NoaaImageEntity):
    """Representation of the Radar Base Reflectivity Image for a specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the office weather device name (e.g.
    "NOAA ILM Weather") with the local entity name ("Radar Base
    Reflectivity") to produce the entity ID
    ``image.noaa_ilm_weather_radar_base_reflectivity``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/gif"

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar image entity."""
        self._office_code = office_code
        self._radar_site = radar_site
        self._log_label = f"radar base reflectivity for {office_code}"
        super().__init__(hass)

    def _base_url(self) -> str:
        """Return the NEXRAD base reflectivity URL for this radar site."""
        return NWS_RADAR_BASE_URL.format(radar=self._radar_site)

    @property
    def name(self):
        """Return the local entity name."""
        return 'Radar Base Reflectivity'

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


class RadarLoopImageEntity(NoaaImageEntity):
    """Representation of the Radar Loop Image (animated) for a specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the office weather device name (e.g.
    "NOAA ILM Weather") with the local entity name ("Radar Loop") to
    produce the entity ID ``image.noaa_ilm_weather_radar_loop``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/gif"

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar loop image entity."""
        self._office_code = office_code
        self._radar_site = radar_site
        self._log_label = f"radar loop for {office_code}"
        super().__init__(hass)

    def _base_url(self) -> str:
        """Return the NEXRAD radar loop URL for this radar site."""
        return NWS_RADAR_LOOP_URL.format(radar=self._radar_site)

    @property
    def name(self):
        """Return the local entity name."""
        return 'Radar Loop'

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


class GOESAirMassImageEntity(NoaaImageEntity):
    """Representation of the GOES-19 Air Mass RGB Satellite Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("GOES Air Mass") to produce the entity ID
    ``image.noaa_hurricane_goes_air_mass``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"
    _log_label = "GOES Air Mass"
    _url = GOES_AIRMASS_URL

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this satellite image is global and is grouped under the
        NOAA Hurricane device alongside the other tropical-cyclone
        tracking images.
        """
        super().__init__(hass)

    @property
    def name(self):
        """Return the local entity name."""
        return 'GOES Air Mass'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_goes_air_mass'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()


class GOESGeoColorImageEntity(NoaaImageEntity):
    """Representation of the GOES-19 GeoColor Satellite Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("GOES Geocolor") to produce the entity ID
    ``image.noaa_hurricane_goes_geocolor``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"
    _log_label = "GOES GeoColor"
    _url = GOES_GEOCOLOR_URL

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this satellite image is global and is grouped under the
        NOAA Hurricane device alongside the other tropical-cyclone
        tracking images.
        """
        super().__init__(hass)

    @property
    def name(self):
        """Return the local entity name."""
        return 'GOES Geocolor'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_goes_geocolor'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()
