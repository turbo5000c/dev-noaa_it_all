"""Tests for location_tracker.py: following a person or device tracker."""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_core = MagicMock()
_ha_core.callback = lambda f: f
_ha_config_entries = MagicMock()
# config_flow (imported via the package) subclasses these at import time.
_ha_config_entries.ConfigFlow = type("ConfigFlow", (), {
    "__init_subclass__": classmethod(lambda cls, **kw: None),
})
_ha_config_entries.OptionsFlow = type("OptionsFlow", (), {})
_ha_event = MagicMock()
_ha_coordinator = MagicMock()
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_aiohttp = MagicMock()
_aiohttp.ClientTimeout = lambda **kwargs: kwargs

_ha_homeassistant = MagicMock()
_ha_homeassistant.config_entries = _ha_config_entries
_ha_homeassistant.core = _ha_core

_MOCK_MODULES = {
    "homeassistant": _ha_homeassistant,
    "homeassistant.core": _ha_core,
    "homeassistant.config_entries": _ha_config_entries,
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.event": _ha_event,
    "homeassistant.helpers.selector": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.discovery": MagicMock(),
    "voluptuous": MagicMock(),
    "aiohttp": _aiohttp,
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


HOME = (34.2257, -77.9447)        # Wilmington, NC
NEARBY = (34.2400, -77.8800)      # ~3.8 mi from home
NORTH_7 = (34.3271, -77.9447)     # 7 mi north of home
NORTH_9 = (34.3561, -77.9447)     # 9 mi north of home
NORTH_10_5 = (34.3779, -77.9447)  # 10.5 mi north of home
NORTH_9_8 = (34.3677, -77.9447)   # 9.8 mi north, 0.7 mi from NORTH_10_5
NORTH_13 = (34.4141, -77.9447)    # 13 mi north, 4 mi from NORTH_9
DENVER = (39.7392, -104.9903)
BOULDER = (40.0150, -105.2705)    # ~24 mi from Denver
AURORA = (39.7294, -104.8319)     # ~8.4 mi from Denver
LONDON = (51.5072, -0.1276)
ENTITY = "person.traveler"


def _state(position=None, state="not_home", **attributes):
    if position is not None:
        attributes.update(latitude=position[0], longitude=position[1])
    return SimpleNamespace(state=state, attributes=attributes)


class _Response:
    def __init__(self, status):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise OSError(f"HTTP {self.status}")


class _Get:
    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result

    async def __aexit__(self, *exc_info):
        return False


class _Session:
    """Answers the Points API: 200 inside the US, 404 elsewhere."""

    def __init__(self, error=None):
        self.urls = []
        self._error = error

    def get(self, url, **kwargs):
        self.urls.append(url)
        if self._error is not None:
            return _Get(self._error)
        latitude = float(url.split("/points/")[1].split(",")[0])
        return _Get(_Response(200 if latitude < 50 else 404))


class _TrackerTest(unittest.TestCase):

    def setUp(self):
        self.hass = MagicMock()
        self.hass.states.get = MagicMock(return_value=None)
        self.coordinators = []
        for _ in range(4):
            coordinator = MagicMock()
            coordinator.async_request_refresh = AsyncMock()
            self.coordinators.append(coordinator)
        self.session = _Session()
        _ha_event.reset_mock()

    def _tracker(self):
        from noaa_it_all.location_tracker import LocationTracker
        return LocationTracker(self.hass, ENTITY, HOME, self.coordinators + [None])

    def _session_patch(self):
        return patch(
            "noaa_it_all.location_tracker.async_get_clientsession",
            return_value=self.session,
        )

    def _evaluate(self, tracker, *states, refresh=True):
        """Decide on each state in turn, as the entity reports it."""
        async def go():
            for state in states:
                self.hass.states.get.return_value = state
                await tracker._async_evaluate(refresh=refresh)
        with self._session_patch():
            _run(go())

    def _assert_moved_to(self, location, source):
        for coordinator in self.coordinators:
            coordinator.set_location.assert_called_with(*location, source=source)

    def _assert_not_moved(self):
        for coordinator in self.coordinators:
            coordinator.set_location.assert_not_called()

    def _reset_calls(self):
        for coordinator in self.coordinators:
            coordinator.set_location.reset_mock()
            coordinator.async_request_refresh.reset_mock()


class TestTrackedPosition(unittest.TestCase):

    def _position(self, state):
        from noaa_it_all.location_tracker import tracked_position
        return tracked_position(state)

    def test_reads_and_rounds_the_coordinates(self):
        state = _state(latitude=39.739236123, longitude=-104.990251987)
        self.assertEqual(self._position(state), (39.7392, -104.9903))

    def test_no_fix_is_none(self):
        self.assertIsNone(self._position(None))
        self.assertIsNone(self._position(_state()))
        self.assertIsNone(self._position(_state(DENVER, state="unavailable")))
        self.assertIsNone(self._position(_state(DENVER, state="unknown")))

    def test_values_that_are_not_coordinates_are_none(self):
        self.assertIsNone(self._position(_state(latitude="39.7", longitude=-104.9)))
        self.assertIsNone(self._position(_state(latitude=True, longitude=-104.9)))
        self.assertIsNone(self._position(_state(latitude=91.0, longitude=-104.9)))
        self.assertIsNone(self._position(_state(latitude=39.7, longitude=181.0)))


class TestLocationAttributes(unittest.TestCase):

    def _attributes(self, coordinator):
        from noaa_it_all.location_tracker import location_attributes
        return location_attributes(coordinator, *HOME)

    def test_home_coordinates_when_not_following(self):
        coordinator = SimpleNamespace(data_location=(1.0, 2.0, None))
        self.assertEqual(
            self._attributes(coordinator),
            {"latitude": HOME[0], "longitude": HOME[1]},
        )

    def test_where_the_data_is_for_while_following_rounded_to_about_a_km(self):
        coordinator = SimpleNamespace(
            data_location=(39.739236, -104.990251, ENTITY),
            # Already moved on; the published data is still Denver's.
            latitude=BOULDER[0], longitude=BOULDER[1], location_source=ENTITY,
        )
        self.assertEqual(
            self._attributes(coordinator),
            {"latitude": 39.74, "longitude": -104.99, "location_source": ENTITY},
        )

    def test_home_while_following_shows_the_configured_coordinates(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        coordinator = SimpleNamespace(data_location=(*HOME, HOME_SOURCE))
        self.assertEqual(
            self._attributes(coordinator),
            {"latitude": HOME[0], "longitude": HOME[1], "location_source": HOME_SOURCE},
        )

    def test_a_coordinator_without_the_attribute_is_home(self):
        self.assertEqual(
            self._attributes(MagicMock()),
            {"latitude": HOME[0], "longitude": HOME[1]},
        )


class TestFollowing(_TrackerTest):

    def test_somewhere_the_nws_covers_is_followed(self):
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER))

        self._assert_moved_to(DENVER, ENTITY)
        for coordinator in self.coordinators:
            coordinator.async_request_refresh.assert_awaited_once()
        self.assertEqual(tracker.location, DENVER)
        self.assertEqual(tracker.source, ENTITY)
        self.assertEqual(len(self.session.urls), 1)
        self.assertIn("/points/39.7392,-104.9903", self.session.urls[0])

    def test_a_small_move_is_ignored(self):
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER))
        self._reset_calls()

        self._evaluate(tracker, _state(AURORA))

        self._assert_not_moved()
        self.assertEqual(len(self.session.urls), 1)
        self.assertEqual(tracker.location, DENVER)

    def test_a_larger_move_is_followed(self):
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER), _state(BOULDER))

        self._assert_moved_to(BOULDER, ENTITY)
        self.assertEqual(len(self.session.urls), 2)

    def test_leaving_the_home_radius_in_steps_is_followed(self):
        """A fix just inside the radius must not hold back the one just past it."""
        tracker = self._tracker()
        self._evaluate(tracker, _state(NORTH_9), _state(NORTH_13))

        self._assert_moved_to(NORTH_13, ENTITY)
        self.assertEqual(tracker.source, ENTITY)

    def test_wandering_around_the_edge_of_the_radius_does_not_flip(self):
        tracker = self._tracker()
        self._evaluate(tracker, _state(NORTH_10_5))
        self._reset_calls()

        self._evaluate(tracker, _state(NORTH_9_8), _state(NORTH_10_5), _state(NORTH_9_8))

        self._assert_not_moved()
        self.assertEqual(tracker.location, NORTH_10_5)
        self.assertEqual(len(self.session.urls), 1)

    def test_coming_home_goes_back_to_the_home_location(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER))
        self._reset_calls()

        self._evaluate(tracker, _state(NEARBY))

        self._assert_moved_to(HOME, HOME_SOURCE)
        for coordinator in self.coordinators:
            coordinator.async_request_refresh.assert_awaited_once()
        # Home is known to be covered: no lookup needed to go back.
        self.assertEqual(len(self.session.urls), 1)

    def test_a_fix_at_home_counts_as_home_even_near_the_followed_spot(self):
        from noaa_it_all.geo import haversine_miles
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        home_fix = (34.2344, -77.9447)  # 0.6 mi from the configured home
        self.assertLess(haversine_miles(*home_fix, *NORTH_10_5), 10)

        tracker = self._tracker()
        self._evaluate(tracker, _state(NORTH_10_5), _state(home_fix, state="home"))

        self._assert_moved_to(HOME, HOME_SOURCE)

    def test_a_burst_of_updates_becomes_one_decision_on_the_latest(self):
        tracker = self._tracker()
        tasks = []
        self.hass.async_create_task.side_effect = tasks.append

        self.hass.states.get.return_value = _state(DENVER)
        tracker._queue_evaluation(SimpleNamespace(data={}))
        self.hass.states.get.return_value = _state(BOULDER)
        tracker._queue_evaluation(SimpleNamespace(data={}))
        tracker._queue_evaluation(SimpleNamespace(data={}))

        self.assertEqual(len(tasks), 1)
        with self._session_patch():
            _run(tasks[0])
        # Decided on the state current when it ran, not on the first event's.
        self._assert_moved_to(BOULDER, ENTITY)
        self.assertEqual(len(self.session.urls), 1)

        # Once it has run, the next update queues a new decision.
        tracker._queue_evaluation(SimpleNamespace(data={}))
        self.assertEqual(len(tasks), 2)
        tasks[1].close()


