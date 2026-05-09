"""Tests for the NOAA entity-ID normalization helper.

Covers ``custom_components.noaa_it_all.helpers.normalize_noaa_entity_object_id``
and the :class:`NoaaEntityIdNormalizationMixin` which uses it.

These tests verify that duplicated office prefixes such as
``noaa_ilm_weather_noaa_ilm_extended_forecast`` are collapsed to the
correct ``noaa_ilm_weather_extended_forecast`` for every supported NWS
office and per-office device group (weather, surf, space), while
leaving valid entity IDs (global hurricane/space and unrelated
office-specific entities) unchanged.
"""

import asyncio
import os
import sys
import unittest

# Ensure the package under test resolves via ``noaa_it_all`` like the
# rest of the test suite.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ``helpers`` is a pure-Python module with no Home Assistant imports,
# so we can import it directly via the ``custom_components/noaa_it_all``
# pythonpath entry (mirroring how ``test_parsers.py`` imports
# ``parsers``) — this keeps the test independent of HA.
from helpers import (  # noqa: E402
    NoaaEntityIdNormalizationMixin,
    normalize_noaa_entity_object_id,
)


class TestNormalizeNoaaEntityObjectId(unittest.TestCase):
    """Verify duplicate-prefix collapsing behaviour."""

    # -- Required cases from the issue ---------------------------------

    def test_extended_forecast_duplicate_prefix_collapsed(self):
        """Issue case 1: duplicated weather prefix for ILM."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_weather_noaa_ilm_extended_forecast", "ilm"
            ),
            "noaa_ilm_weather_extended_forecast",
        )

    def test_extended_forecast_different_office(self):
        """Issue case 2: duplicated weather prefix for SGX."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_sgx_weather_noaa_sgx_extended_forecast", "SGX"
            ),
            "noaa_sgx_weather_extended_forecast",
        )

    def test_lox_current_conditions_duplicate_prefix_collapsed(self):
        """Issue example: duplicated weather prefix for LOX."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_lox_weather_noaa_lox_current_conditions", "lox"
            ),
            "noaa_lox_weather_current_conditions",
        )

    def test_surf_group_duplicate_prefix_collapsed(self):
        """Issue case 3: non-weather grouped (surf) entity."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_surf_noaa_ilm_rip_current_risk", "ilm"
            ),
            "noaa_ilm_surf_rip_current_risk",
        )

    def test_global_hurricane_entity_unchanged(self):
        """Issue case 4: hurricane global entity stays unchanged."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_weather_hurricane_activity", "ilm"
            ),
            "noaa_weather_hurricane_activity",
        )

    def test_global_space_entity_unchanged(self):
        """Issue case 5: global space entity stays unchanged."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_space_planetary_k_index", "ilm"
            ),
            "noaa_space_planetary_k_index",
        )

    def test_office_specific_entity_without_duplicate_unchanged(self):
        """Issue case 6: a valid office-specific entity stays unchanged."""
        self.assertEqual(
            normalize_noaa_entity_object_id("noaa_ilm_temperature", "ilm"),
            "noaa_ilm_temperature",
        )

    # -- Additional defensive cases ------------------------------------

    def test_space_group_duplicate_prefix_collapsed(self):
        """Duplicated ``noaa_{office}_space_`` prefix is collapsed."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_space_noaa_ilm_aurora_next_time", "ilm"
            ),
            "noaa_ilm_space_aurora_next_time",
        )

    def test_works_for_every_supported_office_code(self):
        """Requirement 5: fix must work for every supported office."""
        from const import OFFICE_COORDINATES
        for office in OFFICE_COORDINATES:
            office_lc = office.lower()
            for group in ("weather", "surf", "space"):
                broken = (
                    f"noaa_{office_lc}_{group}_"
                    f"noaa_{office_lc}_some_metric"
                )
                expected = f"noaa_{office_lc}_{group}_some_metric"
                self.assertEqual(
                    normalize_noaa_entity_object_id(broken, office),
                    expected,
                    f"office={office} group={group}",
                )

    def test_idempotent_when_no_duplicate(self):
        """Calling on an already-clean object_id is a no-op."""
        clean = "noaa_ilm_weather_extended_forecast"
        self.assertEqual(
            normalize_noaa_entity_object_id(clean, "ilm"), clean,
        )
        # Double application stays stable.
        self.assertEqual(
            normalize_noaa_entity_object_id(
                normalize_noaa_entity_object_id(clean, "ilm"), "ilm",
            ),
            clean,
        )

    def test_pathological_repeat_duplicate_collapsed(self):
        """If duplicate-prefix appears repeatedly the while-loop collapses all of them."""
        broken = (
            "noaa_ilm_weather_noaa_ilm_noaa_ilm_extended_forecast"
        )
        # The while-loop replaces ``noaa_ilm_weather_noaa_ilm_`` once,
        # then re-detects the freshly-formed ``noaa_ilm_weather_noaa_ilm_``
        # prefix and collapses it again, yielding the clean object_id.
        self.assertEqual(
            normalize_noaa_entity_object_id(broken, "ilm"),
            "noaa_ilm_weather_extended_forecast",
        )

    def test_uppercase_office_code_handled(self):
        """Office code is matched case-insensitively."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_sgx_weather_noaa_sgx_extended_forecast", "SGX"
            ),
            "noaa_sgx_weather_extended_forecast",
        )

    def test_input_lowercased(self):
        """Result is always lowercase to match HA entity_id slug rules."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "NOAA_ILM_WEATHER_NOAA_ILM_EXTENDED_FORECAST", "ilm"
            ),
            "noaa_ilm_weather_extended_forecast",
        )

    def test_no_office_only_lowercases(self):
        """Without an office code we cannot dedupe — only lowercase."""
        broken = "noaa_ilm_weather_noaa_ilm_extended_forecast"
        self.assertEqual(
            normalize_noaa_entity_object_id(broken, None), broken,
        )

    def test_empty_input(self):
        """Empty / falsy input is returned unchanged."""
        self.assertEqual(normalize_noaa_entity_object_id("", "ilm"), "")
        self.assertIsNone(normalize_noaa_entity_object_id(None, "ilm"))

    def test_other_office_in_id_not_touched(self):
        """An office prefix that does not match the entity's office is kept."""
        # Entity belongs to ILM but the object_id mentions SGX — leave SGX alone.
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_sgx_weather_noaa_sgx_extended_forecast", "ilm"
            ),
            "noaa_sgx_weather_noaa_sgx_extended_forecast",
        )


