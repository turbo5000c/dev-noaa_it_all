"""Keep a converting sensor's unit across restarts.

Home Assistant stores the unit a sensor shows (its ``sensor.private`` options)
only when the unit system converts the sensor's native unit, and never for a
temperature, which it shows in the unit system's temperature unit instead. A
sensor without one is reset at the next start to the unit the registry kept
from the start before (``SensorEntity.add_to_platform_start``, for integrations
that dropped their own conversion). So after the unit system was changed, a
sensor showed the old unit again after a restart: Temperature in °F in a
metric Home Assistant. This is probably home-assistant/core#182297; the mixin
can go once the minimum Home Assistant stores the shown unit itself, or no
longer resets a sensor after a unit-system change.
"""

from homeassistant.components.sensor import SensorDeviceClass

# The temperature units Home Assistant shows in the unit system's unit. Strings,
# as the sensors' units are, since the tests stub homeassistant.const.
_TEMPERATURE_UNITS = ("°C", "°F")


class KeepsItsUnit:
    """Mixin for a SensorEntity that Home Assistant converts to the unit system."""

    def get_initial_entity_options(self):
        """Return Home Assistant's initial options, or the unit it shows when it has none."""
        options = super().get_initial_entity_options()
        if options is not None or self.device_class is None or self.native_unit_of_measurement is None:
            return options
        unit = self.native_unit_of_measurement
        # Home Assistant's own test, with "is" (sensor/__init__.py, unit_of_measurement).
        if self.device_class is SensorDeviceClass.TEMPERATURE and unit in _TEMPERATURE_UNITS:
            unit = self.hass.config.units.temperature_unit
        # The unit Home Assistant shows without one, kept so it survives a restart.
        return {"sensor.private": {"suggested_unit_of_measurement": unit}}
