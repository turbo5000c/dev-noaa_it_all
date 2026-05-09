"""Shared helper utilities for NOAA Integration entities.

This module provides defensive helpers used by every NOAA entity class
to keep entity object IDs (and therefore Home Assistant ``entity_id``
values) free of duplicated office-code prefixes.

Background
----------

NOAA entities are grouped under per-office, per-domain devices such as
``NOAA ILM Weather`` (slug ``noaa_ilm_weather``) and given names such as
``NOAA ILM Extended Forecast``.  Depending on the Home Assistant entity
naming mode, this can cause the device slug to be concatenated with the
entity name slug — yielding broken entity IDs like::

    sensor.noaa_ilm_weather_noaa_ilm_extended_forecast

The expected entity ID is::

    sensor.noaa_ilm_weather_extended_forecast

To prevent that class of bug regardless of where the entity_id is
constructed, every NOAA entity should pass its candidate object_id
through :func:`normalize_noaa_entity_object_id` (or inherit
:class:`NoaaEntityIdNormalizationMixin`, which performs the
normalization automatically when the entity is added to Home Assistant).
"""

from __future__ import annotations

import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)


# Domain/group names that may appear in per-office NOAA device slugs.
# These match the ``identifiers`` produced by ``device_info`` on the
# various sensor base classes (weather, surf, space).  Hurricane is a
# global device (no office in its slug) so it is intentionally omitted.
_NOAA_OFFICE_DEVICE_GROUPS = ("weather", "surf", "space")


def normalize_noaa_entity_object_id(
    object_id: str,
    office_code: Optional[str] = None,
) -> str:
    """Return ``object_id`` with any duplicated office prefix removed.

    Replaces patterns of the form ``noaa_{office}_{group}_noaa_{office}_``
    with the correct ``noaa_{office}_{group}_`` prefix, for each known
    NOAA per-office device group (weather, surf, space).

    The transformation is idempotent and case-insensitive on the input
    (the result is always lowercase, matching Home Assistant's
    ``entity_id`` slug format).  When ``office_code`` is not provided
    the input is only lowercased — there is no safe way to guess which
    prefix is duplicated without knowing the office.

    Examples
    --------
    >>> normalize_noaa_entity_object_id(
    ...     "noaa_ilm_weather_noaa_ilm_extended_forecast", "ilm"
    ... )
    'noaa_ilm_weather_extended_forecast'

    >>> normalize_noaa_entity_object_id(
    ...     "noaa_weather_hurricane_activity", "ilm"
    ... )
    'noaa_weather_hurricane_activity'
    """
    if not object_id:
        return object_id

    object_id = object_id.lower()

    if not office_code:
        return object_id

    office = office_code.lower()
    for group in _NOAA_OFFICE_DEVICE_GROUPS:
        duplicate_prefix = f"noaa_{office}_{group}_noaa_{office}_"
        correct_prefix = f"noaa_{office}_{group}_"
        # ``while`` to defensively collapse pathological repeats such as
        # ``noaa_ilm_weather_noaa_ilm_weather_noaa_ilm_extended_forecast``
        # if they ever occur.
        while duplicate_prefix in object_id:
            object_id = object_id.replace(duplicate_prefix, correct_prefix)

    return object_id


class NoaaEntityIdNormalizationMixin:
    """Mixin that normalizes ``self.entity_id`` once added to Home Assistant.

    Any NOAA entity class that exposes ``self._office_code`` can include
    this mixin (placed *before* the Home Assistant base class in the
    MRO) to defensively strip duplicated office prefixes from its
    ``entity_id``.  If no duplication is present the entity_id is left
    untouched, so the mixin is safe to apply broadly.
    """

    async def async_added_to_hass(self) -> None:  # type: ignore[override]
        """Normalize ``self.entity_id`` after Home Assistant assigns it."""
        # Cooperatively call the next ``async_added_to_hass`` in the MRO
        # (e.g. ``CoordinatorEntity.async_added_to_hass``) before we
        # touch the entity_id.
        parent = getattr(super(), "async_added_to_hass", None)
        if callable(parent):
            await parent()

        entity_id = getattr(self, "entity_id", None)
        office_code = getattr(self, "_office_code", None)
        if not entity_id or not office_code:
            return

        domain, sep, object_id = entity_id.partition(".")
        if not sep:
            return

        normalized = normalize_noaa_entity_object_id(object_id, office_code)
        if normalized != object_id:
            new_entity_id = f"{domain}.{normalized}"
            _LOGGER.debug(
                "Normalizing NOAA entity_id %s -> %s",
                entity_id, new_entity_id,
            )
            self.entity_id = new_entity_id