# ---------------------------------------------------------------------
# Mixin behaviour
# ---------------------------------------------------------------------


def _run(coro):
    """Run a coroutine on a fresh event loop (sync test helper)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _DummyParent:
    """Stand-in for a Home Assistant ``Entity`` base class.

    Records whether ``async_added_to_hass`` was awaited so we can prove
    the mixin cooperates with the rest of the MRO instead of replacing
    it.
    """

    def __init__(self):
        self.parent_called = False

    async def async_added_to_hass(self):  # pragma: no cover - trivial
        self.parent_called = True


class _DummyEntity(NoaaEntityIdNormalizationMixin, _DummyParent):
    def __init__(self, entity_id, office_code):
        super().__init__()
        self.entity_id = entity_id
        self._office_code = office_code


class TestNoaaEntityIdNormalizationMixin(unittest.TestCase):
    """Verify the mixin sanitizes ``entity_id`` once added to Home Assistant."""

    def test_mixin_strips_duplicate_prefix(self):
        ent = _DummyEntity(
            "sensor.noaa_ilm_weather_noaa_ilm_extended_forecast", "ilm",
        )
        _run(ent.async_added_to_hass())
        self.assertEqual(
            ent.entity_id, "sensor.noaa_ilm_weather_extended_forecast",
        )
        self.assertTrue(
            ent.parent_called,
            "Mixin must call super().async_added_to_hass() cooperatively",
        )

    def test_mixin_leaves_clean_entity_id_alone(self):
        ent = _DummyEntity("sensor.noaa_ilm_temperature", "ilm")
        _run(ent.async_added_to_hass())
        self.assertEqual(ent.entity_id, "sensor.noaa_ilm_temperature")

    def test_mixin_leaves_global_entities_alone(self):
        for entity_id in (
            "sensor.noaa_weather_hurricane_activity",
            "sensor.noaa_space_planetary_k_index",
        ):
            ent = _DummyEntity(entity_id, "ilm")
            _run(ent.async_added_to_hass())
            self.assertEqual(ent.entity_id, entity_id)

    def test_mixin_no_op_without_office_code(self):
        ent = _DummyEntity(
            "sensor.noaa_ilm_weather_noaa_ilm_extended_forecast", None,
        )
        _run(ent.async_added_to_hass())
        # Without an office_code we cannot safely strip the duplicate;
        # the mixin must leave entity_id unchanged.
        self.assertEqual(
            ent.entity_id,
            "sensor.noaa_ilm_weather_noaa_ilm_extended_forecast",
        )

    def test_mixin_no_op_without_entity_id(self):
        ent = _DummyEntity(None, "ilm")
        _run(ent.async_added_to_hass())
        self.assertIsNone(ent.entity_id)


if __name__ == "__main__":
    unittest.main()