class TestHomeFallback(_TrackerTest):

    def test_near_home_uses_home_without_a_lookup(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        tracker = self._tracker()
        self._evaluate(tracker, _state(NEARBY, state="home"))

        self._assert_moved_to(HOME, HOME_SOURCE)
        self.assertEqual(self.session.urls, [])

    def test_within_the_move_threshold_of_home_uses_home(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        tracker = self._tracker()
        self._evaluate(tracker, _state(NORTH_7))

        self._assert_moved_to(HOME, HOME_SOURCE)
        self.assertEqual(self.session.urls, [])

    def test_no_coordinates_uses_home(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER), _state(DENVER, state="unavailable"))

        self._assert_moved_to(HOME, HOME_SOURCE)
        self.assertEqual(tracker.location, HOME)

    def test_outside_nws_coverage_uses_home(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        tracker = self._tracker()
        self._evaluate(tracker, _state(LONDON))

        self._assert_moved_to(HOME, HOME_SOURCE)
        self.assertEqual(len(self.session.urls), 1)

    def test_outside_coverage_is_not_rechecked_on_every_small_move(self):
        tracker = self._tracker()
        self._evaluate(
            tracker,
            _state(LONDON),
            _state((51.5080, -0.1300)),
            _state((51.5100, -0.1200)),
        )
        self.assertEqual(len(self.session.urls), 1)

    def test_an_api_error_changes_nothing_and_updates_wait_for_the_retry(self):
        _ha_event.async_call_later = MagicMock(return_value=MagicMock())
        tracker = self._tracker()
        self._evaluate(tracker, _state(NEARBY))
        self._reset_calls()
        self.session = _Session(error=OSError("Connection reset"))

        self._evaluate(tracker, _state(DENVER), _state(DENVER), _state(BOULDER))

        self._assert_not_moved()
        self.assertEqual(tracker.location, HOME)
        # One failed check, then the pending retry decides -- not every update.
        self.assertEqual(len(self.session.urls), 1)

    def test_coming_home_still_applies_while_a_retry_is_pending(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        _ha_event.async_call_later = MagicMock(return_value=MagicMock())
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER))  # followed
        self.session = _Session(error=OSError("Connection reset"))
        self._evaluate(tracker, _state(BOULDER))  # check fails, retry pending
        self._reset_calls()

        self._evaluate(tracker, _state(NEARBY))

        self._assert_moved_to(HOME, HOME_SOURCE)

    def test_a_first_decision_that_cannot_reach_the_nws_is_labelled_home(self):
        from noaa_it_all.location_tracker import HOME as HOME_SOURCE
        _ha_event.async_call_later = MagicMock(return_value=MagicMock())
        self.session = _Session(error=OSError("Connection reset"))
        tracker = self._tracker()

        self._evaluate(tracker, _state(DENVER))

        self._assert_moved_to(HOME, HOME_SOURCE)
        self.assertEqual(tracker.source, HOME_SOURCE)

    def test_outside_coverage_is_forgotten_after_a_while(self):
        import noaa_it_all.location_tracker as module
        tracker = self._tracker()
        with patch.object(module.time, "monotonic", return_value=1000.0):
            self._evaluate(tracker, _state(LONDON))
        later = 1000.0 + module.OUTSIDE_COVERAGE_MEMORY.total_seconds() + 1
        with patch.object(module.time, "monotonic", return_value=later):
            self._evaluate(tracker, _state((51.5080, -0.1300)))
        self.assertEqual(len(self.session.urls), 2)

    def test_an_api_error_schedules_a_retry_without_waiting_for_a_move(self):
        from noaa_it_all.location_tracker import COVERAGE_RETRY
        cancel = MagicMock()
        _ha_event.async_call_later = MagicMock(return_value=cancel)
        self.session = _Session(error=OSError("Connection reset"))
        tracker = self._tracker()

        self._evaluate(tracker, _state(DENVER))

        args = _ha_event.async_call_later.call_args.args
        self.assertEqual(args[1], COVERAGE_RETRY)
        # The retry re-decides on the entity's current state.
        tasks = []
        self.hass.async_create_task.side_effect = tasks.append
        self.session = _Session()
        args[2](None)
        self.assertEqual(len(tasks), 1)
        with self._session_patch():
            _run(tasks[0])
        self._assert_moved_to(DENVER, ENTITY)

    def test_stopping_cancels_a_pending_retry(self):
        cancel = MagicMock()
        _ha_event.async_call_later = MagicMock(return_value=cancel)
        self.session = _Session(error=OSError("Connection reset"))
        tracker = self._tracker()
        self._evaluate(tracker, _state(DENVER))

        tracker.async_stop()

        cancel.assert_called_once()


class TestPrivacy(_TrackerTest):

    def test_a_failed_coverage_check_keeps_coordinates_out_of_the_warning(self):
        class _ClientResponseError(Exception):
            status = 503

        self.session = _Session(error=_ClientResponseError(
            "503, message='Service Unavailable', "
            "url='https://api.weather.gov/points/39.7392,-104.9903'"
        ))
        tracker = self._tracker()

        with self.assertLogs("noaa_it_all.location_tracker", level="INFO") as logs:
            self._evaluate(tracker, _state(DENVER))

        warnings = [r.getMessage() for r in logs.records if r.levelname == "WARNING"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("503", warnings[0])
        for record in logs.records:
            if record.levelname != "DEBUG":
                self.assertNotIn("39.7392", record.getMessage())
                self.assertNotIn("104.99", record.getMessage())


class TestLifecycle(_TrackerTest):

    def test_an_update_queued_before_stop_changes_nothing(self):
        tracker = self._tracker()
        tracker.async_stop()

        self._evaluate(tracker, _state(DENVER))

        self._assert_not_moved()
        self.assertEqual(self.session.urls, [])

    def test_no_new_decisions_are_queued_after_stop(self):
        tracker = self._tracker()
        tracker.async_stop()
        tracker._queue_evaluation(SimpleNamespace(data={}))
        self.hass.async_create_task.assert_not_called()

    def test_start_applies_the_current_position_without_refreshing(self):
        self.hass.states.get = MagicMock(return_value=_state(DENVER))
        tracker = self._tracker()

        with self._session_patch():
            _run(tracker.async_start())

        self._assert_moved_to(DENVER, ENTITY)
        # setup refreshes every coordinator right after this.
        for coordinator in self.coordinators:
            coordinator.async_request_refresh.assert_not_awaited()
        self.hass.states.get.assert_called_with(ENTITY)

    def test_start_subscribes_before_the_first_decision(self):
        """An update arriving while the first coverage check runs is not lost."""
        order = []
        _ha_event.async_track_state_change_event = MagicMock(
            side_effect=lambda *a: order.append("subscribe") or MagicMock()
        )
        self.hass.states.get = MagicMock(
            side_effect=lambda entity_id: order.append("decide") or _state(DENVER)
        )
        tracker = self._tracker()

        with self._session_patch():
            _run(tracker.async_start())

        self.assertEqual(order[:2], ["subscribe", "decide"])

    def test_start_follows_the_entity_and_stop_lets_go(self):
        unsubscribe = MagicMock()
        track = MagicMock(return_value=unsubscribe)
        _ha_event.async_track_state_change_event = track
        tracker = self._tracker()

        with self._session_patch():
            _run(tracker.async_start())

        args = track.call_args.args
        self.assertEqual(args[1], [ENTITY])
        handler = args[2]
        handler(SimpleNamespace(data={"new_state": _state(DENVER)}))
        self.hass.async_create_task.assert_called_once()
        self.hass.async_create_task.call_args.args[0].close()

        tracker.async_stop()
        unsubscribe.assert_called_once()
        tracker.async_stop()
        unsubscribe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
