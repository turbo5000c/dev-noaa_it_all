"""Follow a person or device tracker so location-based data moves with it.

Observations, forecasts, cloud cover and NWS alerts are all looked up from
coordinates. With a tracked entity configured, those coordinates follow the
entity instead of staying on the configured home location, so the weather
on a trip is the weather where you are.

Home stays the fallback: when the entity has no usable coordinates, when it
is near home, or when it is somewhere the NWS does not cover (the Points API
answers 404 outside the US and its territories). The location only changes
once the entity has moved ``TRACKING_MIN_MOVE_MILES`` from where the data
currently comes from, and switches back to home within
``TRACKING_RETURN_HOME_MILES`` of it. Entity IDs, unique IDs and device names
are untouched, so a trip never creates new entities.
"""

import asyncio
import logging
import time
from datetime import timedelta
from typing import Iterable, Optional

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DEFAULT_SCAN_INTERVAL,
    LOCATION_SOURCE_HOME,
    NWS_POINTS_URL,
    REQUEST_TIMEOUT,
    TRACKING_MIN_MOVE_MILES,
    TRACKING_RETURN_HOME_MILES,
    USER_AGENT,
)
from .geo import haversine_miles

_LOGGER = logging.getLogger(__name__)

# Kept for readability at the call sites below.
HOME = LOCATION_SOURCE_HOME

# A coverage check that could not reach the NWS is tried again after this
# long, rather than waiting for the entity to move -- which a parked phone
# may not do for hours. Until then, updates do not ask again.
COVERAGE_RETRY = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

# How long a place found to be outside NWS coverage is remembered as such,
# so that updates from around it do not each ask again. Short, so a one-off
# 404 does not stick to a place, or to the US side of a nearby border.
OUTSIDE_COVERAGE_MEMORY = COVERAGE_RETRY

# Decimal places of the followed position shown in entity attributes:
# about 1 km, enough to say where the data is for without publishing the
# person's exact position to everyone who can see a weather entity.
ATTRIBUTE_DECIMALS = 2

_NO_POSITION_STATES = ("unavailable", "unknown")


def tracked_position(state) -> Optional[tuple[float, float]]:
    """Return a tracker state's (latitude, longitude), or None without a fix.

    Rounded to four decimal places (about 11 m): the NWS Points API redirects
    anything finer, and nothing here needs more.
    """
    if state is None or state.state in _NO_POSITION_STATES:
        return None
    latitude = state.attributes.get("latitude")
    longitude = state.attributes.get("longitude")
    for value in (latitude, longitude):
        # bool is an int subclass; a True latitude is not a coordinate.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return round(float(latitude), 4), round(float(longitude), 4)


def location_attributes(coordinator, latitude, longitude) -> dict:
    """``latitude``/``longitude`` attributes for an entity fed by ``coordinator``.

    The configured coordinates, unless the coordinator follows a tracked
    entity -- then where the published data was fetched for, which lags a
    move until the next refresh lands, and from whom.
    """
    fetched_for = getattr(coordinator, "data_location", None)
    if not isinstance(fetched_for, tuple) or not isinstance(fetched_for[2], str):
        return {"latitude": latitude, "longitude": longitude}
    data_latitude, data_longitude, source = fetched_for
    if source == HOME:
        return {"latitude": latitude, "longitude": longitude, "location_source": source}
    return {
        "latitude": round(data_latitude, ATTRIBUTE_DECIMALS),
        "longitude": round(data_longitude, ATTRIBUTE_DECIMALS),
        "location_source": source,
    }


def location_source_attribute(coordinator) -> dict:
    """``location_source`` for an entity fed by ``coordinator``, while following.

    For entities with no coordinates of their own to report.
    """
    fetched_for = getattr(coordinator, "data_location", None)
    if not isinstance(fetched_for, tuple) or not isinstance(fetched_for[2], str):
        return {}
    return {"location_source": fetched_for[2]}


