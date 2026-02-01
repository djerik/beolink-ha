"""State extraction and conversion utilities for BeoLink integration."""

from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE
from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import State


def get_target_temperature(state: State) -> float | None:
    """Extract and round target temperature from state."""
    temp = state.attributes.get(ATTR_TEMPERATURE)
    if isinstance(temp, (int, float)):
        return round(temp)
    return None


def get_current_temperature(state: State) -> float | None:
    """Extract and round current temperature from state."""
    temp = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
    if isinstance(temp, (int, float)):
        return round(temp)
    return None


def get_brightness_level(state: State) -> int:
    """Get brightness as 0-100 percentage.

    Home Assistant uses 0-255 for brightness, this converts to 0-100.
    """
    brightness = state.attributes.get("brightness", 0)
    if brightness:
        return int((brightness / 255) * 100)
    return 0


def get_cover_position(state: State) -> int:
    """Get cover position as 0-100 percentage."""
    return state.attributes.get(ATTR_CURRENT_POSITION, 0)


def map_hvac_mode_to_beolink(hvac_mode: str | None) -> str:
    """Map Home Assistant HVAC mode to BeoLink mode.

    BeoLink expects: "Off", "Heat", "Cool", "Auto", "Eco"
    """
    if not hvac_mode:
        return "Off"

    mode_map = {
        "off": "Off",
        "heat": "Heat",
        "cool": "Cool",
        "auto": "Auto",
        "heat_cool": "Auto",
        "dry": "Auto",
        "fan_only": "Auto",
    }
    return mode_map.get(hvac_mode, "Off")


def map_beolink_mode_to_hvac(beolink_mode: str) -> str:
    """Map BeoLink mode to Home Assistant HVAC mode."""
    mode_map = {
        "Off": "off",
        "Heat": "heat",
        "Cool": "cool",
        "Auto": "auto",
        "Eco": "heat",  # Map Eco to heat as HA doesn't have eco as hvac_mode
    }
    return mode_map.get(beolink_mode, "off")