class LocationTracker:
    """Point location-based coordinators at a tracked entity's position."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        home: tuple[float, float],
        coordinators: Iterable,
    ) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._home = home
        self._coordinators = [c for c in coordinators if c is not None]
        self._location: tuple[float, float] = home
        self._source: Optional[str] = None
        # The last position found to be outside NWS coverage, and when, so
        # that GPS updates from around it do not each repeat the check.
        self._last_outside: Optional[tuple[float, float]] = None
        self._last_outside_at = 0.0
        self._lock = asyncio.Lock()
        self._queued = False
        self._stopped = False
        self._unsubscribe = None
        self._cancel_retry = None

    @property
    def location(self) -> tuple[float, float]:
        """The coordinates currently in use."""
        return self._location

    @property
    def source(self) -> Optional[str]:
        """The tracked entity while following it, HOME otherwise."""
        return self._source

    async def async_start(self) -> None:
        """Apply the entity's current position, then follow its changes.

        Called before the coordinators' first refresh, so that refresh is
        already for the right place and needs no second one.
        """
        # Imported here rather than at module level so importing the package
        # does not need it; Home Assistant core always has it loaded.
        from homeassistant.helpers.event import async_track_state_change_event

        # Subscribe first: an update that arrives while the first decision
        # is waiting on the NWS then queues another, instead of being lost.
        self._unsubscribe = async_track_state_change_event(
            self._hass, [self._entity_id], self._queue_evaluation
        )
        await self._async_evaluate(refresh=False)

    @callback
    def async_stop(self) -> None:
        """Stop following the entity."""
        # An evaluation already queued must not move coordinators that are
        # being unloaded.
        self._stopped = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None

    @callback
    def _queue_evaluation(self, *_args) -> None:
        """Queue a decision on the entity's position, unless one is waiting.

        Takes the place of the event's own new_state: the decision reads
        whatever the state is once it runs, so a burst of GPS updates that
        arrives while a lookup is in flight becomes one decision on the
        latest position rather than one per position already passed.
        """
        if self._queued or self._stopped:
            return
        self._queued = True
        self._hass.async_create_task(self._async_evaluate())

    def _schedule_retry(self) -> None:
        from homeassistant.helpers.event import async_call_later

        if self._cancel_retry is not None:
            self._cancel_retry()
        self._cancel_retry = async_call_later(
            self._hass, COVERAGE_RETRY, self._retry
        )

    @callback
    def _retry(self, _now) -> None:
        self._cancel_retry = None
        self._queue_evaluation()

    async def _async_evaluate(self, refresh: bool = True) -> None:
        async with self._lock:
            self._queued = False
            if self._stopped:
                return
            position = tracked_position(self._hass.states.get(self._entity_id))

            if position is None:
                await self._async_apply(self._home, HOME, refresh)
                return
            if haversine_miles(*position, *self._home) < TRACKING_RETURN_HOME_MILES:
                await self._async_apply(self._home, HOME, refresh)
                return
            # Moves are measured from the location in use, home included, so
            # GPS wandering around the edge of the home radius does not flip
            # between the two.
            if (
                self._source is not None
                and haversine_miles(*position, *self._location) < TRACKING_MIN_MOVE_MILES
            ):
                return
            if haversine_miles(*position, *self._home) < TRACKING_MIN_MOVE_MILES:
                await self._async_apply(self._home, HOME, refresh)
                return
            if (
                self._last_outside is not None
                and time.monotonic() - self._last_outside_at
                < OUTSIDE_COVERAGE_MEMORY.total_seconds()
                and haversine_miles(*position, *self._last_outside)
                < TRACKING_MIN_MOVE_MILES
            ):
                # Still around a place just found to be outside coverage.
                await self._async_apply(self._home, HOME, refresh)
                return
            if self._cancel_retry is not None:
                # The NWS could not be reached a moment ago; the scheduled
                # retry decides, rather than every update asking again.
                return

            covered = await self._async_nws_covers(position)
            if self._stopped:
                return
            if covered is None:
                # Could not tell. Leave everything as it is and decide again
                # when the retry fires. On the very first decision that means
                # home, so say so rather than leaving it unlabelled.
                self._schedule_retry()
                if self._source is None:
                    await self._async_apply(self._home, HOME, refresh)
                return
            if covered:
                self._last_outside = None
                await self._async_apply(position, self._entity_id, refresh)
            else:
                self._last_outside = position
                self._last_outside_at = time.monotonic()
                _LOGGER.info(
                    "%s is outside NWS coverage; using the home location",
                    self._entity_id,
                )
                await self._async_apply(self._home, HOME, refresh)

    async def _async_apply(
        self, location: tuple[float, float], source: str, refresh: bool
    ) -> None:
        if location == self._location and source == self._source:
            return
        self._location = location
        self._source = source
        # Coordinates only at debug: logs get pasted into bug reports.
        _LOGGER.info(
            "Location-based NOAA data now uses %s",
            "the home location" if source == HOME else f"the location of {source}",
        )
        _LOGGER.debug("New location: %s, %s", location[0], location[1])
        for coordinator in self._coordinators:
            coordinator.set_location(*location, source=source)
        if refresh:
            await asyncio.gather(
                *(c.async_request_refresh() for c in self._coordinators),
                return_exceptions=True,
            )

    async def _async_nws_covers(self, position: tuple[float, float]) -> Optional[bool]:
        """Whether the NWS has a forecast for ``position``; None if unknown."""
        session = async_get_clientsession(self._hass)
        url = NWS_POINTS_URL.format(lat=position[0], lon=position[1])
        try:
            async with session.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 404:
                    return False
                resp.raise_for_status()
                return True
        except Exception as err:
            # aiohttp errors embed the request URL, which holds the followed
            # coordinates; keep those out of the warning.
            status = getattr(err, "status", None)
            _LOGGER.warning(
                "Could not check NWS coverage for %s, will retry: %s%s",
                self._entity_id, type(err).__name__,
                f" {status}" if status else "",
            )
            _LOGGER.debug("Coverage check failed: %s", err)
            return None
